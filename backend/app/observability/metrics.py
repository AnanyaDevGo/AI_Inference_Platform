from __future__ import annotations

import asyncio
from prometheus_client import Counter, Gauge, Histogram

# ── HTTP metrics (supplementing prometheus-fastapi-instrumentator) ──────────

HTTP_REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Number of HTTP requests currently being processed",
)

# ── Inference metrics ───────────────────────────────────────────────────────

INFERENCE_REQUESTS_TOTAL = Counter(
    "inference_requests_total",
    "Total number of inference requests",
    ["org_id", "model", "status"],
)

INFERENCE_DURATION_SECONDS = Histogram(
    "inference_duration_seconds",
    "Wall-clock duration of inference requests in seconds",
    ["org_id", "model"],
    # CPU inference is slow — buckets tuned accordingly
    buckets=[1, 5, 10, 20, 30, 45, 60, 90, 120, float("inf")],
)

INFERENCE_TTFT_SECONDS = Histogram(
    "inference_ttft_seconds",
    "Time to first token for streaming inference requests in seconds",
    ["org_id", "model"],
    buckets=[0.5, 1, 2, 5, 10, 15, 20, 30, 45, float("inf")],
)

INFERENCE_TOKENS_TOTAL = Counter(
    "inference_tokens_total",
    "Total tokens processed",
    ["org_id", "model", "token_type"],  # token_type: prompt | completion
)

INFERENCE_CONCURRENT_REQUESTS = Gauge(
    "inference_concurrent_requests",
    "Number of concurrent inference requests",
    ["model"],
)

INFERENCE_QUEUE_LENGTH = Gauge(
    "inference_queue_length",
    "Number of inference requests currently waiting in queue",
    ["model"],
)

# ── Rate limiting metrics ───────────────────────────────────────────────────

RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "rate_limit_rejections_total",
    "Total number of requests rejected by rate limiter",
    ["org_id"],
)

# ── Auth metrics ────────────────────────────────────────────────────────────

AUTH_FAILURES_TOTAL = Counter(
    "auth_failures_total",
    "Total authentication failures",
    ["reason"],  # reason: invalid_credentials | token_expired | invalid_key | revoked_key
)

USER_REGISTRATIONS_TOTAL = Counter(
    "user_registrations_total",
    "Total user signups",
)

USER_LOGINS_TOTAL = Counter(
    "user_logins_total",
    "Total user login attempts",
    ["status"],  # status: success | failure
)

# ── Email metrics ───────────────────────────────────────────────────────────

EMAILS_SENT_TOTAL = Counter(
    "emails_sent_total",
    "Total emails sent",
    ["status", "purpose"],  # status: success | failure, purpose: otp_verification | password_reset
)

# ── Dependency availability metrics ─────────────────────────────────────────

DB_UP = Gauge(
    "db_up",
    "PostgreSQL availability status (1 = UP, 0 = DOWN)",
)

REDIS_UP = Gauge(
    "redis_up",
    "Redis availability status (1 = UP, 0 = DOWN)",
)

OLLAMA_UP = Gauge(
    "ollama_up",
    "Ollama availability status (1 = UP, 0 = DOWN)",
)

OLLAMA_MODEL_STATUS = Gauge(
    "ollama_model_status",
    "Model loaded status in Ollama (1 = loaded, 0 = not loaded)",
    ["model"],
)

ACTIVE_MODELS_COUNT = Gauge(
    "active_models_count",
    "Number of models currently loaded in Ollama",
)

# ── Database connection pool metrics ────────────────────────────────────────

DB_POOL_SIZE = Gauge(
    "db_pool_size",
    "Configured database connection pool size",
)

DB_POOL_CHECKED_OUT = Gauge(
    "db_pool_checked_out",
    "Number of database connections checked out from the pool",
)

DB_POOL_OVERFLOW = Gauge(
    "db_pool_overflow",
    "Number of overflow database connections",
)

# ── Redis memory metrics ───────────────────────────────────────────────────

REDIS_MEMORY_USED = Gauge(
    "redis_memory_used_bytes",
    "Redis memory usage in bytes",
)

REDIS_KEYSPACE_HITS = Gauge(
    "redis_keyspace_hits_total",
    "Total number of successful keyspace lookups in Redis",
)

REDIS_KEYSPACE_MISSES = Gauge(
    "redis_keyspace_misses_total",
    "Total number of failed keyspace lookups in Redis",
)

# ── App & User Analytics periodic metrics ───────────────────────────────────

TOTAL_REGISTERED_USERS = Gauge(
    "total_registered_users",
    "Total number of registered users on the platform",
)

ACTIVE_USERS_LAST_15M = Gauge(
    "active_users_last_15m",
    "Number of active users in the last 15 minutes",
)

DAILY_ACTIVE_USERS = Gauge(
    "daily_active_users",
    "Number of daily active users (last 24 hours)",
)

TOTAL_CHATS_CREATED = Gauge(
    "total_chats_created",
    "Total number of chat conversations created",
)

RESPONSE_SIZE_BYTES = Histogram(
    "response_size_bytes",
    "Size of responses generated in bytes",
    ["handler"],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, float("inf")],
)

