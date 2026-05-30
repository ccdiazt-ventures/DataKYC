"""API key schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    organization_id: UUID
    scopes: list[str] = ["extract"]
    is_live: bool = True
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    id: UUID
    organization_id: UUID
    key_prefix: str
    scopes: list
    is_live: bool
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreateResult(BaseModel):
    """Returned when creating a new API key — raw key shown only once."""
    id: UUID
    raw_key: str
    key_prefix: str
    scopes: list
    is_live: bool


class ApiKeyRevoke(BaseModel):
    id: UUID
