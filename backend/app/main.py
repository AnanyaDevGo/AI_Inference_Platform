from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_settings
from app.middleware.correlation import CorrelationMiddleware
from app.middleware.error_handler import app_error_handler, unhandled_error_handler
from app.middleware.logging import LoggingMiddleware
from app.observability.logging import configure_logging
from app.routers import auth, conversations, health, inference
from app.routers.admin import orgs as admin_orgs, users as admin_users, api_keys as admin_api_keys, usage as admin_usage
from app.utils.errors import AppError
from app.services.inference_service import check_ollama_health
from app.database import Base, get_engine
import app.models.org  # noqa: F401
import app.models.user  # noqa: F401
import app.models.api_key  # noqa: F401
import app.models.usage_log  # noqa: F401
import app.models.conversation  # noqa: F401
import app.models.otp  # noqa: F401

configure_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    logger.info(
        "platform_starting",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        ollama_url=settings.OLLAMA_BASE_URL,
    )

    # Create DB tables if they don't exist
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_ready")

    # Validate Ollama connectivity (non-fatal warning — Ollama may start later)
    if await check_ollama_health():
        logger.info("ollama_connected", url=settings.OLLAMA_BASE_URL)
    else:
        logger.warning(
            "ollama_unreachable",
            url=settings.OLLAMA_BASE_URL,
            note="Inference requests will fail until Ollama is reachable",
        )

    yield

    logger.info("platform_shutdown_initiated")
    
    from app.services.inference_service import get_active_inferences
    import asyncio
    
    # Wait for active inference requests to finish before closing
    while True:
        active = get_active_inferences()
        if active == 0:
            break
        logger.info("waiting_for_active_inferences", count=active)
        await asyncio.sleep(1.0)
        
    logger.info("platform_shutdown_complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="CPU-native AI inference serving platform with OpenAI-compatible API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost executes first) ────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(CorrelationMiddleware)

    # ── Exception handlers ───────────────────────────────────────────────────
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    # ── Prometheus instrumentation ───────────────────────────────────────────
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    # ── Routers ──────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(inference.router)
    app.include_router(auth.router)
    app.include_router(conversations.router)
    app.include_router(admin_orgs.router)
    app.include_router(admin_users.router)
    app.include_router(admin_api_keys.router)
    app.include_router(admin_usage.router)

    return app


app = create_app()
