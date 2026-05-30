"""API dependencies for FastAPI dependency injection."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header, HTTPException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_key
from app.database import async_session_factory, get_db
from app.models.api_key import ApiKey
from app.models.organization import Organization
from app.services.tier_service import get_tier_config


async def get_redis() -> Redis:
    """Redis connection dependency."""
    from app.config import get_settings
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def get_current_api_key(
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> ApiKey:
    """Validate API key and return the ApiKey model."""
    key_hash = hash_key(x_api_key.strip())

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    )
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not api_key.is_active:
        raise HTTPException(status_code=401, detail="API key has been revoked")

    from datetime import datetime, timezone
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="API key has expired")

    return api_key


async def get_current_organization(
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get the organization associated with the current API key."""
    result = await db.execute(
        select(Organization).where(Organization.id == api_key.organization_id)
    )
    org = result.scalar_one_or_none()

    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not org.is_active:
        raise HTTPException(status_code=403, detail="Organization is suspended")

    return org


async def check_tier_feature(
    feature: str,
    org: Organization = Depends(get_current_organization),
):
    """Dependency factory: check if org plan has a specific feature."""
    config = get_tier_config(org.plan)
    if not config.get(feature, False):
        raise HTTPException(
            status_code=403,
            detail={
                "error": f"Feature '{feature}' not available in {org.plan} plan",
                "code": "FEATURE_NOT_AVAILABLE",
                "current_plan": org.plan,
                "required_feature": feature,
            },
        )
    return org
