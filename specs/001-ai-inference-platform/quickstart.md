# Quickstart: AI Inference Platform

**Phase 1 output** | Feature: `001-ai-inference-platform`

Get the platform running on a developer laptop in under 10 minutes.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker Desktop | 24+ | With Docker Compose v2 |
| Ollama | Latest | Installed natively — NOT in Docker |
| Python | 3.11+ | For local backend dev (optional) |
| Node | 20 LTS | For local frontend dev (optional) |
| RAM | 8 GB+ | 6 GB free recommended for Ollama |

---

## Step 1 — Install & Start Ollama

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows: download installer from https://ollama.com/download

# Pull a CPU-friendly model
ollama pull llama3.2:3b

# Pre-warm the model (eliminates cold-start on first API request)
ollama run llama3.2:3b ""

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

---

## Step 2 — Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with required values:

```env
# ── REQUIRED ────────────────────────────────────────────────────
SECRET_KEY=change-me-to-a-random-64-char-hex-string
DATABASE_URL=postgresql://appuser:apppassword@db:5432/inference_platform
REDIS_URL=redis://redis:6379/0
OLLAMA_BASE_URL=http://host.docker.internal:11434

# ── OPTIONAL (shown with defaults) ──────────────────────────────
LOG_LEVEL=INFO
LOG_FORMAT=json
INFERENCE_TIMEOUT_SECONDS=120
RATE_LIMIT_FAIL_OPEN=true
USAGE_LOG_RETENTION_DAYS=90
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:80
```

Generate a secure SECRET_KEY:
```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

---

## Step 3 — Start the Platform

```bash
docker compose up -d

# Watch startup logs
docker compose logs -f api

# Verify all services healthy
docker compose ps
```

Expected output:
```
NAME         STATUS          PORTS
api          running (healthy)   0.0.0.0:8000->8000/tcp
frontend     running (healthy)   0.0.0.0:80->80/tcp
db           running (healthy)   5432/tcp
redis        running (healthy)   6379/tcp
prometheus   running             0.0.0.0:9090->9090/tcp
grafana      running             0.0.0.0:3001->3000/tcp
```

---

## Step 4 — Verify Inference

```bash
# Health check
curl http://localhost:8000/health

# Get a JWT (using the seeded admin account)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@platform.local","password":"changeme123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Non-streaming inference
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2:3b",
    "messages": [{"role": "user", "content": "Say hello in one sentence."}],
    "stream": false
  }'

# Streaming inference
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2:3b",
    "messages": [{"role": "user", "content": "Count to 5."}],
    "stream": true
  }'
```

---

## Step 5 — Open Admin UI

Navigate to: **http://localhost**

Default credentials (change immediately after first login):
- Email: `admin@platform.local`
- Password: `changeme123`

---

## Step 6 — Open Monitoring

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3001 (admin / admin on first login)

The "AI Inference Platform" dashboard is provisioned automatically.

---

## Stopping the Platform

```bash
# Stop (preserve data)
docker compose down

# Stop and wipe all data (fresh start)
docker compose down -v
```

---

## Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| `api` container unhealthy | Ollama not running | Run `ollama serve` on host |
| `db` container not healthy | Port conflict | Check `5432` not in use |
| Inference timeout | Model not pre-warmed | Run `ollama run <model> ""` first |
| `RATE_LIMIT_FAIL_OPEN` warning in logs | Redis not reachable | Check `redis` container health |
| Streaming cuts off mid-response | Ollama OOM on CPU | Use smaller model or increase swap |

---

## Windows-Specific Notes

- Use `host.docker.internal` as `OLLAMA_BASE_URL` host (already in `.env.example`)
- On Docker Desktop for Windows, ensure "Use WSL 2 based engine" is enabled
- Run Ollama in a separate terminal: `ollama serve`
- PowerShell equivalent for token generation: `python -c "import secrets; print(secrets.token_hex(64))"`

---

## Platform Administration Reference

```bash
# Run DB migrations manually
docker compose exec api alembic upgrade head

# Create additional admin users
docker compose exec api python -m app.cli create-user \
  --email ops@example.com --role platform_admin --password changeme123

# Tail structured logs
docker compose logs -f api | python -m json.tool

# Run pip-audit
docker compose exec api pip-audit

# Run test suite
docker compose exec api pytest tests/ -v
```
