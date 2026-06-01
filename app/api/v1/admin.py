"""Admin endpoints — organization management, API keys, usage stats.

All admin endpoints require JWT authentication (Bearer token from /api/v1/auth/login).

Role-based access:
- SUPER_ADMIN: full platform control — manage all orgs, approve registrations
- ADMIN/USER: manage only their own organization (API keys, usage, settings)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.auth import get_current_superadmin, get_current_user, hash_password
from app.core.constants import OrganizationRole, OrganizationStatus
from app.core.security import generate_api_key
from app.models.api_key import ApiKey
from app.models.extraction import ExtractionLog
from app.models.organization import Organization
from app.models.quota import MonthlyQuota
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreateResult,
    ApiKeyResponse,
    ApiKeyRevoke,
)
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationListItem,
    OrganizationApproval,
    OrganizationResponse,
    OrganizationUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ────────────────────────── Organizations (SUPER_ADMIN) ──────────────────────────


@router.get("/organizations", response_model=list[OrganizationListItem])
async def list_all_organizations(
    status: str | None = Query(None, description="Filter by status: PENDING, APPROVED, REJECTED"),
    db: AsyncSession = Depends(get_db),
    _: Organization = Depends(get_current_superadmin),
):
    """List all organizations (SUPER_ADMIN only). Optionally filter by status."""
    stmt = select(Organization).order_by(Organization.created_at.desc())
    if status:
        stmt = stmt.where(Organization.status == status.upper())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/organizations/pending", response_model=list[OrganizationListItem])
async def list_pending_organizations(
    db: AsyncSession = Depends(get_db),
    _: Organization = Depends(get_current_superadmin),
):
    """List organizations awaiting approval (SUPER_ADMIN only)."""
    result = await db.execute(
        select(Organization)
        .where(Organization.status == OrganizationStatus.PENDING)
        .order_by(Organization.created_at.asc())
    )
    return result.scalars().all()


@router.patch("/organizations/{org_id}/approve", response_model=OrganizationResponse)
async def approve_organization(
    org_id: UUID,
    body: OrganizationApproval,
    db: AsyncSession = Depends(get_db),
    _: Organization = Depends(get_current_superadmin),
):
    """Approve or reject a pending organization (SUPER_ADMIN only)."""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if org.status != OrganizationStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Organization is already {org.status}, not PENDING",
        )

    if body.status == OrganizationStatus.APPROVED:
        org.status = OrganizationStatus.APPROVED
        org.is_active = True
    elif body.status == OrganizationStatus.REJECTED:
        org.status = OrganizationStatus.REJECTED
        org.is_active = False
    else:
        raise HTTPException(status_code=400, detail="Status must be APPROVED or REJECTED")

    await db.flush()
    await db.refresh(org)
    return org


@router.post("/organizations", response_model=OrganizationResponse, status_code=201)
async def create_organization_admin(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    _: Organization = Depends(get_current_superadmin),
):
    """Create an organization directly (SUPER_ADMIN only — skips approval)."""
    result = await db.execute(
        select(Organization).where(Organization.email == body.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    org = Organization(
        name=body.name,
        email=body.email,
        plan=body.plan.value,
        role=body.role.value,
        status=body.status.value,
        password_hash=hash_password(body.password),
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return org


# ────────────────────────── My Organization (all authenticated) ──────────────────────────


@router.get("/organizations/me", response_model=OrganizationResponse)
async def get_my_organization(
    org: Organization = Depends(get_current_user),
):
    """Get the current authenticated organization's details."""
    return org


@router.patch("/organizations/me", response_model=OrganizationResponse)
async def update_my_organization(
    body: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_user),
):
    """Update current organization. Only SUPER_ADMIN can change role/status."""
    update_data = body.model_dump(exclude_unset=True)

    # Non-superadmin users cannot change their own role or status
    if org.role != OrganizationRole.SUPER_ADMIN:
        for forbidden in ("role", "status"):
            if forbidden in update_data:
                del update_data[forbidden]

    if "plan" in update_data and hasattr(update_data["plan"], "value"):
        update_data["plan"] = update_data["plan"].value
    if "role" in update_data and hasattr(update_data["role"], "value"):
        update_data["role"] = update_data["role"].value
    if "status" in update_data and hasattr(update_data["status"], "value"):
        update_data["status"] = update_data["status"].value

    for key, val in update_data.items():
        setattr(org, key, val)

    await db.flush()
    await db.refresh(org)
    return org


