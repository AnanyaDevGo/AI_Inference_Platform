from __future__ import annotations

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse

from app.utils.errors import AppError, RateLimitError

logger = structlog.get_logger(__name__)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert AppError subclasses into standard error envelopes. No stack traces."""
    request_id = getattr(request.state, "request_id", None)

    log_ctx = {
        "error_code": exc.code,
        "status_code": exc.status_code,
        "path": str(request.url.path),
    }

    if exc.status_code >= 500:
        logger.error("app_error", **log_ctx)
    else:
        logger.warning("app_error", **log_ctx)

    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitError):
        headers["Retry-After"] = str(exc.retry_after)
        headers["X-RateLimit-Remaining"] = "0"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            },
        },
        headers=headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unexpected errors. Never exposes stack traces or internal details."""
    request_id = getattr(request.state, "request_id", None)

    logger.exception(
        "unhandled_exception",
        path=str(request.url.path),
        exc_type=type(exc).__name__,
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
                "request_id": request_id,
            },
        },
    )
