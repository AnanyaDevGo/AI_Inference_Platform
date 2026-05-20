from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import structlog
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.api_key import ApiKey
from app.models.org import Org
from app.models.user import User
from app.utils.errors import InvalidCredentialsError, UnauthorizedError

logger = structlog.get_logger(__name__)


# ── Password hashing ────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ──────────────────────────────────────────────────────────────────────


def create_access_token(user: User) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        seconds=settings.ACCESS_TOKEN_TTL_SECONDS
    )
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "org_id": str(user.org_id),
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(user: User) -> tuple[str, str]:
    """Generate a new refresh token and return a tuple of (token_string, jti)."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        seconds=settings.REFRESH_TOKEN_TTL_SECONDS
    )
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(user.id),
        "jti": jti,
        "type": "refresh",
        "exp": expire,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return token, jti


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")


def create_verification_token(payload_data: dict) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {
        **payload_data,
        "purpose": "google_registration",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def create_reset_token(email: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {
        "email": email,
        "purpose": "password_reset",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


# ── Refresh Token Rotation via Redis ─────────────────────────────────────────

async def store_active_refresh_token(user_id: str, jti: str, expires_in: int) -> None:
    from app.services.otp_service import get_redis_client
    r = await get_redis_client()
    key = f"refresh_token:{user_id}:{jti}"
    await r.setex(key, expires_in, "active")


async def revoke_refresh_token(user_id: str, jti: str) -> None:
    from app.services.otp_service import get_redis_client
    r = await get_redis_client()
    key = f"refresh_token:{user_id}:{jti}"
    await r.delete(key)


async def is_refresh_token_valid(user_id: str, jti: str) -> bool:
    from app.services.otp_service import get_redis_client
    r = await get_redis_client()
    key = f"refresh_token:{user_id}:{jti}"
    val = await r.get(key)
    return val == "active"


async def revoke_all_user_refresh_tokens(user_id: str) -> None:
    from app.services.otp_service import get_redis_client
    r = await get_redis_client()
    pattern = f"refresh_token:{user_id}:*"
    keys = await r.keys(pattern)
    if keys:
        await r.delete(*keys)


# ── User lookup ──────────────────────────────────────────────────────────────


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    if not user.is_active:
        raise UnauthorizedError("Account is deactivated")
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


# ── Org helpers ──────────────────────────────────────────────────────────────


async def get_or_create_default_org(db: AsyncSession) -> Org:
    """Get the 'default' org or create it if it doesn't exist."""
    result = await db.execute(select(Org).where(Org.slug == "default"))
    org = result.scalar_one_or_none()
    if org:
        return org

    org = Org(name="Default", slug="default")
    db.add(org)
    await db.flush()
    await db.refresh(org)
    logger.info("default_org_created", org_id=str(org.id))
    return org


import re

async def get_or_create_custom_org(db: AsyncSession, org_name: str) -> tuple[Org, bool]:
    """Get a custom org by name, or create it. Returns (Org, is_new)."""
    # Simple slugification
    slug = re.sub(r'[^a-z0-9]+', '-', org_name.lower()).strip('-')
    if not slug:
        slug = f"org-{uuid.uuid4().hex[:8]}"

    # Check by slug
    result = await db.execute(select(Org).where(Org.slug == slug))
    org = result.scalar_one_or_none()
    if org:
        return org, False

    # Create new org
    org = Org(name=org_name, slug=slug)
    db.add(org)
    await db.flush()
    await db.refresh(org)
    logger.info("custom_org_created", org_id=str(org.id), name=org_name)
    return org, True


async def count_users(db: AsyncSession) -> int:
    """Count total users — used to determine if first user should be admin."""
    from sqlalchemy import func
    result = await db.execute(select(func.count(User.id)))
    return result.scalar() or 0


# ── API Key helpers ──────────────────────────────────────────────────────────


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (plaintext, sha256_hash, prefix)."""
    raw = f"sk-{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:8]
    return raw, key_hash, prefix


async def lookup_api_key(db: AsyncSession, raw_key: str) -> ApiKey | None:
    """Look up an API key by SHA-256 hash. Returns None if not found or revoked."""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        return None
    # Check expiry
    if key.expires_at and key.expires_at < datetime.now(timezone.utc):
        return None
    # Update last_used_at
    key.last_used_at = datetime.now(timezone.utc)
    return key
