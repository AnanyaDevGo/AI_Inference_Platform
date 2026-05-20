from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import CurrentUser, require_role
from app.models.usage_log import UsageLog

router = APIRouter(prefix="/admin/usage", tags=["admin-usage"])


class UsageSummaryOut(BaseModel):
    total_requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@router.get("/summary", response_model=UsageSummaryOut)
async def get_usage_summary(
    start_date: str | None = Query(None, description="ISO format start date"),
    end_date: str | None = Query(None, description="ISO format end date"),
    org_id: str | None = Query(None, description="Filter by Org ID (platform_admin only)"),
    user: CurrentUser = Depends(require_role("platform_admin", "org_admin", "operator", "viewer")),
    db: AsyncSession = Depends(get_db),
):
    """
    Get token and request usage summary.
    Role gating:
      - platform_admin: can see all orgs, or filter by org_id.
      - org_admin: can see all usage for their org.
      - operator/viewer: can only see their own usage.
    """
    stmt = select(
        func.count(UsageLog.id).label("total_requests"),
        func.sum(UsageLog.prompt_tokens).label("prompt_tokens"),
        func.sum(UsageLog.completion_tokens).label("completion_tokens"),
        func.sum(UsageLog.total_tokens).label("total_tokens"),
    )

    # RBAC logic
    if user.role == "platform_admin":
        if org_id:
            stmt = stmt.where(UsageLog.org_id == uuid.UUID(org_id))
    elif user.role == "org_admin":
        stmt = stmt.where(UsageLog.org_id == uuid.UUID(user.org_id))
    else:
        # operator or viewer
        stmt = stmt.where(UsageLog.user_id == uuid.UUID(user.user_id))

    # Date filtering
    now = datetime.now(timezone.utc)
    # Default to last 30 days if not provided
    dt_start = datetime.fromisoformat(start_date) if start_date else now - timedelta(days=30)
    dt_end = datetime.fromisoformat(end_date) if end_date else now

    stmt = stmt.where(UsageLog.created_at >= dt_start, UsageLog.created_at <= dt_end)

    result = await db.execute(stmt)
    row = result.first()

    if not row or row.total_requests == 0:
        return UsageSummaryOut(
            total_requests=0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )

    return UsageSummaryOut(
        total_requests=row.total_requests or 0,
        prompt_tokens=row.prompt_tokens or 0,
        completion_tokens=row.completion_tokens or 0,
        total_tokens=row.total_tokens or 0,
    )
