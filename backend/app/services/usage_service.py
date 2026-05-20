from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_log import UsageLog

logger = structlog.get_logger(__name__)


async def log_usage(
    db: AsyncSession,
    *,
    org_id: str,
    user_id: str | None = None,
    api_key_id: str | None = None,
    model_name: str,
    request_id: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: int = 0,
    ttft_ms: int | None = None,
    status: str = "success",
    error_code: str | None = None,
) -> None:
    """Insert a row into usage_logs. Never raises — logs errors internally."""
    try:
        log_entry = UsageLog(
            org_id=uuid.UUID(org_id),
            user_id=uuid.UUID(user_id) if user_id else None,
            api_key_id=uuid.UUID(api_key_id) if api_key_id else None,
            model_name=model_name,
            request_id=request_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            duration_ms=duration_ms,
            ttft_ms=ttft_ms,
            status=status,
            error_code=error_code,
        )
        db.add(log_entry)
        await db.flush()
    except Exception:
        logger.exception(
            "usage_log_write_failed",
            org_id=org_id,
            model_name=model_name,
            request_id=request_id,
        )
