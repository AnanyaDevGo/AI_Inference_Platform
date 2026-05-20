# Research: AI Inference Platform

**Phase 0 output** | Generated: 2026-05-13 | Feature: `001-ai-inference-platform`

All NEEDS CLARIFICATION items from the spec have been resolved below. No open unknowns remain.

---

## R-001: Ollama HTTP API Integration Pattern

**Decision**: Use `httpx.AsyncClient` with `stream=True` to proxy requests from FastAPI to Ollama's `POST /api/chat` endpoint. Translate OpenAI-compatible request schema to Ollama schema on the fly in `inference_service.py`.

**Rationale**: Ollama exposes a REST API on `localhost:11434`. Using async httpx keeps the FastAPI event loop non-blocking during token streaming. No Ollama Python SDK is used — direct HTTP is simpler and avoids SDK version coupling.

**Alternatives Considered**:
- Ollama Python SDK: adds a version dependency without meaningful benefit at this scale
- Subprocess llama.cpp: harder to manage model lifecycle; Ollama already wraps llama.cpp

**OpenAI → Ollama mapping**:

| OpenAI field | Ollama field | Notes |
|---|---|---|
| `model` | `model` | Direct pass-through |
| `messages` | `messages` | Direct pass-through |
| `stream` | `stream` | Direct pass-through |
| `temperature` | `options.temperature` | Nested under `options` |
| `max_tokens` | `options.num_predict` | Different name |
| `top_p` | `options.top_p` | Nested under `options` |

---

## R-002: JWT Strategy

**Decision**: Use `python-jose[cryptography]` with HS256 algorithm. Access token TTL = 15 minutes. Refresh token TTL = 7 days, stored in `api_keys`-adjacent table row with a `jti` (JWT ID) for revocation. Tokens carry: `sub` (user_id), `org_id`, `role`, `jti`, `exp`.

**Rationale**: HS256 is sufficient for single-host deployment where the secret never leaves the server. RS256 adds key management overhead with no benefit here. Short access TTL limits blast radius of token theft.

**Alternatives Considered**:
- RS256: unnecessary complexity for single-host; no external token consumers
- Stateless refresh tokens: cannot revoke without a blocklist; chosen approach uses DB row deletion for revocation

---

## R-003: API Key Hashing

**Decision**: On creation, generate a 32-byte cryptographically random key prefixed with `sk-` (e.g., `sk-<base64url>`). Store `SHA-256(raw_key)` in the `api_keys.key_hash` column. Return the plaintext key once to the caller. On each request, compute `SHA-256(presented_key)` and look up by hash.

**Rationale**: SHA-256 is appropriate for high-entropy random secrets (API keys). bcrypt is for low-entropy human-chosen passwords. Constant-time comparison (`hmac.compare_digest`) prevents timing attacks.

**Alternatives Considered**:
- bcrypt for API keys: unnecessary — keys are already high entropy; bcrypt adds 100–300 ms per lookup
- Storing plaintext: rejected — violates security requirement FR-010

---

## R-004: Redis Token-Bucket Rate Limiting

**Decision**: Implement token-bucket algorithm via a single Lua script executed atomically on Redis. Script signature: `EVAL lua_script 1 <key> <capacity> <refill_rate_per_second> <now_unix_ms>`. Key format: `ratelimit:<org_id>:<key_hash_prefix>`. TTL set to `capacity / refill_rate * 2` seconds.

**Rationale**: Lua scripts execute atomically in Redis — no race conditions without distributed locks. Single script = single round-trip. Token bucket (vs fixed window) provides smooth burst handling appropriate for inference workloads.

**Failure Behavior**: If Redis is unreachable, check `RATE_LIMIT_FAIL_OPEN` env var. Default: `true` (fail open — allow request, log warning). Operators can set `false` for stricter environments.

**Alternatives Considered**:
- Fixed window counter: simpler but allows 2× burst at window boundary
- Sliding window log: accurate but memory-intensive at scale
- External rate-limit service: YAGNI — Redis already in stack

---

## R-005: SSE Streaming Implementation

**Decision**: Use FastAPI's `StreamingResponse` with `media_type="text/event-stream"`. Generator function reads from `httpx` async stream, formats each chunk as `data: <json>\n\n`, and yields. Final chunk sends `data: [DONE]\n\n`. TTFT is measured as time from request receipt to first non-empty chunk yielded.

**Rationale**: FastAPI's `StreamingResponse` handles back-pressure and client disconnect cleanly. SSE (not WebSocket) is sufficient — inference is unidirectional server-to-client.

**Client Disconnect Handling**: Wrap the async generator in a `try/finally` block; on `asyncio.CancelledError` (client disconnect), cancel the upstream httpx request and log the event.

---

## R-006: PostgreSQL Schema & Indexing Strategy

**Decision**: See `data-model.md` for full schema. Key indexing decisions:
- `api_keys.key_hash`: unique index — primary lookup path
- `usage_logs(org_id, created_at)`: composite index for dashboard queries
- `usage_logs(api_key_id)`: index for per-key breakdown
- `users(org_id, email)`: composite unique index for org-scoped uniqueness
- All foreign keys indexed by default via SQLAlchemy

**Pagination**: Cursor-based using `created_at + id` for `usage_logs`. Keyset pagination avoids OFFSET performance degradation on large tables.

---

## R-007: Structured Logging with structlog

**Decision**: Configure `structlog` with `JSONRenderer` for production and `ConsoleRenderer` for local dev (controlled by `LOG_FORMAT=json|console` env var). Every request attaches `request_id`, `org_id`, `user_id` to the structlog context via middleware. Log levels: DEBUG (dev), INFO (prod default).

