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


async def pull_default_models():
    import asyncio
    from app.config import get_settings
    from app.services.inference_service import check_ollama_health, _get_client
    
    settings = get_settings()
    if settings.INFERENCE_ENGINE == "openai_compatible":
        logger.info("skipping_model_pull_for_openai_compatible_engine")
        return
    logger.info("checking_ollama_ready_to_pull_models")
    # Wait for Ollama up to 60s
    for i in range(12):
        if await check_ollama_health():
            break
        await asyncio.sleep(5)
    else:
        logger.error("ollama_unreachable_during_model_pull")
        return

    models_to_pull = ["gemma2:2b", "llama3.2"]
    async with _get_client() as client:
        try:
            resp = await client.get("/api/tags", timeout=5.0)
            existing_names = []
            if resp.status_code == 200:
                existing_names = [m.get("name") for m in resp.json().get("models", [])]
        except Exception as e:
            logger.warning("failed_to_fetch_existing_models", error=str(e))
            existing_names = []

        for m_name in models_to_pull:
            match_found = False
            for existing in existing_names:
                if existing.startswith(m_name) or m_name in existing:
                    match_found = True
                    break

            if match_found:
                logger.info("model_already_exists", model=m_name)
                continue

            logger.info("pulling_model_started", model=m_name)
            try:
                pull_resp = await client.post("/api/pull", json={"name": m_name, "stream": False}, timeout=600.0)
                if pull_resp.status_code == 200:
                    logger.info("pulling_model_success", model=m_name)
                else:
                    logger.error("pulling_model_failed", model=m_name, status=pull_resp.status_code, body=pull_resp.text)
            except Exception as e:
                logger.exception("pulling_model_failed_exception", model=m_name, error=str(e))


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
    
    # Self-healing migration for otps table
    from sqlalchemy import text
    schema_ok = False
    async with engine.connect() as conn:
        try:
            # Try to query the new 'purpose' column
            res = await conn.execute(text("SELECT purpose FROM otps LIMIT 1"))
            await res.all()
            schema_ok = True
        except Exception:
            pass

    if not schema_ok:
        logger.info("otps_table_has_outdated_schema_or_does_not_exist_dropping_if_exists")
        async with engine.begin() as conn:
            try:
                await conn.execute(text("DROP TABLE IF EXISTS otps CASCADE"))
            except Exception as e:
                logger.error("failed_to_drop_old_otps_table", error=str(e))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_ready")

    # Seed Super Admin
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as db:
        try:
            from app.services.auth_service import get_or_create_default_org, get_user_by_email, hash_password
            from app.models.user import User
            
            existing_admin = await get_user_by_email(db, settings.SUPER_ADMIN_EMAIL)
            if not existing_admin:
                org = await get_or_create_default_org(db)
                admin_user = User(
                    org_id=org.id,
                    name="Super Admin",
                    email=settings.SUPER_ADMIN_EMAIL,
                    password_hash=hash_password(settings.SUPER_ADMIN_PASSWORD),
                    role="platform_admin",
                    auth_provider="local",
                    is_active=True,
                    is_verified=True,
                    password_set=True,
                )
                db.add(admin_user)
                await db.commit()
                logger.info("super_admin_seeded", email=settings.SUPER_ADMIN_EMAIL)
        except Exception as e:
            logger.error("super_admin_seeding_failed", error=str(e))

    # Validate Redis connectivity (critical dependency)
    try:
        from app.services.otp_service import get_redis_client
        redis_client = await get_redis_client()
        await redis_client.ping()
        logger.info("redis_connected", url=settings.REDIS_URL)
    except Exception as e:
        logger.error("redis_connection_failed", url=settings.REDIS_URL, error=str(e))
        raise e

    # Validate inference engine connectivity (non-fatal warning — engine may start later)
    engine_url = settings.INFERENCE_ENGINE_URL if settings.INFERENCE_ENGINE == "openai_compatible" else settings.OLLAMA_BASE_URL
    if await check_ollama_health():
        logger.info("inference_engine_connected", engine=settings.INFERENCE_ENGINE, url=engine_url)
    else:
        logger.warning(
            "inference_engine_unreachable",
            engine=settings.INFERENCE_ENGINE,
            url=engine_url,
            note=f"Inference requests will fail until {settings.INFERENCE_ENGINE} is reachable",
        )

    import asyncio
    asyncio.create_task(pull_default_models())

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
