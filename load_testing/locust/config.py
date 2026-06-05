"""
InferVoyage Load Testing — Configuration
Environment-based config for all test scenarios.
"""
import os

# ── Target ───────────────────────────────────────────────────────────────────
HOST = os.getenv("LOCUST_HOST", "http://localhost:8000")

# ── Test Credentials ──────────────────────────────────────────────────────────
TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL", "loadtest@infervoyage.com")
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", "LoadTest@12345")
TEST_USER_NAME = os.getenv("TEST_USER_NAME", "Load Test User")

# For multi-tenant tests — org slugs for tenant isolation validation
TENANT_ORGS = [
    {"email": "tenant1@infervoyage.com", "password": "Tenant1@12345", "slug": "tenant-one"},
    {"email": "tenant2@infervoyage.com", "password": "Tenant2@12345", "slug": "tenant-two"},
    {"email": "tenant3@infervoyage.com", "password": "Tenant3@12345", "slug": "tenant-three"},
]

# ── Inference ─────────────────────────────────────────────────────────────────
MODEL_NAME = os.getenv("MODEL_NAME", "llama3")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "200"))
STREAM_TIMEOUT = int(os.getenv("STREAM_TIMEOUT", "180"))   # seconds
INFERENCE_TIMEOUT = int(os.getenv("INFERENCE_TIMEOUT", "180"))

# ── Performance Thresholds (used by CI pass/fail checks) ─────────────────────
THRESHOLD_P95_MS = int(os.getenv("THRESHOLD_P95_MS", "3000"))     # 3s for AI inference
THRESHOLD_P99_MS = int(os.getenv("THRESHOLD_P99_MS", "8000"))     # 8s for streaming
THRESHOLD_TTFT_MS = int(os.getenv("THRESHOLD_TTFT_MS", "2000"))   # 2s time-to-first-token
THRESHOLD_ERROR_RATE = float(os.getenv("THRESHOLD_ERROR_RATE", "0.02"))  # 2% max errors
THRESHOLD_RPS = int(os.getenv("THRESHOLD_RPS", "10"))             # Minimum sustained RPS

# ── Scenario Weights ─────────────────────────────────────────────────────────
# Controls how often each task is called relative to others
WEIGHT_LOGIN = int(os.getenv("WEIGHT_LOGIN", "5"))
WEIGHT_CHAT = int(os.getenv("WEIGHT_CHAT", "40"))
WEIGHT_STREAMING = int(os.getenv("WEIGHT_STREAMING", "35"))
WEIGHT_HEALTH = int(os.getenv("WEIGHT_HEALTH", "10"))
WEIGHT_ADMIN = int(os.getenv("WEIGHT_ADMIN", "10"))

# ── Scenario Prompts ─────────────────────────────────────────────────────────
SHORT_PROMPTS = [
    "What is machine learning?",
    "Explain REST APIs in one sentence.",
    "What is 15 * 17?",
    "Name three programming languages.",
    "What is the capital of France?",
    "Summarize TCP/IP in one line.",
    "What is a neural network?",
    "Define latency in computing.",
    "What is Docker used for?",
    "Explain what a token is in AI.",
]

MEDIUM_PROMPTS = [
    "Explain the difference between supervised and unsupervised machine learning with examples.",
    "What are the SOLID principles in software design? Give a brief explanation of each.",
    "How does JWT authentication work? Describe the token structure and validation flow.",
    "Compare Redis and Memcached as caching solutions. When would you choose one over the other?",
    "Explain database connection pooling and why it matters in high-concurrency applications.",
]

LARGE_PROMPTS = [
    (
        "You are a senior software architect. I need you to design a complete microservices "
        "architecture for an e-commerce platform that handles 100,000 concurrent users. "
        "Include service decomposition, data stores, API gateways, caching strategies, "
        "message queues, and observability. Provide a detailed explanation for each decision."
    ),
    (
        "Write a comprehensive guide on PostgreSQL performance tuning for production workloads. "
        "Cover indexing strategies, query optimization, connection pooling, autovacuum tuning, "
        "partitioning, and monitoring. Include specific configuration parameters and their impact."
    ),
]
