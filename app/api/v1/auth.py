"""Auth endpoints — login, JWT token management."""

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
from app.database import get_db
from app.models.organization import Organization
from app.models.api_key import ApiKey

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
    """Validate JWT and return the authenticated organization."""
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


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password. Returns JWT bearer token."""
    result = await db.execute(
        select(Organization).where(Organization.email == body.email)
    )
    org = result.scalar_one_or_none()

    if org is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not org.is_active:
        raise HTTPException(status_code=403, detail="Organization is suspended")

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
        },
        expires_in=expires_in,
    )


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
