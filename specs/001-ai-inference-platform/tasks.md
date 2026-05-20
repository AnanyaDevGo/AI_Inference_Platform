# Tasks: AI Inference Platform

**Feature**: `001-ai-inference-platform` | **Generated**: 2026-05-13
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## Phase 1 — Setup (Project Initialization)

- [ ] T001 Initialize backend project structure: `backend/` with `app/`, `tests/`, `alembic/`, `pyproject.toml`
- [ ] T002 Initialize frontend project: `frontend/` via `npm create vite@latest . -- --template react-ts`
- [ ] T003 Create root `docker-compose.yml` with `db`, `redis`, `api`, `frontend` service stubs
- [ ] T004 Create `.env.example` with all required and optional variables documented
- [ ] T005 [P] Create `backend/Dockerfile` (Python 3.11-slim, non-root user, entrypoint.sh)
- [ ] T006 [P] Create `frontend/Dockerfile` (Node 20 build stage + Nginx serve stage)
- [ ] T007 Create `backend/app/config.py` using `pydantic-settings` BaseSettings with startup env validation
- [ ] T008 Create `backend/entrypoint.sh`: run `alembic upgrade head` then start uvicorn

---

## Phase 2 — Foundational (Blocking Prerequisites)

- [ ] T009 Configure PostgreSQL service in `docker-compose.yml` with healthcheck and named volume
- [ ] T010 Configure Redis service in `docker-compose.yml` with healthcheck
- [ ] T011 Create `backend/app/database.py`: async SQLAlchemy engine + `AsyncSession` factory + `get_db` dependency
- [ ] T012 Configure `alembic/env.py` for async engine and `DATABASE_URL` from env
- [ ] T013 Create migration `001_create_orgs.py`: `orgs` table per data-model.md
- [ ] T014 Create migration `002_create_users.py`: `users` table with FK → orgs
- [ ] T015 Create migration `003_create_api_keys.py`: `api_keys` table with FK → orgs, users
- [ ] T016 Create migration `004_create_refresh_tokens.py`: `refresh_tokens` table with FK → users
- [ ] T017 Create migration `005_create_model_registry.py`: `model_registry` table
- [ ] T018 Create migration `006_create_usage_logs.py`: `usage_logs` table with all FKs
- [ ] T019 Create migration `007_add_indexes.py`: all composite indexes per data-model.md
- [ ] T020 Create `backend/app/main.py`: FastAPI app factory, lifespan, include all routers
- [ ] T021 Create `backend/app/middleware/correlation.py`: inject UUID `X-Request-ID` on every request
- [ ] T022 Create `backend/app/observability/logging.py`: structlog JSON config, bind request_id/org_id/user_id
- [ ] T023 Create `backend/app/middleware/logging.py`: structlog request middleware (method, path, status, duration_ms)
- [ ] T024 [P] Create SQLAlchemy ORM model `backend/app/models/org.py`
- [ ] T025 [P] Create SQLAlchemy ORM model `backend/app/models/user.py`
- [ ] T026 [P] Create SQLAlchemy ORM model `backend/app/models/api_key.py`
- [ ] T027 [P] Create SQLAlchemy ORM model `backend/app/models/refresh_token.py`
- [ ] T028 [P] Create SQLAlchemy ORM model `backend/app/models/model_registry.py`
- [ ] T029 [P] Create SQLAlchemy ORM model `backend/app/models/usage_log.py`
- [ ] T030 Seed script: create default `platform` org and `admin@platform.local` platform-admin user

---

## Phase 3 — User Story 1: Developer Sends an Inference Request (P1)

