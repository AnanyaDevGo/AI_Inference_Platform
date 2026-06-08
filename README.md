# InferVoyage (AI Inference Platform)

InferVoyage is a single-host, CPU-native AI inference serving platform exposing an OpenAI-compatible API, backed by Ollama + llama.cpp using GGUF quantized models. It is designed to provide a highly secure, scalable, and self-hosted alternative to proprietary LLM APIs for development teams and local developers.

---

## 🏗️ System Architecture & Routing

```
                              [ User Client ]
                                     │
                                     ▼ (Port 80 / 443 / 8443)
                         [ Ingress / Reverse Proxy ]
                        (TLS Offloading & Rate Limiting)
                                     │
              ┌──────────────────────┴──────────────────────┐
              │ / (React Web App)                           │ /v1 & /auth (FastAPI)
              ▼                                             ▼
    [ Frontend Service ]                             [ API Gateway Service ]
     (Caddy / Nginx)                                    (FastAPI Backend)
              │                                             │
              └─────────────── (Internal Communication) ────┼──────────────┐
                                                            │              │
                                                            ▼              ▼
                                                     [ Postgres DB ]  [ Redis Cache ]
                                                      (SQL Storage)   (OTP / Rate Limit)
                                                            │
                                                            ▼
                                                    [ Ollama Service ]
                                                 (GGUF quantized models)
```

---

## 🚀 Key Features

### 1. OpenAI-Compatible Inference
* **API Compatibility:** Exposes endpoints like `/v1/chat/completions` and `/v1/models` matching the OpenAI spec. Supports both single-response and streaming (SSE) response modes.
* **Quantized Model Support:** Run CPU-friendly quantized GGUF models (e.g., `llama3.2:3b`, `gemma2:2b`) via Ollama.
* **Auto Model Pulling:** Optional startup routine that auto-pulls default models if they are not already installed.
* **Performance Metrics:** Measures and logs Time-To-First-Token (TTFT) and total prompt/completion tokens for all requests.

### 2. Multi-Tenancy & Role-Based Access Control (RBAC)
* **Organization Isolation:** Hard boundaries between tenants. All queries are implicitly filtered by `org_id`, preventing any cross-organization data leakage.
* **Four-Tiered Access Control:**
  * **Super Admin (`platform_admin`):** Full control over all organizations, users, and global configurations.
  * **Org Admin (`org_admin`):** Manage users and API keys inside their respective organization.
  * **Team Lead (`team_lead`):** Scoped access to create keys and view metrics/usage logs.
  * **User / Operator (`user` / `operator` / `viewer`):** Scoped access to chat completions, history, or read-only metrics dashboards.

### 3. Advanced Authentication & Security
* **JWT & API Key Verification:** Double authentication layer. Users utilize JWT tokens with automatic rotation, and external apps utilize cryptographic API keys.
* **API Key Rotation:** API keys are stored only as SHA-256 hashes. Plaintext keys are shown once during creation or rotation, and old keys are instantly invalidated.
* **Double-OTP Verification System:**
  * Registering or resetting passwords sends a 6-digit OTP code to the user's email.
  * **Google Sign-In (`/auth/google`):** Initiates OAuth sign-ups, issuing verification tokens and sending registration OTPs.
  * **Rate Limiting on OTPs:** Max 3 OTP requests / resends within a 15-minute window per email.
  * **Lockout Protection:** Accounts are locked after 5 consecutive failed OTP verification attempts.
  * **Setup Password:** Allows third-party OAuth (e.g., Google) registered users to set a local password for email login.

### 4. Conversation & Chat History
* **Database Persistence:** Full conversation sessions and chat messages storage.
* **Message Truncation:** Ability to delete a message and automatically truncate/delete all messages that follow it in a conversation stream to correct and restart chat flows.

### 5. Cascading Deletions & Self-Healing
* **Cascade Deletes:**
  * Deleting a user automatically invalidates their API keys, deletes their conversations/messages, and nullifies references in usage logs.
  * Deleting an organization cascades to wipe the org, its users, keys, conversations, and usage logs cleanly.
* **Self-Healing Schema Migrations:** On backend startup, the lifecycle routine dynamically checks and updates schema constraints (e.g., table updates for `otps` and `conversations` tables) without manual intervention.

