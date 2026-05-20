# Data Model: AI Inference Platform

**Phase 1 output** | Generated: 2026-05-13 | Feature: `001-ai-inference-platform`

---

## Entity Overview

```
orgs ──< users ──< refresh_tokens
 │
 ├──< api_keys
 ├──< model_registry
 └──< usage_logs >── api_keys
                 └── model_registry
```

---

## Table: `orgs`

Primary tenant boundary. Every other entity belongs to exactly one org.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default gen_random_uuid() | |
| `name` | VARCHAR(100) | NOT NULL, UNIQUE | Human-readable name |
| `slug` | VARCHAR(50) | NOT NULL, UNIQUE | URL-safe identifier |
| `rate_limit_rpm` | INTEGER | NOT NULL, default 60 | Requests per minute |
| `rate_limit_burst` | INTEGER | NOT NULL, default 10 | Burst capacity |
| `is_active` | BOOLEAN | NOT NULL, default TRUE | Soft-delete |
| `created_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default NOW() | Updated via trigger |

**Indexes**: `slug` (unique), `is_active`

**State transitions**: `is_active: TRUE → FALSE` (deactivate); no hard delete.

---

## Table: `users`

Human principals. One user can belong to multiple orgs via role assignment (future: `user_org_roles` join table; Phase 1 simplification: one primary org per user).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → orgs.id, NOT NULL | Primary org |
| `email` | VARCHAR(255) | NOT NULL | |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt, cost 12 |
| `role` | VARCHAR(20) | NOT NULL | `platform_admin`, `org_admin`, `operator`, `viewer` |
| `is_active` | BOOLEAN | NOT NULL, default TRUE | |
| `created_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |

**Indexes**: `(org_id, email)` UNIQUE, `org_id`, `role`

**Constraints**: `role` CHECK IN ('platform_admin', 'org_admin', 'operator', 'viewer')

**Validation rules**:
- `email` must match RFC 5322 pattern (validated in Pydantic schema, not DB constraint)
- `password_hash` never returned in any API response (excluded from all schemas)

---

## Table: `api_keys`

Long-lived credentials for programmatic access. Plaintext key shown once at creation; never stored.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → orgs.id, NOT NULL | Scoping |
| `created_by_user_id` | UUID | FK → users.id, NOT NULL | Audit |
| `name` | VARCHAR(100) | NOT NULL | Human label |
| `key_hash` | VARCHAR(64) | NOT NULL, UNIQUE | SHA-256 hex digest |
| `key_prefix` | VARCHAR(8) | NOT NULL | First 8 chars for display |
| `is_active` | BOOLEAN | NOT NULL, default TRUE | Revocation flag |
| `expires_at` | TIMESTAMPTZ | NULL | Optional expiry |
| `last_used_at` | TIMESTAMPTZ | NULL | Updated on each use |
| `created_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |

**Indexes**: `key_hash` (unique — primary lookup), `org_id`, `is_active`

**State transitions**: `is_active: TRUE → FALSE` (revoke); no hard delete; no un-revoke.

**Security**: On lookup, compute `SHA-256(presented_key)` and query `WHERE key_hash = ? AND is_active = TRUE AND (expires_at IS NULL OR expires_at > NOW())`.

---

## Table: `refresh_tokens`

Tracks issued refresh tokens for revocation support.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `user_id` | UUID | FK → users.id, NOT NULL | |
| `jti` | VARCHAR(36) | NOT NULL, UNIQUE | JWT ID claim |
| `expires_at` | TIMESTAMPTZ | NOT NULL | |
| `revoked_at` | TIMESTAMPTZ | NULL | Set on logout/rotation |
| `created_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |

**Indexes**: `jti` (unique), `user_id`, `expires_at` (for cleanup job)

**Cleanup**: Expired and revoked rows can be purged periodically; no business logic depends on history.

---

## Table: `model_registry`

