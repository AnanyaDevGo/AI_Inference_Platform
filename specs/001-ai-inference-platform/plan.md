# Implementation Plan: AI Inference Platform

**Branch**: `001-ai-inference-platform` | **Date**: 2026-05-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-ai-inference-platform/spec.md`

## Summary

A single-host, CPU-native AI inference serving platform exposing an OpenAI-compatible API, backed by Ollama + llama.cpp with GGUF quantized models. The platform provides JWT + API-key authentication, org-scoped RBAC, Redis-based rate limiting, PostgreSQL usage logging, Prometheus/Grafana observability, and a React/Vite admin SPA — all deployed via Docker Compose on a developer laptop with 8–16 GB RAM.

## Technical Context

**Language/Version**: Python 3.11 (backend), Node 20 LTS (frontend build)
**Primary Dependencies**: FastAPI 0.111, SQLAlchemy 2.0, Alembic, Pydantic v2, httpx (Ollama proxy), python-jose (JWT), passlib[bcrypt], redis-py, prometheus-fastapi-instrumentator, structlog; React 18 + Vite 5, React Router v6, Zustand, Recharts
**Storage**: PostgreSQL 15 (persistent), Redis 7 (rate-limit store — ephemeral OK)
**Testing**: pytest + pytest-asyncio + httpx (API), Locust (load), Playwright (E2E optional)
**Target Platform**: Linux/macOS/Windows via Docker Compose; Ollama runs natively on host
**Project Type**: Web service (backend API) + SPA (admin frontend)
**Performance Goals**: First token within 30 s for 7B Q4 model on CPU; rate-limit check < 50 ms; dashboard query < 2 s for 30-day window
**Constraints**: Single host, ≤ 8 GB RAM total for Dockerized services (Ollama excluded), no GPU, no cloud, no Kubernetes
**Scale/Scope**: ≤ 50 concurrent users, ≤ 10 orgs, ≤ 100 API keys

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Gate | Constraint | Status |
|------|-----------|--------|
| Single-host only | No multi-node, no Kubernetes | ✅ PASS — Docker Compose single-host |
| CPU-only inference | No GPU assumptions | ✅ PASS — Ollama with GGUF/Q4 only |
| No cloud dependencies | All services local | ✅ PASS — PostgreSQL, Redis, Prometheus in Compose |
| No OAuth/SSO | Internal auth only | ✅ PASS — JWT + bcrypt + API keys |
| No billing | Not in scope | ✅ PASS — Excluded from all phases |
| No vLLM | Ollama + llama.cpp only | ✅ PASS — No vLLM in stack |
| No training pipelines | Inference only | ✅ PASS — Model files pre-downloaded |
| YAGNI / Simplicity-first | No premature abstraction | ✅ PASS — Layered FastAPI, no DDD overengineering |
| Structured logging | JSON to stdout | ✅ PASS — structlog planned |
| Secret management | Env vars, no hard-coded secrets | ✅ PASS — BaseSettings + .env file |

**Constitution Check Result**: ALL GATES PASS — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/001-ai-inference-platform/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/           ← Phase 1 output
│   ├── openai-api.md
│   ├── admin-api.md
│   └── auth-api.md
└── tasks.md             ← Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── alembic/
│   ├── versions/
│   └── env.py
├── app/
│   ├── main.py
│   ├── config.py                  # BaseSettings
│   ├── dependencies.py            # DI: get_db, get_current_user, require_role
│   ├── middleware/
│   │   ├── logging.py             # structlog request context
│   │   └── correlation.py         # X-Request-ID injection
│   ├── routers/
│   │   ├── auth.py                # POST /auth/login, /auth/refresh
│   │   ├── inference.py           # POST /v1/chat/completions
│   │   ├── models.py              # GET/POST /v1/models
│   │   ├── admin/
│   │   │   ├── orgs.py
│   │   │   ├── users.py
│   │   │   └── api_keys.py
│   │   └── usage.py               # GET /v1/usage
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── inference_service.py   # Ollama proxy + streaming
│   │   ├── rate_limit_service.py  # Redis token-bucket Lua
│   │   └── usage_service.py
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── org.py
│   │   ├── user.py
│   │   ├── api_key.py
│   │   ├── model_registry.py
│   │   └── usage_log.py
│   ├── schemas/                   # Pydantic v2 request/response
│   │   ├── auth.py
│   │   ├── inference.py
│   │   ├── admin.py
│   │   └── usage.py
│   └── observability/
│       ├── metrics.py             # Prometheus counters/histograms
│       └── logging.py             # structlog config
├── tests/
│   ├── unit/
│   ├── integration/
│   └── load/
├── pyproject.toml
└── Dockerfile

frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/                       # axios client wrappers
│   ├── components/
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx
│   │   ├── Models.tsx
│   │   ├── Users.tsx
│   │   ├── ApiKeys.tsx
│   │   └── Usage.tsx
│   ├── stores/                    # Zustand auth + org state
│   └── hooks/
├── index.html
├── vite.config.ts
└── Dockerfile

docker-compose.yml
docker-compose.override.yml        # dev overrides
.env.example
```

