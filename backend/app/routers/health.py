from __future__ import annotations

import time
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.database import get_engine
from app.services.inference_service import check_ollama_health
from app.services.rate_limit_service import _get_redis

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["platform"])


@router.get("/health/liveness", summary="Platform liveness check")
@router.get("/health/live", summary="Platform liveness check (alias)", include_in_schema=False)
async def liveness() -> JSONResponse:
    """Simple ping to verify the API process is running."""
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.get("/health/readiness", summary="Platform readiness check")
@router.get("/health/ready", summary="Platform readiness check (alias)", include_in_schema=False)
@router.get("/health", summary="Platform readiness check (alias)", include_in_schema=False)
async def readiness() -> JSONResponse:
    """
    Returns 200 if all dependencies (DB, Redis, Ollama) are reachable.
    Returns 503 if any are degraded.
    Uses a direct engine connection to avoid PendingRollbackError pool contamination.
    """
    settings = get_settings()
    checks: dict[str, str] = {}
    is_healthy = True

    # 1. Check Ollama
    ollama_ok = await check_ollama_health()
    checks["ollama"] = "reachable" if ollama_ok else "unreachable"
    if not ollama_ok:
        is_healthy = False

    # 2. Check Database — use engine.connect() directly to avoid session pool conflicts
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
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


@router.get("/health/diagnostics", summary="API connectivity diagnostics")
async def diagnostics(request: Request) -> JSONResponse:
    """
    Detailed check of API headers, database query latency, Redis ping latency,
    Ollama response latency, and CORS origin settings for troubleshooting.
    Uses direct engine connection to avoid pool interference.
    """
    settings = get_settings()
    
    # 1. Collect request headers to verify proxy headers (e.g. X-Forwarded-For)
    req_headers = {k: v for k, v in request.headers.items() if k.lower() in [
        "host", "origin", "referer", "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host", "user-agent"
    ]}

    # 2. Database latency check
    db_latency_ms = None
    try:
        engine = get_engine()
        t0 = time.perf_counter()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    except Exception as e:
        logger.error("diagnostics_db_ping_failed", error=str(e))

    # 3. Redis latency check
    redis_latency_ms = None
    try:
        t0 = time.perf_counter()
        redis_client = await _get_redis()
        await redis_client.ping()
        redis_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    except Exception as e:
        logger.error("diagnostics_redis_ping_failed", error=str(e))

    # 4. Ollama latency check
    ollama_latency_ms = None
    ollama_ok = False
    try:
        t0 = time.perf_counter()
        ollama_ok = await check_ollama_health()
        ollama_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    except Exception as e:
        logger.error("diagnostics_ollama_ping_failed", error=str(e))

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "diagnostics": {
                "app_name": settings.APP_NAME,
                "app_version": settings.APP_VERSION,
                "debug_mode": settings.DEBUG,
                "allowed_cors_origins": settings.ALLOWED_ORIGINS,
                "cookie_secure": settings.COOKIE_SECURE,
                "cookie_samesite": settings.COOKIE_SAMESITE,
                "request_headers": req_headers,
                "services": {
                    "database": {"status": "reachable" if db_latency_ms is not None else "unreachable", "latency_ms": db_latency_ms},
                    "redis": {"status": "reachable" if redis_latency_ms is not None else "unreachable", "latency_ms": redis_latency_ms},
                    "ollama": {"status": "reachable" if ollama_ok else "unreachable", "latency_ms": ollama_latency_ms},
                }
            }
        }
    )
