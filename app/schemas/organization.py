"""Organization schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.constants import PlanTier


class OrganizationCreate(BaseModel):
    name: str
    email: str
    password: str
    plan: PlanTier = PlanTier.FREE


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    email: str
    plan: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrganizationUpdate(BaseModel):
    name: str | None = None
    plan: PlanTier | None = None
    is_active: bool | None = None
