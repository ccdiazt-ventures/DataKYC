"""API Key authentication middleware.

Authenticates requests using X-API-Key header.
Matches BiometriKYC pattern: lookup by hash, enforce active keys, track last_used.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_key
from app.database import async_session_factory
from app.models.api_key import ApiKey


class AuthenticatedRequest(Request):
    """Extended request with organization and API key context."""
    organizacion_id: UUID | None = None
    api_key_id: UUID | None = None
    api_key_scopes: list[str] = []


async def verify_api_key(
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> tuple[UUID, UUID, list[str]]:
    """Verify the API key and return (organization_id, api_key_id, scopes).

    Raises HTTPException on invalid/expired/revoked keys.
    """
    key_hash = hash_key(x_api_key.strip())

    async with async_session_factory() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()

        if api_key is None:
            raise HTTPException(status_code=401, detail="Invalid API key")

        if not api_key.is_active:
            raise HTTPException(status_code=401, detail="API key has been revoked")

        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="API key has expired")

        # Track last used
        api_key.last_used_at = datetime.now(timezone.utc)
        await session.commit()

        return (api_key.organization_id, api_key.id, api_key.scopes or [])
