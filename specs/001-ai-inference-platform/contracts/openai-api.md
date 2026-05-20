# Contract: OpenAI-Compatible Inference API

**Phase 1 output** | Feature: `001-ai-inference-platform`

All inference endpoints are under `/v1` to match OpenAI API path conventions. Auth: Bearer token (JWT) **or** `Authorization: Bearer sk-<api-key>`.

---

## POST /v1/chat/completions

Submit a chat completion request. Supports both blocking and streaming modes.

**Auth required**: Yes (JWT or API key). Role required: `operator`, `org_admin`, `platform_admin`.

**Rate limiting**: Applied per API key using token-bucket algorithm before forwarding to Ollama.

### Request

```json
{
  "model": "llama3:8b-q4_K_M",
  "messages": [
    { "role": "system", "content": "You are a helpful assistant." },
    { "role": "user", "content": "Explain CPU inference in one paragraph." }
  ],
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 512,
  "top_p": 0.95
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | ✅ | Must match `model_registry.name` |
| `messages` | array | ✅ | At least one message required |
| `stream` | boolean | ❌ | Default: `false` |
| `temperature` | float | ❌ | 0.0–2.0, default 0.7 |
| `max_tokens` | integer | ❌ | Default 512, max per model context window |
| `top_p` | float | ❌ | 0.0–1.0, default 0.95 |

### Response 200 — Non-streaming

```json
{
  "id": "chatcmpl-uuid",
  "object": "chat.completion",
  "created": 1715590800,
  "model": "llama3:8b-q4_K_M",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "CPU inference uses..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 28,
    "completion_tokens": 120,
    "total_tokens": 148
  }
}
```

### Response 200 — Streaming (`stream: true`)

`Content-Type: text/event-stream`

```
data: {"id":"chatcmpl-uuid","object":"chat.completion.chunk","created":1715590800,"model":"llama3:8b-q4_K_M","choices":[{"index":0,"delta":{"role":"assistant","content":"CPU"},"finish_reason":null}]}

data: {"id":"chatcmpl-uuid","object":"chat.completion.chunk","created":1715590800,"model":"llama3:8b-q4_K_M","choices":[{"index":0,"delta":{"content":" inference"},"finish_reason":null}]}

data: [DONE]
```

### Error Responses

| Status | Code | Condition |
|--------|------|-----------|
| 400 | `validation_error` | Invalid request schema |
| 401 | `unauthorized` | Missing/invalid auth |
| 403 | `forbidden` | Insufficient role |
| 404 | `not_found` | Model not in registry |
| 422 | `model_not_loaded` | Model registered but not loaded in Ollama |
| 429 | `rate_limit_exceeded` | Token bucket exhausted |
| 503 | `inference_unavailable` | Ollama unreachable |
| 504 | `inference_timeout` | Response exceeded `INFERENCE_TIMEOUT_SECONDS` |

---

## GET /v1/models

List all enabled models registered in the platform, with their current status from Ollama.

**Auth required**: Yes. Role required: any authenticated user.

**Response 200**
```json
{
  "object": "list",
  "data": [
    {
      "id": "llama3:8b-q4_K_M",
      "object": "model",
      "display_name": "Llama 3 8B (Q4_K_M)",
      "status": "loaded",
      "context_window": 8192,
      "quantization": "Q4_K_M",
      "created": 1715590800
    }
  ]
}
```

---

## GET /v1/models/{model_name}

Get detail for a single model.

**Response 200**: Single model object (same schema as above).
**Response 404**: Model not found in registry.

---

## POST /v1/models/{model_name}/load

Request Ollama to load (warm) the model. Operator or platform-admin only.

**Auth**: Bearer. Role: `operator`, `platform_admin`.

**Response 202**
```json
{ "model": "llama3:8b-q4_K_M", "status": "loading", "message": "Load request submitted to inference engine" }
```

---

## POST /v1/models/{model_name}/unload

Request Ollama to unload the model from memory. Operator or platform-admin only.

**Response 202**
```json
{ "model": "llama3:8b-q4_K_M", "status": "unloaded", "message": "Unload request submitted" }
```

---

## GET /health

Platform health check. No auth required. Used by Docker Compose `healthcheck`.

**Response 200**
```json
{
  "status": "ok",
  "ollama": "reachable",
  "database": "ok",
  "redis": "ok",
  "version": "1.0.0"
}
```

**Response 503** — any dependency unhealthy
```json
{
  "status": "degraded",
  "ollama": "unreachable",
  "database": "ok",
  "redis": "ok"
}
```

---

## GET /metrics

Prometheus metrics scrape endpoint. No auth required (firewalled at network level). Returns text/plain Prometheus exposition format.
