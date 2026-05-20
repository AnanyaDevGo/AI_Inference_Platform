#!/bin/sh
set -e

echo "[entrypoint] Starting AI Inference Platform..."

# ── Environment validation ────────────────────────────────────────────────────
# Python config.py does the definitive check — this is a fast pre-flight
for var in SECRET_KEY DATABASE_URL REDIS_URL; do
    eval val=\$$var
    if [ -z "$val" ]; then
        echo "[entrypoint] ERROR: Required environment variable '$var' is not set."
        echo "[entrypoint] Check your .env file or Docker Compose environment config."
        exit 1
    fi
done

# ── Database migrations ───────────────────────────────────────────────────────
VERSIONS_DIR="alembic/versions"
if [ -d "$VERSIONS_DIR" ] && [ "$(ls -A $VERSIONS_DIR 2>/dev/null)" ]; then
    echo "[entrypoint] Running Alembic migrations..."
    alembic upgrade head
    echo "[entrypoint] Migrations complete."
else
    echo "[entrypoint] No migration files found — skipping migrations (add them via 'alembic revision')."
fi

# ── Start application ─────────────────────────────────────────────────────────
echo "[entrypoint] Starting uvicorn..."
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --loop asyncio \
    --no-access-log
