"""Organization schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.core.constants import OrganizationStatus, PlanTier, OrganizationRole


class OrganizationRegisterRequest(BaseModel):
    """Public registration — no auth required. Creates PENDING org for admin review."""
    name: str
    email: str
    password: str
    plan: PlanTier = PlanTier.FREE


class OrganizationRegisterResponse(BaseModel):
    """Returned after registration — PENDING approval."""
    id: UUID
    name: str
    email: str
    plan: str
    status: str
    message: str

    model_config = {"from_attributes": True}


class OrganizationCreate(BaseModel):
    """Admin-only: direct creation with role assignment (SUPER_ADMIN only)."""
    name: str
    email: str
    password: str
    plan: PlanTier = PlanTier.FREE
    role: OrganizationRole = OrganizationRole.USER
    status: OrganizationStatus = OrganizationStatus.APPROVED


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    email: str
    plan: str
    role: str
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrganizationUpdate(BaseModel):
    name: str | None = None
    plan: PlanTier | None = None
    role: OrganizationRole | None = None
    status: OrganizationStatus | None = None
    is_active: bool | None = None


class OrganizationApproval(BaseModel):
    """Approve (status=APPROVED) or reject (status=REJECTED) a pending org."""
    status: OrganizationStatus  # APPROVED or REJECTED


class OrganizationListItem(BaseModel):
    """Abbreviated org info for admin listing."""
    id: UUID
    name: str
    email: str
    plan: str
    role: str
    status: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
