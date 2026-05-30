"""Admin endpoints — organization management, API keys, usage stats.

All admin endpoints require JWT authentication (Bearer token from /api/v1/auth/login).
Each organization can only see and manage its own resources.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.auth import get_current_user, hash_password
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
    OrganizationResponse,
    OrganizationUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ───────────────────── Helpers ─────────────────────

def _require_superadmin(org: Organization):
    """Only SUPER_ADMIN (first org) can manage other organizations."""
    # For now: the organization with plan ENTERPRISE and earliest creation date
    # is considered the platform admin.
    # In production, add a dedicated `role` field.
    pass  # All authenticated orgs can manage themselves


# ────────────────────────── Organizations ──────────────────────────


@router.post("/organizations", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new organization (self-service signup)."""
    # Check email uniqueness
    result = await db.execute(
        select(Organization).where(Organization.email == body.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    org = Organization(
        name=body.name,
        email=body.email,
        plan=body.plan.value,
        password_hash=hash_password(body.password),
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return org


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
    """Update current organization (plan upgrades handled via billing)."""
    update_data = body.model_dump(exclude_unset=True)
    if "plan" in update_data and isinstance(update_data["plan"], type(org.plan)):
        update_data["plan"] = update_data["plan"].value

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
    # Verify the org owns this organization
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
        "remaining": quota.extractions_limit - quota.extractions_used if quota.extractions_limit >= 0 else "unlimited",
    }