**Structure Decision**: Web application (Option 2). Backend FastAPI service + React/Vite SPA. No monorepo tooling needed at this scale.

---

## Delivery Phases

### Phase 1 — Inference & Database

**Objective**: Establish working inference proxy and persistent data layer. Everything else builds on this.

**Deliverables**:
- Docker Compose with PostgreSQL, Redis services running with health checks
- Alembic with initial migrations: `orgs`, `users`, `api_keys`, `model_registry`, `usage_logs`
- FastAPI app skeleton: config, DB session, structured logging, `/health` endpoint
- Ollama connectivity check on startup (`GET /api/tags` via httpx)
- `POST /v1/chat/completions` — unauthenticated stub — proxies to Ollama, returns streaming SSE
- TTFT measurement on every streaming request
- `usage_logs` write on completion
- pytest: inference proxy round-trip, DB migrations run cleanly

**Dependencies**:
- Ollama installed natively on host with at least one GGUF model pulled
- Docker + Docker Compose installed
- Python 3.11 + Node 20 available for local dev

**Risks**:
- Cold-start latency on CPU can exceed 30 s for large models — mitigated by recommending Q4_K_M quantization for ≤ 7B models
- Ollama API surface may change — pin Ollama version in quickstart

**Exit Criteria**:
- `docker compose up` starts PostgreSQL and Redis with passing health checks
- `POST /v1/chat/completions` with `stream: true` returns tokens incrementally from Ollama
- `usage_logs` row written after each completed request
- All migrations apply cleanly on fresh DB

**Validation Checkpoints**:
1. `curl http://localhost:11434/api/tags` returns model list (Ollama running natively)
2. `docker compose ps` shows `db` and `redis` as healthy
3. `curl -N http://localhost:8000/v1/chat/completions -d '{"model":"...","messages":[...],"stream":true}'` streams tokens
4. `SELECT COUNT(*) FROM usage_logs;` returns > 0 after test request

**Rollback**: Drop all containers and volumes; DB is fresh at this phase.

---

### Phase 2 — API Gateway & Auth

**Objective**: Add authentication, RBAC, rate limiting, and API key management. All routes become protected.

**Deliverables**:
- `POST /auth/login` — bcrypt password verify → JWT access + refresh tokens
- `POST /auth/refresh` — rotate refresh token
- JWT middleware: validates token, injects `current_user` into request context
- API key authentication: SHA-256 lookup against `api_keys` table
- `require_role(...)` FastAPI dependency enforced on every protected route
- Org isolation: every DB query filtered by `org_id` from token context
- Redis Lua token-bucket rate limiter on `/v1/chat/completions` per API key
- Admin routes: CRUD for orgs, users, API keys (platform-admin and org-admin scoped)
- Rate-limit 429 response with `Retry-After` header
- Startup env validation: refuse start if `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL` absent
- pytest: RBAC matrix tests, rate-limit exhaustion, cross-org rejection, revoked key rejection

**Dependencies**: Phase 1 complete; DB migrations for `users`, `api_keys`, `orgs` stable

**Risks**:
- JWT secret rotation requires all sessions invalidated — document in ops runbook
- bcrypt cost factor must be tuned: default 12 may be slow on low-core CPU — benchmark and document