TENANT_CHAT_COUNT = Gauge(
    "tenant_chat_count",
    "Total chats created per tenant",
    ["org_id"],
)

TENANT_INFERENCE_COUNT = Gauge(
    "tenant_inference_count",
    "Total inference requests per tenant",
    ["org_id"],
)

TENANT_TOKEN_COUNT = Gauge(
    "tenant_token_count",
    "Total tokens consumed per tenant",
    ["org_id"],
)


# ── Periodic metrics collection loop ────────────────────────────────────────

async def collect_periodic_metrics():
    """Background task that runs periodically to gather system, database, and model metrics."""
    import structlog
    from app.database import get_engine, get_session_factory
    from sqlalchemy import text
    from datetime import datetime, timedelta, timezone

    logger = structlog.get_logger(__name__)
    engine = get_engine()
    session_factory = get_session_factory()

    logger.info("periodic_metrics_collection_loop_starting")

    # Prevent circular import
    from app.services.inference_service import list_ollama_models

    while True:
        try:
            # 1. DB pool statistics
            try:
                pool = engine.sync_engine.pool
                DB_POOL_SIZE.set(pool.size())
                DB_POOL_CHECKED_OUT.set(pool.checkedout())
                DB_POOL_OVERFLOW.set(pool.overflow())
            except Exception as e:
                logger.warning("failed_to_collect_db_pool_metrics", error=str(e))

            # 2. Database availability and transactional counts
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                DB_UP.set(1)
            except Exception:
                DB_UP.set(0)

            # 3. Database user/chat analytics
            try:
                async with session_factory() as session:
                    # Registered users
                    res = await session.execute(text("SELECT count(*) FROM users"))
                    TOTAL_REGISTERED_USERS.set(res.scalar() or 0)

                    # Active users last 15m
                    now = datetime.now(timezone.utc)
                    cutoff_15m = now - timedelta(minutes=15)
                    res = await session.execute(
                        text("SELECT count(distinct id) FROM users WHERE last_login_at >= :cutoff"),
                        {"cutoff": cutoff_15m}
                    )
                    ACTIVE_USERS_LAST_15M.set(res.scalar() or 0)

                    # Daily active users last 24h
                    cutoff_24h = now - timedelta(days=1)
                    res = await session.execute(
                        text("SELECT count(distinct id) FROM users WHERE last_login_at >= :cutoff"),
                        {"cutoff": cutoff_24h}
                    )
                    DAILY_ACTIVE_USERS.set(res.scalar() or 0)

                    # Chats count
                    res = await session.execute(text("SELECT count(*) FROM conversations"))
                    TOTAL_CHATS_CREATED.set(res.scalar() or 0)

                    # Tenant-wise chats
                    res = await session.execute(
                        text("SELECT users.org_id, count(*) FROM conversations JOIN users ON conversations.user_id = users.id GROUP BY users.org_id")
                    )
                    for row in res.all():
                        TENANT_CHAT_COUNT.labels(org_id=str(row[0])).set(row[1])

                    # Tenant-wise inference and tokens
                    res = await session.execute(
                        text("SELECT org_id, count(*), sum(total_tokens) FROM usage_logs GROUP BY org_id")
                    )
                    for row in res.all():
                        org_id = str(row[0])
                        TENANT_INFERENCE_COUNT.labels(org_id=org_id).set(row[1])
                        toks = row[2] or 0
                        TENANT_TOKEN_COUNT.labels(org_id=org_id).set(toks)

            except Exception as e:
                logger.warning("failed_to_collect_db_user_analytics", error=str(e))

            # 4. Redis metrics
            try:
                from app.services.rate_limit_service import _get_redis
                redis_client = await _get_redis()
                await redis_client.ping()
                REDIS_UP.set(1)

                mem_info = await redis_client.info(section="memory")
                used_memory = int(mem_info.get("used_memory", 0))
                REDIS_MEMORY_USED.set(used_memory)

                stats_info = await redis_client.info(section="stats")
                REDIS_KEYSPACE_HITS.set(int(stats_info.get("keyspace_hits", 0)))
                REDIS_KEYSPACE_MISSES.set(int(stats_info.get("keyspace_misses", 0)))
            except Exception as e:
                REDIS_UP.set(0)
                logger.warning("failed_to_collect_redis_metrics", error=str(e))

            # 5. Ollama models metrics
            try:
                models = await list_ollama_models()
                OLLAMA_UP.set(1)
                ACTIVE_MODELS_COUNT.set(len(models))

                loaded_models = {m.get("name", "") for m in models}
                for model_name in ["gemma2:2b", "llama3.2"]:
                    is_loaded = any(model_name in name for name in loaded_models)
                    OLLAMA_MODEL_STATUS.labels(model=model_name).set(1 if is_loaded else 0)
            except Exception as e:
                OLLAMA_UP.set(0)
                ACTIVE_MODELS_COUNT.set(0)
                for model_name in ["gemma2:2b", "llama3.2"]:
                    OLLAMA_MODEL_STATUS.labels(model=model_name).set(0)
                logger.warning("failed_to_collect_ollama_metrics", error=str(e))

        except Exception as exc:
            logger.exception("unhandled_error_in_metrics_collector", error=str(exc))

        await asyncio.sleep(30)