- [ ] T031 [US1] Create `backend/app/schemas/inference.py`: Pydantic v2 `ChatCompletionRequest`, `ChatCompletionResponse`, `StreamChunk` schemas (OpenAI-compatible)
- [ ] T032 [US1] Create `backend/app/services/inference_service.py`: async httpx Ollama proxy, OpenAI→Ollama field mapping per research.md R-001
- [ ] T033 [US1] Implement non-streaming path in `inference_service.py`: POST to Ollama `/api/chat`, parse response, return `ChatCompletionResponse`
- [ ] T034 [US1] Implement streaming path in `inference_service.py`: `httpx` stream, yield SSE chunks, measure TTFT, send `[DONE]`, handle client disconnect via `try/finally`
- [ ] T035 [US1] Create `backend/app/routers/inference.py`: `POST /v1/chat/completions` using `StreamingResponse` for stream=true, regular response for stream=false
- [ ] T036 [US1] Implement timeout handling in `inference_service.py`: wrap httpx call with `asyncio.wait_for(INFERENCE_TIMEOUT_SECONDS)`; raise 504 on timeout
- [ ] T037 [US1] Create `backend/app/routers/models.py`: `GET /v1/models`, `GET /v1/models/{name}`, `POST /v1/models/{name}/load`, `POST /v1/models/{name}/unload`
- [ ] T038 [US1] Create `backend/app/routers/health.py`: `GET /health` checks DB, Redis, Ollama reachability; returns 200/503
- [ ] T039 [US1] Create `backend/app/services/usage_service.py`: write `usage_log` row after every completed inference request (tokens, duration_ms, ttft_ms, status)
- [ ] T040 [US1] Wire Ollama startup validation in `app/main.py` lifespan: log warning if `GET /api/tags` fails (non-fatal)
- [ ] T041 [US1] Integration test `tests/integration/test_inference.py`: streaming round-trip, non-streaming round-trip, timeout simulation, Ollama-unreachable 503

---

## Phase 4 — User Story 2: Administrator Manages Users, Roles & API Keys (P1)