Catalog of models known to the platform. Backed by Ollama; this table tracks metadata and platform-side config.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `name` | VARCHAR(100) | NOT NULL, UNIQUE | Ollama model name e.g. `llama3:8b-q4_K_M` |
| `display_name` | VARCHAR(100) | NOT NULL | Human label |
| `context_window` | INTEGER | NOT NULL | Max tokens |
| `quantization` | VARCHAR(20) | NULL | e.g. `Q4_K_M` |
| `status` | VARCHAR(20) | NOT NULL, default 'unknown' | `loaded`, `unloaded`, `loading`, `unknown` |
| `last_status_check` | TIMESTAMPTZ | NULL | |
| `is_enabled` | BOOLEAN | NOT NULL, default TRUE | Soft-disable without unloading |
| `created_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default NOW() | |

**Indexes**: `name` (unique), `status`, `is_enabled`

**State transitions**:
```
unknown → loading → loaded
loaded  → unloaded
unloaded → loading → loaded
any     → unknown  (on health-check failure)
```

---

## Table: `usage_logs`

Immutable append-only record of every completed inference request.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `org_id` | UUID | FK → orgs.id, NOT NULL | Denormalized for query performance |
| `api_key_id` | UUID | FK → api_keys.id, NULL | NULL for session-auth requests |
| `user_id` | UUID | FK → users.id, NULL | NULL for API-key-auth requests |
| `model_id` | UUID | FK → model_registry.id, NOT NULL | |
| `model_name` | VARCHAR(100) | NOT NULL | Denormalized; model may be deleted |
| `request_id` | VARCHAR(36) | NOT NULL | X-Request-ID for correlation |
| `prompt_tokens` | INTEGER | NOT NULL | |
| `completion_tokens` | INTEGER | NOT NULL | |
| `total_tokens` | INTEGER | NOT NULL | prompt + completion |
| `duration_ms` | INTEGER | NOT NULL | Wall-clock request duration |
| `ttft_ms` | INTEGER | NULL | NULL for non-streaming requests |
| `status` | VARCHAR(20) | NOT NULL | `success`, `error`, `timeout`, `cancelled` |
| `error_code` | VARCHAR(50) | NULL | Set on non-success |
| `created_at` | TIMESTAMPTZ | NOT NULL, default NOW() | Partition key candidate |

**Indexes**:
- `(org_id, created_at DESC)` — primary dashboard query index
- `(api_key_id, created_at DESC)` — per-key breakdown
- `(model_id, created_at DESC)` — per-model breakdown
- `request_id` — correlation lookup
- `status` — error rate queries

**Immutability**: No UPDATE or DELETE allowed on this table. Rows are never modified after insert. Retention policy: configurable `USAGE_LOG_RETENTION_DAYS` (default 90); cleanup via scheduled task or pg_cron (future).

**Pagination**: Keyset pagination using `(created_at, id)` cursor. Example:
```sql
WHERE org_id = $1
  AND created_at < $cursor_created_at
  OR (created_at = $cursor_created_at AND id < $cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT 50
```

---

## Pydantic Schema Strategy

All Pydantic v2 models use `model_config = ConfigDict(from_attributes=True)` for ORM compatibility.

**Pattern**: separate `Create`, `Update`, `Response` schemas per entity. Passwords and key hashes excluded from all `Response` schemas via `model_fields_set` or `exclude`.

```python
# Example pattern
class ApiKeyCreate(BaseModel):
    name: str
    expires_at: datetime | None = None

class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    key_prefix: str      # e.g. "sk-abc123"
    is_active: bool
    created_at: datetime
    # key_hash: excluded always
    # plaintext: returned only in ApiKeyCreatedResponse (one-time)

class ApiKeyCreatedResponse(ApiKeyResponse):
    plaintext_key: str   # Only in creation response; never stored
```

---

## Alembic Migration Ordering

```
001_create_orgs.py          → orgs table
002_create_users.py         → users table (FK: orgs)
003_create_api_keys.py      → api_keys table (FK: orgs, users)
004_create_refresh_tokens.py → refresh_tokens table (FK: users)
005_create_model_registry.py → model_registry table
006_create_usage_logs.py    → usage_logs table (FK: orgs, api_keys, users, model_registry)
007_add_indexes.py          → all composite indexes (separate migration for clarity)
```

Each migration is additive. Rollback via `alembic downgrade -1` tested before merge.
