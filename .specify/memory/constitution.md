# AI Inference Platform Constitution

## Core Principles

### I. Inference-First Architecture
Every component is built around CPU-native LLM inference via Ollama + llama.cpp. Models must be GGUF-quantised (Q4_K_M), under 4 GB file size, and run within a 3 GB RAM budget for the inference process. Only one model is loaded at a time (`OLLAMA_MAX_LOADED_MODELS=1`). Context window is capped at `num_ctx=2048` to conserve RAM. Primary model is Llama 3.2 3B Instruct Q4_K_M; fallbacks are Phi-3 Mini 3.8B and Gemma 2 2B.

### II. OpenAI-Compatible API Contract
All inference endpoints must conform to the OpenAI REST schema. `POST /v1/chat/completions` must support both blocking and SSE streaming modes. Every response — success or error — must follow the unified envelope: `{ success, data }` or `{ success, error: { code, message, details } }`. No deviations without explicit team agreement.

### III. Role-Based Access Control (NON-NEGOTIABLE)
Four roles are enforced platform-wide: **Super Admin** (platform-level), **Org Admin** (org-scoped), **Team Lead** (team-scoped), **User** (self-scoped). Every user belongs to exactly one organisation and holds exactly one role. Cross-org requests are rejected with `403` before any business logic executes. Role checks are applied as FastAPI route-level dependencies — never inline in handlers.

### IV. Security by Default
API keys are shown only once at creation and stored exclusively as SHA-256 hashes — plaintext is never persisted or logged. JWT secrets must be at least 32 characters and rotated every 90 days. `.env` files are never committed; only `.env.example` with placeholder values is tracked. No stack traces are exposed in HTTP responses in production. Redis rate-limit state is ephemeral and acceptable to lose on restart.

### V. Structured Observability
All logs are emitted as structured JSON to stdout using `python-json-logger`. Every log line within a request context must include `request_id`, `user_id`, and `org_id`. Inference latency must be logged at `INFO` level for every request. Prometheus counters and histograms (TTFT, throughput, per-key counts) are scraped every 15 seconds by Prometheus and visualised in Grafana. No `print()` statements; no root logger usage.

### VI. Configuration as Code
All configuration is injected via environment variables validated at startup by Pydantic `BaseSettings`. The application must refuse to start if any required variable is missing. No hardcoded values in source code. The `Settings` class in `app/config.py` is the single authoritative configuration object.

### VII. Simplicity & Single-Host Scope (v1)
v1 is a single-host Docker Compose deployment on a developer laptop. Kubernetes, vLLM, cloud deployment, OAuth/SSO, billing, and model training are explicitly out of scope. YAGNI — defer complexity to v2. Ollama runs as a native host process outside Docker Compose to retain all remaining CPU/RAM.

## Technology Stack

| Layer | Technology | Constraint |
|---|---|---|
| Inference | Ollama + llama.cpp | CPU-native GGUF; no GPU required |
| API Framework | FastAPI + Uvicorn (Python 3.12) | Async; OpenAI-compatible; SSE streaming |
| Database | PostgreSQL 16 | Orgs, users, keys (hashed), usage logs |
| Auth | JWT (HS256) + SHA-256 + bcrypt | Stateless; no external IdP |
| Rate Limiting | Redis + Lua token bucket (redis-py) | Per-key atomic bucket; no slowapi |
| Orchestration | Docker Compose | Single-host local dev only |
| Admin UI | React + Vite | SPA for org, user, key management |
| Observability | Prometheus + Grafana | TTFT, throughput, per-key dashboards |
| ORM / Migrations | SQLAlchemy 2 + Alembic | Async ORM; migrations run before serving |
| Testing | pytest + httpx | API integration tests + load benchmarks |

## Development Standards

**Exception handling**: Never raise `HTTPException` directly — use `AppError` subclasses. Never let `SQLAlchemy IntegrityError` propagate — catch and re-raise as `ConflictError`. Always log with `logger.exception()` server-side; never expose stack traces to clients.

**Naming**: Python files `snake_case`; classes `PascalCase`; constants `SCREAMING_SNAKE_CASE`; API routes `kebab-case` nouns; DB tables `snake_case` plural; DB indexes `idx_{table}_{column}`; React components `PascalCase`; React hooks `camelCase` with `use` prefix.

**Folder structure**: Monorepo with `backend/`, `frontend/`, `docker-compose/`, and `observability/` as top-level directories. Business logic lives in `services/`; no DB calls in route handlers. Pydantic schemas in `schemas/`; SQLAlchemy models in `models/`.

**Startup order**: PostgreSQL → Redis → Alembic migration job → api-backend → frontend → Prometheus → Grafana → Ollama (native, must be up before backend).

**Pagination**: All list endpoints accept `page` (default 1) and `page_size` (default 20, max 100). The `meta` field is always present on list responses.

## Delivery Phases & Quality Gates

| Phase | Timeline | Key Gate |
|---|---|---|
| Phase 1 — Inference & Database | Day 1–2 | Ollama streams response; Alembic migrations clean; all Compose services healthy |
| Phase 2 — API Gateway & Auth | Day 3–6 | `/v1/chat/completions` matches OpenAI schema; 429 on rate limit; structured JSON logs |
| Phase 3 — Multi-tenancy & Admin UI | Day 7–10 | Cross-org calls rejected; React UI functional; role-gated views enforced |
| Phase 4 — Observability & Hardening | Day 11–15 | Grafana panels populated; `pip-audit` passes; cold-start under 5 minutes |

## Governance

This Constitution supersedes all other practices and conventions on this project. Any deviation requires explicit team agreement and must be documented with justification. All PRs must verify compliance with the role enforcement, API response format, logging, and secret management rules above. Scope additions must be deferred to v2 unless formally amended here.

**Version**: 1.0.0 | **Ratified**: 2026-05-13 | **Last Amended**: 2026-05-13