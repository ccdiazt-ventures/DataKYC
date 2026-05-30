"""Tier service — feature gating and quota management."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DocumentType, PlanTier
from app.models.organization import Organization
from app.models.quota import MonthlyQuota

# ---------------------------------------------------------------------------
# Tier definitions — mirrors BiometriKYC pattern
# ---------------------------------------------------------------------------

TIER_CONFIGS: dict[str, dict] = {
    PlanTier.FREE: {
        "rate_per_minute": 5,
        "extractions_per_month": 10,
        "document_types": [
            DocumentType.INE_FRONT,
        ],
        "cross_validation": False,
        "fill_form": False,
        "batch_processing": False,
    },
    PlanTier.BASIC: {
        "rate_per_minute": 20,
        "extractions_per_month": 100,
        "document_types": [
            DocumentType.INE_FRONT,
            DocumentType.INE_BACK,
            DocumentType.CURP,
            DocumentType.RFC,
        ],
        "cross_validation": False,
        "fill_form": True,
        "batch_processing": False,
    },
    PlanTier.PRO: {
        "rate_per_minute": 60,
        "extractions_per_month": 1000,
        "document_types": [
            DocumentType.INE_FRONT,
            DocumentType.INE_BACK,
            DocumentType.CURP,
            DocumentType.RFC,
            DocumentType.PASSPORT,
            DocumentType.COMPROBANTE_DOMICILIO,
            DocumentType.ESTADO_CUENTA,
        ],
        "cross_validation": True,
        "fill_form": True,
        "batch_processing": False,
    },
    PlanTier.ENTERPRISE: {
        "rate_per_minute": 120,
        "extractions_per_month": -1,  # unlimited
        "document_types": ["*"],
        "cross_validation": True,
        "fill_form": True,
        "batch_processing": True,
    },
}


def get_tier_config(plan: str) -> dict:
    return TIER_CONFIGS.get(plan, TIER_CONFIGS[PlanTier.FREE])


def has_feature(plan: str, feature: str) -> bool:
    config = get_tier_config(plan)
    return config.get(feature, False)


def is_doc_type_allowed(plan: str, doc_type: DocumentType) -> bool:
    config = get_tier_config(plan)
    allowed = config["document_types"]
    if "*" in allowed:
        return True
    return doc_type.value in allowed


async def get_current_quota(
    db: AsyncSession, organization_id: UUID
) -> MonthlyQuota | None:
    """Get or create the current month's quota record."""
    now = datetime.utcnow()
    stmt = select(MonthlyQuota).where(
        MonthlyQuota.organization_id == organization_id,
        MonthlyQuota.year == now.year,
        MonthlyQuota.month == now.month,
    )
    result = await db.execute(stmt)
    quota = result.scalar_one_or_none()
    return quota


async def ensure_quota(
    db: AsyncSession, organization: Organization
) -> MonthlyQuota:
    """Get or create the current month's quota record."""
    now = datetime.utcnow()
    quota = await get_current_quota(db, organization.id)

    if quota is None:
        config = get_tier_config(organization.plan)
        limit = config["extractions_per_month"]
        quota = MonthlyQuota(
            organization_id=organization.id,
            year=now.year,
            month=now.month,
            extractions_used=0,
            extractions_limit=limit,
        )
        db.add(quota)
        await db.flush()

    return quota


async def check_and_increment_quota(
    db: AsyncSession, organization: Organization
) -> tuple[bool, str | None]:
    """Check quota and increment if allowed. Returns (allowed, error_message)."""
    quota = await ensure_quota(db, organization)

    # Unlimited
    if quota.extractions_limit < 0:
        quota.extractions_used += 1
        return True, None

    if quota.extractions_used >= quota.extractions_limit:
        return False, (
            f"Monthly extraction limit ({quota.extractions_limit}) reached. "
            f"Used: {quota.extractions_used}/{quota.extractions_limit}. "
            f"Upgrade your plan or wait until next month."
        )

    quota.extractions_used += 1
    return True, None
