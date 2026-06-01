"""Organization model with tier/plan and role support."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="FREE")
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="USER",
        server_default="USER",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING",
        server_default="PENDING",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="organization", cascade="all, delete-orphan"
    )
    extraction_logs: Mapped[list["ExtractionLog"]] = relationship(
        "ExtractionLog", back_populates="organization", cascade="all, delete-orphan"
    )
    monthly_quotas: Mapped[list["MonthlyQuota"]] = relationship(
        "MonthlyQuota", back_populates="organization", cascade="all, delete-orphan"
    )