**Log Schema**:
```json
{
  "timestamp": "2026-05-13T08:30:00.123Z",
  "level": "info",
  "request_id": "uuid4",
  "org_id": "uuid4",
  "user_id": "uuid4 or null",
  "api_key_id": "uuid4 or null",
  "event": "inference_request_complete",
  "model": "llama3:8b-q4_K_M",
  "duration_ms": 12450,
  "ttft_ms": 890,
  "prompt_tokens": 120,
  "completion_tokens": 340
}
```

---

## R-008: Prometheus Metrics

**Decision**: Use `prometheus-fastapi-instrumentator` for automatic HTTP metrics. Add custom metrics in `app/observability/metrics.py`:

| Metric | Type | Labels |
|--------|------|--------|
| `inference_requests_total` | Counter | `org_id`, `model`, `status` |
| `inference_duration_seconds` | Histogram | `org_id`, `model` |
| `inference_ttft_seconds` | Histogram | `org_id`, `model` |
| `rate_limit_rejections_total` | Counter | `org_id` |
| `active_models_count` | Gauge | — |
| `auth_failures_total` | Counter | `reason` |

Buckets for duration histogram: `[1, 5, 10, 20, 30, 45, 60, 90, 120]` seconds (CPU inference is slow).

---

## R-009: Frontend Auth Storage

**Decision**: Store JWT access token in memory (Zustand store), not localStorage. Use `httpOnly` cookie for refresh token set by `/auth/login` response. On page reload, attempt silent refresh via `/auth/refresh` using the cookie; if it fails, redirect to login.

**Rationale**: Memory storage prevents XSS token theft. `httpOnly` cookie for refresh token prevents JS access. Trade-off: token lost on tab close, but silent refresh recovers it seamlessly.

---

## R-010: Docker Compose Resource Limits

**Decision**: Apply `deploy.resources.limits` per service:

| Service | CPU | Memory |
|---------|-----|--------|
| `api` (FastAPI) | 2.0 | 512 MB |
| `frontend` (Nginx) | 0.5 | 64 MB |
| `db` (PostgreSQL) | 1.0 | 512 MB |
| `redis` | 0.5 | 128 MB |
| `prometheus` | 0.5 | 256 MB |
| `grafana` | 0.5 | 256 MB |

Total: ~1.8 GB RAM for Dockerized services. Ollama + OS take remaining RAM (targeting ≤ 6 GB for Ollama with a 7B Q4 model).

---

## R-011: Alembic Migration Strategy

**Decision**: Sequential integer versioning (`001_`, `002_`, etc.) enforced by naming convention. `alembic upgrade head` runs automatically on API container startup via `entrypoint.sh`. Migrations are additive-only in Phases 1–3; destructive migrations require explicit `--unsafe` flag documented in runbook.

**Migration Order**:
1. `001_create_orgs.py`
2. `002_create_users.py`
3. `003_create_api_keys.py`
4. `004_create_model_registry.py`
5. `005_create_usage_logs.py`
6. `006_create_refresh_tokens.py`
7. `007_add_indexes.py`

---

## R-012: RBAC Permission Matrix

| Action | platform-admin | org-admin | operator | viewer |
|--------|:-:|:-:|:-:|:-:|
| Create org | ✅ | ❌ | ❌ | ❌ |
| List orgs | ✅ | ✅ (own) | ❌ | ❌ |
| Create user | ✅ | ✅ (own org) | ❌ | ❌ |
| Delete user | ✅ | ✅ (own org) | ❌ | ❌ |
| Create API key | ✅ | ✅ (own org) | ❌ | ❌ |
| Revoke API key | ✅ | ✅ (own org) | ❌ | ❌ |
| Submit inference | ✅ | ✅ | ✅ | ❌ |
| View usage | ✅ | ✅ (own org) | ✅ (own org) | ✅ (own org) |
| Load/unload model | ✅ | ❌ | ✅ | ❌ |
| View models | ✅ | ✅ | ✅ | ✅ |
| View metrics | ✅ | ❌ | ✅ | ❌ |

**Implementation**: `require_role(*roles)` FastAPI dependency raises `HTTP 403` if `current_user.role not in roles`. Org isolation applied as a DB filter: `query.filter(Model.org_id == current_user.org_id)` for all non-platform-admin requests.

---

## R-013: Cold-Start Handling

**Decision**: Ollama loads models lazily on first request. The platform adds a configurable `INFERENCE_TIMEOUT_SECONDS` (default: 120 s) for the full request. A separate `OLLAMA_HEALTH_CHECK_TIMEOUT` (default: 5 s) is used for startup validation. If Ollama is unreachable at startup, the API logs a warning but continues — Ollama may start after the API container.

**Cold-start mitigation**: Document in `quickstart.md` that operators should run `ollama run <model> ""` before starting the platform to pre-warm the model. The platform does not auto-warm models.

---

## R-014: Testing Strategy

**Unit tests** (`tests/unit/`): Pure function tests — JWT encode/decode, SHA-256 key hashing, Lua script logic simulation, Pydantic schema validation.

**Integration tests** (`tests/integration/`): Use `httpx.AsyncClient` with `TestClient` against a real test DB (PostgreSQL in Compose test profile). Cover: full auth flow, RBAC matrix (all role × action combinations), rate-limit exhaustion, cross-org rejection, streaming response chunking, usage log writes.

**Load tests** (`tests/load/`): Locust script with 10 concurrent users, 5-minute ramp. Target: zero 5xx, P95 latency reported, TTFT measured.

**RBAC test matrix**: Parametrized pytest — iterate all (role, endpoint, expected_status) combinations from a fixture table. Ensures no gaps.
