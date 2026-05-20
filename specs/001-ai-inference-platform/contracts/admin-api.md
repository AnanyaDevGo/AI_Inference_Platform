# Contract: Admin API

**Phase 1 output** | Feature: `001-ai-inference-platform`

All admin endpoints are under `/v1/admin`. Auth: Bearer JWT only (not API keys). Role enforcement is per-endpoint as documented.

---

## Organizations

### GET /v1/admin/orgs

List all organizations. **Role**: `platform_admin` only.

**Response 200**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "Acme Corp",
      "slug": "acme-corp",
      "is_active": true,
      "rate_limit_rpm": 60,
      "rate_limit_burst": 10,
      "created_at": "2026-05-13T00:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### POST /v1/admin/orgs

Create a new organization. **Role**: `platform_admin` only.

**Request**
```json
{
  "name": "Acme Corp",
  "slug": "acme-corp",
  "rate_limit_rpm": 60,
  "rate_limit_burst": 10
}
```

**Response 201**: Full org object.

### PATCH /v1/admin/orgs/{org_id}

Update org settings (rate limits, active status). **Role**: `platform_admin` only.

**Request**: Any subset of `rate_limit_rpm`, `rate_limit_burst`, `is_active`.

**Response 200**: Updated org object.

---

## Users

### GET /v1/admin/users

List users. **Role**: `platform_admin` (all orgs), `org_admin` (own org only).

**Query params**: `org_id` (platform_admin only), `role`, `is_active`, `page`, `page_size`

**Response 200**: Paginated list of user objects. Password hash never included.

### POST /v1/admin/users

Create a new user. **Role**: `platform_admin` (any org), `org_admin` (own org, max role: `operator`).

**Request**
```json
{
  "email": "newuser@example.com",
  "password": "secure-password-min-12-chars",
  "role": "operator",
  "org_id": "uuid"
}
```

**Response 201**
```json
{
  "id": "uuid",
  "email": "newuser@example.com",
  "role": "operator",
  "org_id": "uuid",
  "is_active": true,
  "created_at": "2026-05-13T00:00:00Z"
}
```

**Validation**:
- Password minimum 12 characters
- `org_admin` cannot create `org_admin` or `platform_admin` roles
- Email must be unique within org

### PATCH /v1/admin/users/{user_id}

Update user. **Role**: `platform_admin`, `org_admin` (own org only).

**Request**: Any subset of `role`, `is_active`. Cannot change `email` or `org_id`.

### DELETE /v1/admin/users/{user_id}

Soft-delete (sets `is_active: false`). **Role**: `platform_admin`, `org_admin` (own org only). Cannot delete self.

**Response 204**: No content.

---

## API Keys

### GET /v1/admin/api-keys

List API keys for the current org. **Role**: `platform_admin`, `org_admin`.

**Response 200**
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "CI Pipeline Key",
      "key_prefix": "sk-abc123",
      "is_active": true,
      "created_at": "2026-05-13T00:00:00Z",
      "last_used_at": "2026-05-13T08:00:00Z",
      "expires_at": null
    }
  ],
  "total": 3
}
```

**Note**: `key_hash` and plaintext are never returned in list/get responses.

### POST /v1/admin/api-keys

Create a new API key. **Role**: `platform_admin`, `org_admin`.

**Request**
```json
{
  "name": "CI Pipeline Key",
  "expires_at": null
}
```

**Response 201** — plaintext key returned ONCE, never again:
```json
{
  "id": "uuid",
  "name": "CI Pipeline Key",
  "key_prefix": "sk-abc123",
  "plaintext_key": "sk-abc123def456ghi789jkl012mno345pqr678stu",
  "is_active": true,
  "created_at": "2026-05-13T00:00:00Z",
  "expires_at": null
}
```

### DELETE /v1/admin/api-keys/{key_id}

Revoke an API key (sets `is_active: false`). **Role**: `platform_admin`, `org_admin` (own org only).

**Response 204**: No content. Key rejected immediately on next use.

---

## Usage Logs

### GET /v1/usage

Query usage logs. **Role**: `platform_admin` (any org), `org_admin`/`operator`/`viewer` (own org only).

**Query params**:

| Param | Type | Notes |
|-------|------|-------|
| `org_id` | UUID | platform_admin only |
| `start_date` | date | ISO 8601 |
| `end_date` | date | ISO 8601 |
| `model` | string | Filter by model name |
| `api_key_id` | UUID | Filter by key |
| `cursor` | string | Opaque pagination cursor |
| `limit` | int | Default 50, max 200 |

**Response 200**
```json
{
  "items": [
    {
      "id": "uuid",
      "org_id": "uuid",
      "api_key_id": "uuid",
      "model_name": "llama3:8b-q4_K_M",
      "prompt_tokens": 28,
      "completion_tokens": 120,
      "total_tokens": 148,
      "duration_ms": 12450,
      "ttft_ms": 890,
      "status": "success",
      "created_at": "2026-05-13T08:30:00Z"
    }
  ],
  "next_cursor": "base64encodedcursor",
  "has_more": true
}
```

### GET /v1/usage/summary

Aggregated token counts grouped by day and model. Used for dashboard charts.

**Query params**: `start_date`, `end_date`, `org_id` (platform_admin only).

**Response 200**
```json
{
  "period": { "start": "2026-05-01", "end": "2026-05-13" },
  "total_tokens": 458200,
  "total_requests": 312,
  "by_day": [
    { "date": "2026-05-13", "tokens": 12450, "requests": 18 }
  ],
  "by_model": [
    { "model": "llama3:8b-q4_K_M", "tokens": 458200, "requests": 312 }
  ]
}
```
