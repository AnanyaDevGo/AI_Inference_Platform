# Contract: Auth API

**Phase 1 output** | Feature: `001-ai-inference-platform`

All auth endpoints are under `/auth`. No versioning prefix — these are platform-internal endpoints.

---

## POST /auth/login

Authenticate with email + password. Returns access token in body; sets refresh token as `httpOnly` cookie.

**Request**
```json
{
  "email": "user@example.com",
  "password": "plaintext-password"
}
```

**Response 200**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}
```
Sets: `Set-Cookie: refresh_token=<token>; HttpOnly; SameSite=Strict; Path=/auth/refresh`

**Response 401** — invalid credentials
```json
{ "error": { "code": "invalid_credentials", "message": "Invalid email or password" } }
```

**Notes**:
- Rate-limited to 10 requests/minute per IP to prevent brute force
- Timing is constant regardless of whether email exists (prevent user enumeration)

---

## POST /auth/refresh

Exchange a valid refresh token (from cookie) for a new access token. Rotates the refresh token (old one invalidated).

**Request**: No body. Reads `refresh_token` from `httpOnly` cookie.

**Response 200**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}
```
Sets: new `refresh_token` cookie (old invalidated in DB).

**Response 401** — expired or revoked refresh token
```json
{ "error": { "code": "token_expired", "message": "Refresh token expired or revoked" } }
```

---

## POST /auth/logout

Revoke the current refresh token. Clears cookie.

**Request**: No body. Auth: Bearer access token in `Authorization` header.

**Response 204**: No content. Clears `refresh_token` cookie.

---

## GET /auth/me

Return the current authenticated user's profile.

**Auth**: Bearer access token.

**Response 200**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "role": "org_admin",
  "org_id": "uuid",
  "org_name": "My Organization",
  "is_active": true
}
```

---

## Standard Error Envelope

All error responses follow this structure:

```json
{
  "error": {
    "code": "machine_readable_code",
    "message": "Human-readable description",
    "request_id": "uuid"
  }
}
```

| HTTP Status | Code | When |
|-------------|------|------|
| 400 | `validation_error` | Request body fails schema validation |
| 401 | `unauthorized` | Missing or invalid token/key |
| 401 | `token_expired` | JWT or refresh token expired |
| 401 | `invalid_credentials` | Wrong email/password |
| 403 | `forbidden` | Authenticated but insufficient role |
| 403 | `cross_org_access` | Attempt to access another org's data |
| 404 | `not_found` | Resource does not exist |
| 429 | `rate_limit_exceeded` | Token bucket exhausted |
| 503 | `inference_unavailable` | Ollama unreachable |
| 504 | `inference_timeout` | Ollama did not respond within timeout |
| 500 | `internal_error` | Unexpected server error |

Rate-limit 429 response includes additional headers:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1715590800
Retry-After: 42
```