# ────────────────────────── API Keys ──────────────────────────


@router.post("/api-keys", response_model=ApiKeyCreateResult, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_user),
):
    """Create a new API key for the authenticated organization.

    The raw key is returned **only once** — store it securely.
    """
    if body.organization_id != org.id:
        raise HTTPException(status_code=403, detail="Cannot create keys for other organizations")

    raw_key, key_hash, prefix_display = generate_api_key(live=body.is_live)

    api_key = ApiKey(
        organization_id=org.id,
        key_hash=key_hash,
        key_prefix=prefix_display,
        scopes=body.scopes,
        is_live=body.is_live,
        expires_at=body.expires_at,
    )
    db.add(api_key)
    await db.flush()

    return ApiKeyCreateResult(
        id=api_key.id,
        raw_key=raw_key,
        key_prefix=prefix_display,
        scopes=body.scopes,
        is_live=body.is_live,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_my_api_keys(
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_user),
):
    """List API keys for the authenticated organization."""
    stmt = (
        select(ApiKey)
        .where(ApiKey.organization_id == org.id)
        .order_by(ApiKey.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/api-keys/revoke")
async def revoke_api_key(
    body: ApiKeyRevoke,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_user),
):
    """Revoke an API key belonging to the authenticated organization."""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == body.id,
            ApiKey.organization_id == org.id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    await db.flush()
    return {"status": "revoked", "id": str(api_key.id)}


# ────────────────────────── Usage Stats ──────────────────────────


@router.get("/usage")
async def get_usage_stats(
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_user),
):
    """Get extraction usage stats for the authenticated organization."""
    stmt = (
        select(
            ExtractionLog.document_type,
            ExtractionLog.status,
            func.count(ExtractionLog.id).label("count"),
            func.avg(ExtractionLog.confidence_score).label("avg_confidence"),
            func.avg(ExtractionLog.processing_time_ms).label("avg_time_ms"),
        )
        .where(ExtractionLog.organization_id == org.id)
        .group_by(
            ExtractionLog.document_type,
            ExtractionLog.status,
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    stats = []
    for row in rows:
        stats.append({
            "document_type": row.document_type,
            "status": row.status,
            "count": row.count,
            "avg_confidence": round(float(row.avg_confidence or 0), 3),
            "avg_time_ms": round(float(row.avg_time_ms or 0), 1),
        })

    return {
        "organization_id": str(org.id),
        "plan": org.plan,
        "usage": stats,
    }


@router.get("/quota")
async def get_my_quota(
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_user),
):
    """Get current month's quota status."""
    now = __import__("datetime").datetime.utcnow()
    result = await db.execute(
        select(MonthlyQuota).where(
            MonthlyQuota.organization_id == org.id,
            MonthlyQuota.year == now.year,
            MonthlyQuota.month == now.month,
        )
    )
    quota = result.scalar_one_or_none()

    from app.services.tier_service import get_tier_config
    limit = get_tier_config(org.plan)["extractions_per_month"]

    if not quota:
        return {
            "organization_id": str(org.id),
            "year": now.year,
            "month": now.month,
            "extractions_used": 0,
            "extractions_limit": limit,
            "remaining": limit if limit >= 0 else "unlimited",
        }

    return {
        "organization_id": str(quota.organization_id),
        "year": quota.year,
        "month": quota.month,
        "extractions_used": quota.extractions_used,
        "extractions_limit": quota.extractions_limit,
        "remaining": quota.extractions_limit - quota.extractions_used if quota.extensions_limit >= 0 else quota.extractions_limit,  # legacy typo preserved
    }