### 6. Observability & Monitoring
* **Structured JSON Logging:** Fully structured `structlog` formatted JSON logs containing request correlation IDs, user IDs, and organization IDs.
* **Prometheus Integration:** Custom instrumentation `/metrics` capturing request counters, latency percentiles (P50/P95/P99), and rate-limit triggers.
* **Grafana Dashboards:** Beautiful out-of-the-box dashboards tracking inference throughput, error rates, TTFT, and active model count.

---

## 📂 Project Structure

```text
AI_Inference_Platform/
├── backend/                       # FastAPI Backend Application
│   ├── alembic/                   # Database migrations
│   ├── app/                       # Core backend code
│   │   ├── models/                # SQLAlchemy database models
│   │   ├── routers/               # API controllers (auth, admin, inference, etc.)
│   │   ├── services/              # Business logic (auth, OTP, rate-limiting, models)
│   │   ├── middleware/            # Error handling, logging, correlation IDs
│   │   └── observability/         # Prometheus metrics and structlog settings
│   └── tests/                     # Unit & Integration pytest files
├── frontend/                      # React Admin Web Interface (Vite, TS, Zustand)
│   ├── src/
│   │   ├── pages/                 # Admin, Chat, Login, Register pages
│   │   └── stores/                # Client state management (Zustand)
│   └── Caddyfile                  # Server config for serving static web files
├── deploy/                        # Production & Cluster Deployments
│   ├── kubernetes/                # Native K8s manifests (postgres, redis, api, ingress)
│   └── helm/                      # Parameterized charts for Kubernetes deployments
├── load_testing/                  # Load and stress testing configurations
│   ├── locust/                    # Distributed Locust files
│   └── k6/                        # K6 stress testing scripts
├── specs/                         # Project specifications and plan docs
└── *.sh / *.ps1                   # Local automation & verification scripts
```

---

## 🚀 Quickstart (Local Docker Compose)

