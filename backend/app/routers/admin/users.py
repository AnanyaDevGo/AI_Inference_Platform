from __future__ import annotations

import uuid
import structlog

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import CurrentUser, require_role
from app.models.user import User
from app.services.auth_service import hash_password
from app.utils.errors import NotFoundError, ValidationError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


class UserOut(BaseModel):
    id: str
    org_id: str
    name: str
    email: str
    role: str
    is_active: bool

class UserCreate(BaseModel):
    org_id: str
    name: str
    email: str
    password: str
    role: str = "viewer"

class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    is_active: bool | None = None


@router.get("", response_model=list[UserOut])
async def list_users(
    user: CurrentUser = Depends(require_role("platform_admin", "org_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    List users. Platform admin sees all; org_admin sees only their org.
    """
    stmt = select(User).order_by(User.created_at)
    if user.role != "platform_admin":
        stmt = stmt.where(User.org_id == uuid.UUID(user.org_id))

    result = await db.execute(stmt)
    users = result.scalars().all()
    return [
        UserOut(
            id=str(u.id), org_id=str(u.org_id), name=u.name,
            email=u.email, role=u.role, is_active=u.is_active,
        ) for u in users
    ]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    req: UserCreate,
    user: CurrentUser = Depends(require_role("platform_admin", "org_admin")),
    db: AsyncSession = Depends(get_db),
):
    """Create a user. Org admins can only create within their own org."""
    if user.role != "platform_admin" and req.org_id != user.org_id:
        raise ValidationError("Org admins can only create users in their own org")

    try:
        org_uuid = uuid.UUID(req.org_id)
    except ValueError:
        logger.error("invalid_org_id_value", org_id_value=req.org_id)
        raise ValidationError("Invalid Organization ID format")

    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise ValidationError("Email already in use")

    new_user = User(
        org_id=org_uuid,
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
        role=req.role,
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)
    return UserOut(
        id=str(new_user.id), org_id=str(new_user.org_id),
        name=new_user.name, email=new_user.email,
        role=new_user.role, is_active=new_user.is_active,
    )


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    req: UserUpdate,
    user: CurrentUser = Depends(require_role("platform_admin", "org_admin")),
    db: AsyncSession = Depends(get_db),
):
    """Update user role/status. Org admins can only modify users in their org."""
    stmt = select(User).where(User.id == uuid.UUID(user_id))
    if user.role != "platform_admin":
        stmt = stmt.where(User.org_id == uuid.UUID(user.org_id))

    result = await db.execute(stmt)
    target = result.scalar_one_or_none()
    if not target:
        raise NotFoundError("User not found")

    if req.name is not None:
        target.name = req.name
    if req.role is not None:
        target.role = req.role
    if req.is_active is not None:
        target.is_active = req.is_active

    await db.flush()
    await db.refresh(target)
    return UserOut(
        id=str(target.id), org_id=str(target.org_id),
        name=target.name, email=target.email,
        role=target.role, is_active=target.is_active,
    )


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    user: CurrentUser = Depends(require_role("platform_admin", "org_admin")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a user. Org admins can only delete users in their org."""
    stmt = select(User).where(User.id == uuid.UUID(user_id))
    if user.role != "platform_admin":
        stmt = stmt.where(User.org_id == uuid.UUID(user.org_id))

    result = await db.execute(stmt)
    target = result.scalar_one_or_none()
    if not target:
        raise NotFoundError("User not found")

    await db.delete(target)
    await db.flush()
