#!/usr/bin/env python3
"""Seed the SUPER_ADMIN organization.

Run once after adding the `role` and `status` columns to organizations table.
- Creates the SUPER_ADMIN org if it doesn't exist
- Upgrades an existing org to SUPER_ADMIN/APPROVED if email matches

Usage:
    python -m app.seed_admin
    # or inside Docker:
    docker compose exec api python -m app.seed_admin
"""

import asyncio
import os
import sys

# Add parent to path for standalone execution
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bcrypt
from sqlalchemy import select, text

from app.database import async_session_factory, engine, Base
from app.models.organization import Organization
from app.core.constants import OrganizationRole, OrganizationStatus


SUPER_ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL", "cesar.diaz@rockyguard.com")
SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "Admin2026!")
SUPER_ADMIN_NAME = os.getenv("SUPER_ADMIN_NAME", "RockyGuard Technologies")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


async def seed():
    async with engine.begin() as conn:
        # Ensure new columns exist (safe — idempotent with IF NOT EXISTS)
        await conn.execute(text("""
            ALTER TABLE organizations
            ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'USER'
        """))
        await conn.execute(text("""
            ALTER TABLE organizations
            ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        """))

    async with async_session_factory() as db:
        # Check if SUPER_ADMIN already exists by email
        result = await db.execute(
            select(Organization).where(Organization.email == SUPER_ADMIN_EMAIL)
        )
        org = result.scalar_one_or_none()

        if org:
            # Upgrade existing org to SUPER_ADMIN
            org.role = OrganizationRole.SUPER_ADMIN
            org.status = OrganizationStatus.APPROVED
            if not org.password_hash:
                org.password_hash = hash_password(SUPER_ADMIN_PASSWORD)
            await db.commit()
            print(f"✅ Upgraded existing org to SUPER_ADMIN: {org.name} ({org.email})")
        else:
            # Create new SUPER_ADMIN
            org = Organization(
                name=SUPER_ADMIN_NAME,
                email=SUPER_ADMIN_EMAIL,
                plan="ENTERPRISE",
                role=OrganizationRole.SUPER_ADMIN,
                status=OrganizationStatus.APPROVED,
                is_active=True,
                password_hash=hash_password(SUPER_ADMIN_PASSWORD),
            )
            db.add(org)
            await db.commit()
            await db.refresh(org)
            print(f"✅ Created SUPER_ADMIN: {org.name} ({org.email})")

        print(f"   Role: {org.role} | Status: {org.status} | Plan: {org.plan}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
