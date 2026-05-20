from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import CurrentUser, require_role
from app.models.api_key import ApiKey
from app.services.auth_service import generate_api_key
from app.utils.errors import NotFoundError

router = APIRouter(prefix="/admin/api-keys", tags=["admin-api-keys"])


class ApiKeyOut(BaseModel):
    id: str
    org_id: str
    name: str
    key_prefix: str
    is_active: bool
    created_at: str

class ApiKeyCreatedOut(ApiKeyOut):
    """Returned only on creation — contains the plaintext key."""
    plaintext_key: str

class ApiKeyCreate(BaseModel):
    name: str


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    user: CurrentUser = Depends(require_role("platform_admin", "org_admin", "operator")),
    db: AsyncSession = Depends(get_db),
):
    """List API keys for the user's org (or all for platform admin)."""
    stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
    if user.role != "platform_admin":
        stmt = stmt.where(ApiKey.org_id == uuid.UUID(user.org_id))
    if user.role == "operator":
        stmt = stmt.where(ApiKey.created_by_user_id == uuid.UUID(user.user_id))

    result = await db.execute(stmt)
    keys = result.scalars().all()
    return [
        ApiKeyOut(
            id=str(k.id), org_id=str(k.org_id), name=k.name,
            key_prefix=k.key_prefix, is_active=k.is_active,
            created_at=k.created_at.isoformat(),
        ) for k in keys
    ]


@router.post("", response_model=ApiKeyCreatedOut, status_code=201)
async def create_api_key(
    req: ApiKeyCreate,
    user: CurrentUser = Depends(require_role("platform_admin", "org_admin", "operator")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new API key. Returns the plaintext key ONCE.
    Save it — it cannot be retrieved again.
    """
    plaintext, key_hash, prefix = generate_api_key()

    key = ApiKey(
        org_id=uuid.UUID(user.org_id),
        created_by_user_id=uuid.UUID(user.user_id),
        name=req.name,
        key_hash=key_hash,
        key_prefix=prefix,
    )
    db.add(key)
    await db.flush()
    await db.refresh(key)

    return ApiKeyCreatedOut(
        id=str(key.id), org_id=str(key.org_id), name=key.name,
        key_prefix=key.key_prefix, is_active=key.is_active,
        created_at=key.created_at.isoformat(),
        plaintext_key=plaintext,
    )


@router.post("/{key_id}/rotate", response_model=ApiKeyCreatedOut)
async def rotate_api_key(
    key_id: str,
    user: CurrentUser = Depends(require_role("platform_admin", "org_admin", "operator")),
    db: AsyncSession = Depends(get_db),
):
    """Rotate an API key. Replaces the hash immediately and returns the new plaintext key once."""
    stmt = select(ApiKey).where(ApiKey.id == uuid.UUID(key_id))
    if user.role != "platform_admin":
        stmt = stmt.where(ApiKey.org_id == uuid.UUID(user.org_id))
    if user.role == "operator":
        stmt = stmt.where(ApiKey.created_by_user_id == uuid.UUID(user.user_id))

    result = await db.execute(stmt)
    key = result.scalar_one_or_none()
    if not key:
        raise NotFoundError("API key not found")

    plaintext, key_hash, prefix = generate_api_key()
    key.key_hash = key_hash
    key.key_prefix = prefix
    
    await db.flush()
    await db.refresh(key)

    return ApiKeyCreatedOut(
        id=str(key.id), org_id=str(key.org_id), name=key.name,
        key_prefix=key.key_prefix, is_active=key.is_active,
        created_at=key.created_at.isoformat(),
        plaintext_key=plaintext,
    )


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    user: CurrentUser = Depends(require_role("platform_admin", "org_admin", "operator")),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key. Irreversible."""
    stmt = select(ApiKey).where(ApiKey.id == uuid.UUID(key_id))
    if user.role != "platform_admin":
        stmt = stmt.where(ApiKey.org_id == uuid.UUID(user.org_id))
    if user.role == "operator":
        stmt = stmt.where(ApiKey.created_by_user_id == uuid.UUID(user.user_id))

    result = await db.execute(stmt)
    key = result.scalar_one_or_none()
    if not key:
        raise NotFoundError("API key not found")

    key.is_active = False
    await db.flush()