### 1. Start Ollama Natively
Download and install [Ollama](https://ollama.com). Then, pull and pre-warm a model:
```bash
ollama pull llama3.2:3b
ollama run llama3.2:3b ""
```

### 2. Configure Environment
Clone `.env.example` to `.env` and fill in the required variables (specifically `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, and `OLLAMA_BASE_URL`):
```bash
cp .env.example .env
```

### 3. Deploy the Stack
Launch the containers via Docker Compose:
```bash
docker compose up -d
docker compose ps
```

* Navigate to the Admin UI: **http://localhost**
* Default platform-admin credentials: `admin@platform.local` / `password123`
* Prometheus: **http://localhost:9090**
* Grafana: **http://localhost:3001**

---

## 🧪 Testing and Verification

The repository contains several layers of automated and script-based tests to verify functionality from low-level unit code to end-to-end user journeys.

### 1. Pytest Test Suite
Located in `backend/tests/`, these can be executed within the API container or locally:
```bash
# Executing within Docker Compose container
docker compose exec api pytest tests/ -v
```

* **Unit Tests:**
  * [test_openai_engine.py](file:///c:/Users/AnanyaPradeep/AI_Inference_Platform/backend/tests/unit/test_openai_engine.py): Validates chat completions, SSE streaming formatting, and HTTP clients.
* **Integration Tests:**
  * [test_conversations.py](file:///c:/Users/AnanyaPradeep/AI_Inference_Platform/backend/tests/integration/test_conversations.py): Verifies conversation management and message truncation/deletion.
  * [test_inference.py](file:///c:/Users/AnanyaPradeep/AI_Inference_Platform/backend/tests/integration/test_inference.py): Integration with Ollama APIs, token counting, and database writes.
  * [test_reliability.py](file:///c:/Users/AnanyaPradeep/AI_Inference_Platform/backend/tests/integration/test_reliability.py): Checks token bucket rate-limiting algorithms and Redis degradation fallback.
  * [test_security_hardening.py](file:///c:/Users/AnanyaPradeep/AI_Inference_Platform/backend/tests/integration/test_security_hardening.py): Verifies RBAC role gating, API key creation/rotation, and cross-org access protection.

### 2. Python Integration & Validation Scripts
Run these scripts to verify advanced security logic against a running platform (Nginx Ingress / Localhost):

* **[test_new_auth_flow.py](file:///c:/Users/AnanyaPradeep/AI_Inference_Platform/test_new_auth_flow.py):**
  * Verifies Google sign-in creates an unverified account.
  * Checks verification token extraction from logs (Mailpit/K8s).
  * Validates setup-password and credential login.
  * Asserts Forgot Password secure response (doesn't leak account existence).
  * Tests OTP resend rate-limiting (Max 3 in 15 mins → 400 Bad Request).
  * Tests verification lockout (5 failed attempts → locks account out).
  * Validates platform-admin user and organization cascading deletions.
  ```bash
  python test_new_auth_flow.py
  ```

* **[test_new_endpoints.py](file:///c:/Users/AnanyaPradeep/AI_Inference_Platform/test_new_endpoints.py):**
  * Verifies OTP password reset flow.
  * Verifies Google registration OTP flows.
  * Verifies message truncation API (deleting a message deletes everything after it and shifts positions).
  ```bash
  python test_new_endpoints.py
  ```

* **[test_roles.py](file:///c:/Users/AnanyaPradeep/AI_Inference_Platform/test_roles.py):**
  * Creates an admin, registration under Stark Ind, and normal employee registration.
  * Verifies correct role claims (`platform_admin`, `org_admin`, `user`) are baked into issued JWTs.
  ```bash
  python test_roles.py
  ```

### 3. Bash E2E Verification Scripts
These scripts use `curl` commands to test key backend operations:
* `test_backend.sh`: Registers a test user, verifies DB connection and health via Nginx.
* `test_e2e.sh`: Runs full register, login, and frontend static asset fetch check.
* `test_inference.sh`: Performs test chat completions (non-streaming and streaming) via curl.
* `test_conversations.sh`: Creates conversations and tests adding messages.
* `test_admin.sh`: Tests administrative operations.
* `test_custom_org.sh`: Checks org isolation rules.

### 4. Load Testing
Located under `load_testing/`:
* **Locust:** Simulate concurrent users streaming text completions. Runs locally or in a distributed master/worker setup in K8s.
* **K6:** Custom JS files under `load_testing/k6/` to stress-test APIs and measure rate-limiting responses under heavy concurrency.

---

## ☸️ Kubernetes-Native Deployment (InferVoyage)

InferVoyage is fully prepared for multi-tenant, cloud, or on-premise Kubernetes environments.

### Raw Manifests
Stored under `deploy/kubernetes/`:
* `namespaces.yaml`: Isolation of environments (`dev`, `staging`, `prod`).
* `postgres/` & `redis/`: StatefulSet and Deployment configurations with Prometheus metrics sidecars (`postgres-exporter`, `redis-exporter`).
* `ollama/`: Scalable HPAs and model storage PVs. Includes switches for GPU resources.
* `api/` & `frontend/`: Container deployments, secrets mappings, configmaps.
* `ingress/`: Nginx Ingress with SSL/TLS termination and host routing rules.
* `locust/`: Dynamic master/worker load testing setup.
* `observability/`: ServiceMonitor files for Prometheus operator integrations.

### Helm Chart Deployments
A fully parameterized Helm chart is located under `deploy/helm/infervoyage/`.
```bash
# Dry run deployment verification
helm install infervoyage-dev deploy/helm/infervoyage -f deploy/helm/infervoyage/values.yaml --dry-run

# Deploy to Dev namespace
helm upgrade --install infervoyage-dev deploy/helm/infervoyage --namespace infervoyage-dev --create-namespace
```

---

## 🛠️ Operations Runbook Summary

Detailed operations procedures can be found in [runbook.md](file:///c:/Users/AnanyaPradeep/AI_Inference_Platform/runbook.md).
* **Cold Start:** Serve Ollama, pre-warm models using `ollama run <model> ""`, and spin up the Docker compose stack.
* **Model Swapping:** Pull the new model via Ollama CLI, pre-warm, and direct API client queries to point to the new model string.
* **Key Rotation:** Instantly rotate a team's compromised or legacy API key via the Admin UI key rotation actions or Direct API endpoint `POST /admin/api-keys/{key_id}/rotate`.
* **Disaster Recovery:** Wipe cache and state using `docker compose down -v` and re-initiate startup; migrations will auto-provision clean PostgreSQL schemas.
