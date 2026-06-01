"""Auth endpoints — login, registration, JWT token management."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.constants import OrganizationRole, OrganizationStatus
from app.database import get_db
from app.models.organization import Organization
from app.models.api_key import ApiKey
from app.schemas.organization import (
    OrganizationRegisterRequest,
    OrganizationRegisterResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

settings = get_settings()

# JWT config
JWT_SECRET = settings.secret_key
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

bearer_scheme = HTTPBearer(auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    organization: dict
    expires_in: int


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Validate JWT and return the authenticated organization.

    Rejects organizations with PENDING or REJECTED status.
    """
    credentials_exception = HTTPException(
        status_code=401,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise credentials_exception

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
        org_id: str = payload.get("sub")
        if org_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    if org is None or not org.is_active:
        raise credentials_exception

    # Block PENDING/REJECTED orgs from authenticated operations
    if org.status in (OrganizationStatus.PENDING, OrganizationStatus.REJECTED):
        raise HTTPException(
            status_code=403,
            detail=f"Organization is {org.status}. Contact your platform administrator.",
        )

    return org


async def get_current_superadmin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Validate JWT and ensure the user is a SUPER_ADMIN."""
    org = await get_current_user(credentials=credentials, db=db)
    if org.role != OrganizationRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="SUPER_ADMIN role required",
        )
    return org


def create_access_token(org_id: str) -> tuple[str, int]:
    """Create a JWT access token. Returns (token, expires_in_seconds)."""
    expires_in = JWT_EXPIRY_HOURS * 3600
    expire = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    payload = {
        "sub": org_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": uuid4().hex,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expires_in


# ────────────────────────── Registration (public) ──────────────────────────


@router.post("/register", response_model=OrganizationRegisterResponse, status_code=201)
async def register_organization(
    body: OrganizationRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new organization (public, no auth).

    All registrations are created with PENDING status.
    A SUPER_ADMIN must approve the organization before login is allowed.
    """
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
        role=OrganizationRole.USER,
        status=OrganizationStatus.PENDING,
        is_active=True,
        password_hash=hash_password(body.password),
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)

    return OrganizationRegisterResponse(
        id=org.id,
        name=org.name,
        email=org.email,
        plan=org.plan,
        status=org.status,
        message="Registration received. Awaiting platform administrator approval.",
    )


# ────────────────────────── Login ──────────────────────────


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password. Returns JWT bearer token.

    Only APPROVED organizations can log in.
    """
    result = await db.execute(
        select(Organization).where(Organization.email == body.email)
    )
    org = result.scalar_one_or_none()

    if org is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not org.is_active:
        raise HTTPException(status_code=403, detail="Organization is suspended")

    if org.status == OrganizationStatus.PENDING:
        raise HTTPException(
            status_code=403,
            detail="Registration pending approval. A platform administrator must approve your organization first.",
        )
    if org.status == OrganizationStatus.REJECTED:
        raise HTTPException(
            status_code=403,
            detail="Registration was rejected. Contact your platform administrator.",
        )

    if not org.password_hash:
        raise HTTPException(status_code=401, detail="No password set. Contact administrator.")

    if not verify_password(body.password, org.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token, expires_in = create_access_token(str(org.id))

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        organization={
            "id": str(org.id),
            "name": org.name,
            "email": org.email,
            "plan": org.plan,
            "role": org.role,
        },
        expires_in=expires_in,
    )


# ────────────────────────── Me ──────────────────────────


@router.get("/me")
async def get_me(
    org: Organization = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated organization info with API keys."""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.organization_id == org.id,
            ApiKey.is_active == True,
        )
    )
    keys = result.scalars().all()

    return {
        "organization": {
            "id": str(org.id),
            "name": org.name,
            "email": org.email,
            "plan": org.plan,
            "role": org.role,
            "status": org.status,
            "is_active": org.is_active,
            "created_at": org.created_at.isoformat() if org.created_at else None,
        },
        "api_keys": [
            {
                "id": str(k.id),
                "key_prefix": k.key_prefix,
                "scopes": k.scopes,
                "is_live": k.is_live,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            }
            for k in keys
        ],
    }
