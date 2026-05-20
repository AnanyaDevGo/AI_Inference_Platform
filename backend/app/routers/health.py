from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.services.inference_service import check_ollama_health
from app.services.rate_limit_service import _get_redis

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["platform"])


@router.get("/health/liveness", summary="Platform liveness check")
async def liveness() -> JSONResponse:
    """Simple ping to verify the API process is running."""
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.get("/health/readiness", summary="Platform readiness check")
@router.get("/health", summary="Platform readiness check (alias)", include_in_schema=False)
async def readiness(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Returns 200 if all dependencies (DB, Redis, Ollama) are reachable.
    Returns 503 if any are degraded.
    """
    settings = get_settings()
    checks: dict[str, str] = {}
    is_healthy = True

    # 1. Check Ollama
    ollama_ok = await check_ollama_health()
    checks["ollama"] = "reachable" if ollama_ok else "unreachable"
    if not ollama_ok:
        is_healthy = False

    # 2. Check Database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "reachable"
    except Exception as e:
        logger.error("health_db_ping_failed", error=str(e))
        checks["database"] = "unreachable"
        is_healthy = False

    # 3. Check Redis
    try:
        redis_client = await _get_redis()
        await redis_client.ping()
        checks["redis"] = "reachable"
    except Exception as e:
        logger.error("health_redis_ping_failed", error=str(e))
        checks["redis"] = "unreachable"
        is_healthy = False

    status_code = 200 if is_healthy else 503

    if not is_healthy:
        logger.warning("health_check_degraded", checks=checks)

    return JSONResponse(
        status_code=status_code,
        content={
            "success": is_healthy,
            "data": {
                "status": "ok" if is_healthy else "degraded",
                "version": settings.APP_VERSION,
                **checks,
            },
        },
    )
