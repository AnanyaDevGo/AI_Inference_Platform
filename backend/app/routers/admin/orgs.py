from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import CurrentUser, require_role
from app.models.org import Org
from app.utils.errors import NotFoundError, ValidationError

router = APIRouter(prefix="/admin/orgs", tags=["admin-orgs"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    rate_limit_rpm: int
    rate_limit_burst: int
    is_active: bool

class OrgCreate(BaseModel):
    name: str
    slug: str
    rate_limit_rpm: int = 60
    rate_limit_burst: int = 10

class OrgUpdate(BaseModel):
    name: str | None = None
    rate_limit_rpm: int | None = None
    rate_limit_burst: int | None = None
    is_active: bool | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[OrgOut])
async def list_orgs(
    user: CurrentUser = Depends(require_role("platform_admin")),
    db: AsyncSession = Depends(get_db),
):
    """List all orgs. Platform admin only."""
    result = await db.execute(select(Org).order_by(Org.created_at))
    orgs = result.scalars().all()
    return [
        OrgOut(
            id=str(o.id), name=o.name, slug=o.slug,
            rate_limit_rpm=o.rate_limit_rpm, rate_limit_burst=o.rate_limit_burst,
            is_active=o.is_active,
        ) for o in orgs
    ]


@router.post("", response_model=OrgOut, status_code=201)
async def create_org(
    req: OrgCreate,
    user: CurrentUser = Depends(require_role("platform_admin")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new org. Platform admin only."""
    existing = await db.execute(select(Org).where(Org.slug == req.slug))
    if existing.scalar_one_or_none():
        raise ValidationError(f"Org with slug '{req.slug}' already exists")

    org = Org(
        name=req.name, slug=req.slug,
        rate_limit_rpm=req.rate_limit_rpm, rate_limit_burst=req.rate_limit_burst,
    )
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return OrgOut(
        id=str(org.id), name=org.name, slug=org.slug,
        rate_limit_rpm=org.rate_limit_rpm, rate_limit_burst=org.rate_limit_burst,
        is_active=org.is_active,
    )


@router.patch("/{org_id}", response_model=OrgOut)
async def update_org(
    org_id: str,
    req: OrgUpdate,
    user: CurrentUser = Depends(require_role("platform_admin")),
    db: AsyncSession = Depends(get_db),
):
    """Update org settings. Platform admin only."""
    result = await db.execute(select(Org).where(Org.id == uuid.UUID(org_id)))
    org = result.scalar_one_or_none()
    if not org:
        raise NotFoundError("Org not found")

    if req.name is not None:
        org.name = req.name
    if req.rate_limit_rpm is not None:
        org.rate_limit_rpm = req.rate_limit_rpm
    if req.rate_limit_burst is not None:
        org.rate_limit_burst = req.rate_limit_burst
    if req.is_active is not None:
        org.is_active = req.is_active

    await db.flush()
    await db.refresh(org)
    return OrgOut(
        id=str(org.id), name=org.name, slug=org.slug,
        rate_limit_rpm=org.rate_limit_rpm, rate_limit_burst=org.rate_limit_burst,
        is_active=org.is_active,
    )


@router.delete("/{org_id}", status_code=204)
async def delete_org(
    org_id: str,
    user: CurrentUser = Depends(require_role("platform_admin")),
    db: AsyncSession = Depends(get_db),
):
    """Delete an organization. Platform admin only."""
    result = await db.execute(select(Org).where(Org.id == uuid.UUID(org_id)))
    org = result.scalar_one_or_none()
    if not org:
        raise NotFoundError("Org not found")
    
    await db.delete(org)
    await db.flush()