**Exit Criteria**:
- Unauthenticated requests to `/v1/chat/completions` return 401
- Viewer-role user cannot create/delete resources (returns 403)
- Cross-org API key returns 403 on org-scoped endpoints
- Rate-limit: 11th request within window returns 429 with correct `Retry-After`
- Revoked API key returns 401 immediately

**Rollback**: Revert auth middleware; routes become open again (Phase 1 state).

---

### Phase 3 — Multi-tenancy & Admin UI

**Objective**: React/Vite SPA with full admin UI, org switching, role-gated views, and usage dashboards.

**Deliverables**:
- React/Vite SPA bootstrapped, served by Nginx in Docker Compose
- Login page → JWT stored in `httpOnly` cookie or memory (not localStorage)
- Protected routes with role-gated rendering (viewer sees read-only, admin sees actions)
- Pages: Dashboard (usage chart), Models (load/unload), Users, API Keys, Usage (filters + pagination)
- Org switcher component for multi-org users
- `GET /v1/usage` paginated endpoint with date/model/key filters
- Usage chart (Recharts) showing token consumption over time per org
- Error boundary: API errors surfaced as toast notifications, not white screens
- Model management: operator can trigger load/unload via admin API
- pytest: usage pagination, org-scoped usage query isolation

**Dependencies**: Phase 2 complete; auth endpoints stable

**Risks**:
- SPA CORS config must match backend's `ALLOWED_ORIGINS` env var — document clearly
- Org switching must invalidate all cached queries — use Zustand reset on switch

**Exit Criteria**:
- Login flow completes, JWT refreshed silently on expiry
- Viewer-role user: action buttons absent from DOM (not just disabled)
- Org switch: dashboard re-fetches scoped to new org, previous org data absent
- Usage dashboard renders data for ≥ 30 days with date filter applied correctly
- API key create flow shows plaintext key once, then never again

**Rollback**: Remove Nginx service from Compose; backend API unchanged.

---

### Phase 4 — Observability & Hardening

**Objective**: Production-grade observability, security hardening, load validation, and dependency audit.

**Deliverables**:
- Prometheus scrape target configured for FastAPI metrics endpoint
- Grafana provisioned with dashboard: request rate, error rate, TTFT P50/P95/P99, rate-limit events, active models
- structlog JSON format finalized: `timestamp`, `level`, `request_id`, `org_id`, `user_id`, `event`
- X-Request-ID middleware: generate UUID per request, propagate to all log lines and response header
- `pip-audit` integrated into CI / pre-commit: fail on critical CVEs
- HTTPS termination via self-signed cert or Nginx TLS config documented
- Locust load test: 10 concurrent users, 5-minute run — validate no crashes, measure P95 latency
- Input validation: all request bodies validated via Pydantic v2 strict mode
- Rate-limit store failure: configurable `RATE_LIMIT_FAIL_OPEN=true/false` env var
- Environment validation expanded: all required vars checked with descriptive startup error
- Deployment readiness checklist validated end-to-end

**Dependencies**: Phases 1–3 complete; Prometheus and Grafana added to Compose

**Risks**:
- Grafana provisioning YAML format is version-sensitive — pin Grafana image version
- CPU saturation during load test may cause Ollama OOM — document swap space recommendation

**Exit Criteria**:
- Grafana dashboard loads with live data after 5-minute test run
- All log lines contain `request_id` and `org_id`
- `pip-audit` returns zero critical findings
- Locust 10-user run completes with zero 5xx errors (excluding intentional rate-limit 429s)
- P95 TTFT ≤ 45 s for 7B Q4 model on 4-core CPU
- Missing `SECRET_KEY` at startup produces clear error, not a panic traceback

**Rollback**: Remove Prometheus/Grafana services; no functional regression.

---

## Complexity Tracking

No Constitution violations. All design choices follow simplicity-first principle.

| Decision | Justification |
|----------|--------------|
| Zustand (not Redux) | Minimal state: auth token + current org. Redux overhead unjustified. |
| httpx (not requests) | Async-native required for FastAPI streaming proxy. |
| Lua in Redis | Atomic token-bucket without race conditions; single script, no extra service. |
| Nginx for SPA | Static file serving + API reverse proxy in one container; no CDN needed. |