- [ ] T042 [US2] Create `backend/app/services/auth_service.py`: bcrypt verify, JWT encode/decode (HS256, python-jose), refresh token issuance + rotation
- [ ] T043 [US2] Create `backend/app/schemas/auth.py`: `LoginRequest`, `TokenResponse`, `UserResponse`
- [ ] T044 [US2] Create `backend/app/routers/auth.py`: `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
- [ ] T045 [US2] Implement `httpOnly` refresh token cookie set/clear in auth router responses
- [ ] T046 [US2] Create `backend/app/dependencies.py`: `get_current_user` (JWT decode → user lookup), `get_current_user_from_api_key` (SHA-256 lookup), `require_role(*roles)` dependency
- [ ] T047 [US2] Implement API key generation in `auth_service.py`: `secrets.token_urlsafe(32)` prefixed `sk-`, SHA-256 hash stored, plaintext returned once
- [ ] T048 [US2] Create `backend/app/schemas/admin.py`: Pydantic schemas for Org, User, ApiKey create/update/response
- [ ] T049 [US2] Create `backend/app/routers/admin/orgs.py`: CRUD endpoints for orgs (platform-admin only)
- [ ] T050 [US2] Create `backend/app/routers/admin/users.py`: list/create/patch/delete users with org-scoped isolation
- [ ] T051 [US2] Create `backend/app/routers/admin/api_keys.py`: list/create/revoke API keys; org-scoped
- [ ] T052 [US2] Apply `require_role` dependency to ALL protected routes; enforce org_id filter on every DB query for non-platform-admin users
- [ ] T053 [US2] Add login rate-limit (10 req/min per IP) to `POST /auth/login` via simple Redis counter (not token-bucket)
- [ ] T054 [US2] Integration test `tests/integration/test_auth.py`: login flow, refresh rotation, logout, revoked token rejection, bcrypt timing
- [ ] T055 [US2] Integration test `tests/integration/test_rbac.py`: parametrized matrix — all (role × endpoint × expected_status) combinations
- [ ] T056 [US2] Integration test `tests/integration/test_cross_org.py`: all cross-org access patterns return 403

---

## Phase 5 — User Story 3: Operator Monitors Platform Health (P2)

- [ ] T057 [US3] Create `backend/app/observability/metrics.py`: define all Prometheus metrics per research.md R-008 (counters, histograms with CPU-appropriate buckets)
- [ ] T058 [US3] Add `prometheus-fastapi-instrumentator` to FastAPI app; mount `/metrics` endpoint
- [ ] T059 [US3] Instrument `inference_service.py`: record `inference_requests_total`, `inference_duration_seconds`, `inference_ttft_seconds` per request
- [ ] T060 [US3] Instrument `rate_limit_service.py`: increment `rate_limit_rejections_total` on 429
- [ ] T061 [US3] Instrument `auth_service.py`: increment `auth_failures_total` with `reason` label
- [ ] T062 [US3] [P] Add Prometheus service to `docker-compose.yml` with scrape config targeting `api:8000/metrics`
- [ ] T063 [US3] [P] Add Grafana service to `docker-compose.yml` with provisioned datasource and dashboard YAML
- [ ] T064 [US3] Create Grafana dashboard JSON `infra/grafana/dashboards/platform.json`: panels for request rate, error rate, TTFT P50/P95/P99, rate-limit events, active models
- [ ] T065 [US3] Integration test `tests/integration/test_metrics.py`: verify metrics endpoint returns expected metric names after sample requests

---

## Phase 6 — User Story 4: Developer Manages Models via Admin UI (P2)

- [ ] T066 [US4] Initialize React/Vite SPA: `frontend/src/` structure with React Router v6, Zustand, Recharts, axios
- [ ] T067 [US4] Create `frontend/src/stores/authStore.ts`: Zustand store for access token (memory), user profile, current org
- [ ] T068 [US4] Create `frontend/src/api/client.ts`: axios instance with base URL, Bearer token injector, 401 → silent refresh → retry interceptor
- [ ] T069 [US4] Create `frontend/src/pages/Login.tsx`: email/password form → POST /auth/login → store token → redirect to dashboard
- [ ] T070 [US4] Create `frontend/src/components/ProtectedRoute.tsx`: redirect to /login if no token; role check for role-gated routes
- [ ] T071 [US4] Create `frontend/src/pages/Models.tsx`: list models with status badges; Load/Unload buttons visible to operator+ only; viewer sees read-only list
- [ ] T072 [US4] Create `frontend/src/pages/Users.tsx`: list users, create user form, deactivate button (org-admin+ only); viewer sees read-only
- [ ] T073 [US4] Create `frontend/src/pages/ApiKeys.tsx`: list keys (prefix + status), create key modal (show plaintext once), revoke button
- [ ] T074 [US4] Create `frontend/src/components/OrgSwitcher.tsx`: dropdown for multi-org users; on switch reset all Zustand query state and refetch
- [ ] T075 [US4] Create `frontend/src/components/ErrorBoundary.tsx` + toast notification system for API errors
- [ ] T076 [US4] Configure Nginx `frontend/nginx.conf`: serve SPA static files + reverse-proxy `/api` → `api:8000`

---

## Phase 7 — User Story 5: Developer Reviews Per-Org Usage (P3)

- [ ] T077 [US5] Create `backend/app/routers/usage.py`: `GET /v1/usage` (paginated, filtered) + `GET /v1/usage/summary` (aggregated) per admin-api.md contract
- [ ] T078 [US5] Implement keyset pagination in `usage_service.py` using `(created_at, id)` cursor (base64-encoded)
- [ ] T079 [US5] Create `frontend/src/pages/Dashboard.tsx`: usage summary chart (Recharts line chart, tokens/day), total requests + tokens KPI cards, date range filter
- [ ] T080 [US5] Create `frontend/src/pages/Usage.tsx`: paginated usage log table with filters (date range, model, API key); infinite-scroll or "load more"
- [ ] T081 [US5] Integration test `tests/integration/test_usage.py`: pagination correctness, date filter, org isolation, per-key breakdown

---

## Phase 8 — Redis Rate Limiting (Cross-Cutting, Blocks US1 Auth in Production)

- [ ] T082 Create `backend/app/services/rate_limit_service.py`: Redis Lua token-bucket script (capacity, refill_rate_per_second, now_unix_ms); atomic EVAL
- [ ] T083 Implement fail-open/fail-closed behavior in `rate_limit_service.py` via `RATE_LIMIT_FAIL_OPEN` env var; log warning on Redis error
- [ ] T084 Wire rate limiter as FastAPI dependency on `POST /v1/chat/completions`: reads `org.rate_limit_rpm` + `rate_limit_burst`; raises 429 with `Retry-After` + rate-limit headers
- [ ] T085 Integration test `tests/integration/test_rate_limit.py`: exhaust bucket → 429 with correct headers; wait for refill → 200; Redis-down fail-open; Redis-down fail-closed

---

## Phase 9 — Security & Hardening

- [ ] T086 Expand `config.py` startup validation: list all required env vars; on missing → log clear error with var name and exit(1), not traceback
- [ ] T087 Add `pip-audit` to `pyproject.toml` dev dependencies; add `pip-audit` step to `entrypoint.sh` pre-start check (warn, not block)
- [ ] T088 Sanitize all 500 error responses: production mode returns `{"error":{"code":"internal_error","message":"An unexpected error occurred","request_id":"..."}}` — no stack traces
- [ ] T089 Create `backend/app/middleware/error_handler.py`: global exception handler mapping exceptions → standard error envelope per auth-api.md contract
- [ ] T090 Set `LOG_FORMAT=json` in production `docker-compose.yml`; verify no plaintext secrets appear in structured log output
- [ ] T091 Add Docker Compose resource limits per research.md R-010 to all services
- [ ] T092 Document HTTPS self-signed cert setup in `docs/runbook.md` (Nginx TLS termination)

---

## Phase 10 — Testing & Validation

- [ ] T093 Create `tests/unit/test_jwt.py`: encode/decode, expiry, invalid signature, missing claims
- [ ] T094 [P] Create `tests/unit/test_api_key_hashing.py`: SHA-256 hash consistency, constant-time compare, prefix extraction
- [ ] T095 [P] Create `tests/unit/test_schemas.py`: Pydantic v2 validation for all request schemas (invalid model, empty messages, out-of-range temperature)
- [ ] T096 [P] Create `tests/unit/test_lua_ratelimit.py`: simulate token-bucket Lua logic in Python, verify burst + refill math
- [ ] T097 Create `tests/load/locustfile.py`: 10 concurrent users, 5-min ramp, mix of streaming + non-streaming; report P50/P95/P99
- [ ] T098 Create `tests/integration/test_cold_start.py`: measure first-request TTFT when model not warmed; assert within 120 s timeout
- [ ] T099 Create `tests/integration/test_streaming.py`: verify SSE chunk format, `[DONE]` termination, client-disconnect cleanup

---

## Phase 11 — Documentation

- [ ] T100 Write `README.md`: project overview, prerequisites, 5-step quickstart, architecture diagram (ASCII), links to all spec docs
- [ ] T101 Write `docs/runbook.md`: startup/shutdown procedures, DB migration steps, log viewing, secret rotation, HTTPS setup, model provisioning
- [ ] T102 [P] Write `docs/api.md`: link to contracts/ and auto-generated OpenAPI at `/docs` (FastAPI built-in)
- [ ] T103 [P] Write `docs/troubleshooting.md`: common failure modes from quickstart.md + remediation steps

---

## Dependency Graph

```
T001–T008 (Setup)
    └─► T009–T030 (Foundational: DB, migrations, ORM, middleware)
            ├─► T031–T041 (US1: Inference — MVP, independently testable)
            ├─► T042–T056 (US2: Auth/RBAC — requires US1 routes to protect)
            │       └─► T082–T085 (Rate Limiting — wires into US1 route)
            ├─► T057–T065 (US3: Observability — instruments US1+US2)
            ├─► T066–T076 (US4: Admin UI — consumes US1+US2 APIs)
            └─► T077–T081 (US5: Usage Dashboard — requires US2 auth + US1 logs)
T086–T092 (Hardening — applies across all phases)
T093–T099 (Testing — written alongside each phase)
T100–T103 (Docs — written last)
```

## Parallel Execution Opportunities

| Track A | Track B |
|---------|---------|
| T031–T041 (Inference backend) | T066–T076 (Frontend scaffold + UI pages) |
| T057–T065 (Metrics + Grafana) | T042–T056 (Auth + RBAC backend) |
| T082–T085 (Rate limiting) | T077–T081 (Usage endpoints) |
| T093–T096 (Unit tests) | T086–T092 (Hardening) |

## MVP Scope (User Story 1 only)

To validate the platform end-to-end with minimum work, complete only:

**T001–T008 → T009–T030 → T031–T041**

This delivers: working inference proxy with streaming, usage logging, health check, and DB — no auth, no UI. Sufficient to validate Ollama integration on target hardware before building the rest.

---

**Total tasks**: 103
**P0 (blocking)**: T001–T041 (Setup + US1)
**P1 (required for v1)**: T042–T085
**P2 (quality/completeness)**: T086–T103
