from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ── Inference metrics ───────────────────────────────────────────────────────

INFERENCE_REQUESTS_TOTAL = Counter(
    "inference_requests_total",
    "Total number of inference requests",
    ["org_id", "model", "status"],
)

INFERENCE_DURATION_SECONDS = Histogram(
    "inference_duration_seconds",
    "Wall-clock duration of inference requests in seconds",
    ["org_id", "model"],
    # CPU inference is slow — buckets tuned accordingly
    buckets=[1, 5, 10, 20, 30, 45, 60, 90, 120, float("inf")],
)

INFERENCE_TTFT_SECONDS = Histogram(
    "inference_ttft_seconds",
    "Time to first token for streaming inference requests in seconds",
    ["org_id", "model"],
    buckets=[0.5, 1, 2, 5, 10, 15, 20, 30, 45, float("inf")],
)

INFERENCE_TOKENS_TOTAL = Counter(
    "inference_tokens_total",
    "Total tokens processed",
    ["org_id", "model", "token_type"],  # token_type: prompt | completion
)

# ── Rate limiting metrics ───────────────────────────────────────────────────

RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "rate_limit_rejections_total",
    "Total number of requests rejected by rate limiter",
    ["org_id"],
)

# ── Auth metrics ────────────────────────────────────────────────────────────

AUTH_FAILURES_TOTAL = Counter(
    "auth_failures_total",
    "Total authentication failures",
    ["reason"],  # reason: invalid_credentials | token_expired | invalid_key | revoked_key
)

# ── Model metrics ───────────────────────────────────────────────────────────

ACTIVE_MODELS_COUNT = Gauge(
    "active_models_count",
    "Number of models currently loaded in Ollama",
)

# ── HTTP metrics (supplementing prometheus-fastapi-instrumentator) ──────────

HTTP_REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Number of HTTP requests currently being processed",
)
