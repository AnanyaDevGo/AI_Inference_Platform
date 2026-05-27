# InferVoyage — Load and Performance Testing Framework

This directory contains the load testing and performance benchmarking suite for the **InferVoyage** AI inference platform. It validates API latency, concurrent model inference, streaming response performance, multi-tenant isolation, database pools, and Redis rate limiters under load.

---

## 🛠️ Framework Architecture

```
                       ┌──────────────────────┐
                       │    Locust Master     │ (Web UI: 8089)
                       └──────────┬───────────┘
                                  │ (Distributed protocol)
                   ┌──────────────┴──────────────┐
                   ▼                             ▼
         ┌───────────────────┐         ┌───────────────────┐
         │  Locust Worker 1  │         │  Locust Worker 2  │
         └─────────┬─────────┘         └─────────┬─────────┘
                   │                             │
                   └──────────────┬──────────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │    FastAPI API Gateway  │ (Port 8000 /metrics)
                    └────┬──────────────┬─────┘
                         │              │
                         ▼              ▼
                   ┌──────────┐   ┌───────────┐
                   │ Postgres │   │   Redis   │ (Rate Limiting)
                   └──────────┘   └───────────┘
                         ▲              ▲
                         │              │
                   ┌─────┴────┐   ┌─────┴─────┐
                   │  PG Exp  │   │ Redis Exp │ (Exporters)
                   └────┬─────┘   └─────┬─────┘
                        │               │
                        └───────┬───────┘
                                ▼
                    ┌─────────────────────────┐
                    │       Prometheus        │ (Port 9090)
                    └───────────┬─────────────┘
                                ▼
                    ┌─────────────────────────┐
                    │         Grafana         │ (Port 3001)
                    └─────────────────────────┘
```

---

## 📂 Folder Structure

- **`locust/`**: Contains the main Python load testing scenarios.
  - `locustfile.py`: Entry point registering user classes and printing summaries.
  - `config.py`: Thresholds, prompts, and scenario weights.
  - `scenarios/`: Task sets:
    - `auth_tasks.py`: Registration, OTP mail sandbox verification, login, JWT refresh.
    - `chat_tasks.py`: Non-streaming and streaming completion tasks with TTFT tracking.
    - `inference_tasks.py`: Raw Ollama request validation, latency tracking.
    - `multi_tenant_tasks.py`: Cross-tenant data isolation and performance validation.
    - `admin_tasks.py`: Super Admin CRUD and key generation queries.
  - `utils/`: Reusable helpers for authentication and payload generation.
- **`k6/`**: Light-weight JS-based smoke testing tool.
- **`docker-compose.loadtest.yml`**: Docker composition for distributed Locust workers.

---

## 🚀 Getting Started

### Prerequisites
- Docker & Docker Compose
- Native Ollama running on host (`http://localhost:11434`) with `llama3` pulled:
  ```bash
  ollama pull llama3
  ```

---

## 🏃 Running the Load Tests

### Option A: Locust GUI (Recommended for Interactive Testing)

1. **Start the platform and all exporters**:
   ```bash
   docker compose up -d
   ```
2. **Start the Locust master & workers**:
   ```bash
   docker compose -f docker-compose.yml -f load_testing/docker-compose.loadtest.yml up --scale locust-worker=4 locust-master locust-worker
   ```
3. Open **[http://localhost:8089](http://localhost:8089)** in your browser.
4. Enter target host: `http://api:8000`.
5. Enter number of users (e.g., `20`) and spawn rate (e.g., `2`).
6. Click **Start swarming**.

### Option B: Headless Execution (CI/CD / Scripted)

To run a headless benchmark for 3 minutes and write reports directly to the `locust/reports` folder:
```bash
docker compose -f docker-compose.yml -f load_testing/docker-compose.loadtest.yml run --rm locust-master \
  --headless --users 30 --spawn-rate 3 --run-time 3m \
  --html /reports/report.html --csv /reports/stats
```

### Option C: Running the k6 Smoke Test
`k6` is included for fast, lightweight HTTP smoke testing:
```bash
# Run using local k6 install or docker container
docker run --rm -i --network=inference_platform grafana/k6 run - < load_testing/k6/smoke_test.js
```

---

## 📈 Monitoring & Observability

While the load tests run, the platform exports metrics into Prometheus, which are visualized inside Grafana.

- **Prometheus UI**: [http://localhost:9090](http://localhost:9090)
- **Grafana Dashboards**: [http://localhost:3001](http://localhost:3001) (Credentials: `admin`/`admin`)

### Built-in Provisioned Dashboards

1. **API Performance** (`api-perf`): Tracks HTTP requests/sec, status code breakdown, endpoints latency (P50, P90, P95, P99), and active client connections.
2. **AI Inference Performance** (`inference-perf`): Tracks **Time to First Token (TTFT)**, total generation duration, token throughput (tokens/sec), active Ollama concurrent queues, and model-level request counts.
3. **PostgreSQL Metrics** (`db-metrics`): Connection pool occupancy, transaction rate, average query duration, and deadlocks.
4. **Redis Metrics** (`redis-metrics`): Caching command ops/sec, memory usage vs limit, connected clients, and key eviction counts.
5. **System Container Overview** (`system-overview`): Container CPU/Memory limits, network I/O per service, and Host CPU load.
6. **Locust Live Stats** (`locust-live`): Visualizes live load testing throughput, failures, and concurrency stats.

---

## 🎯 Custom Metrics & Benchmarking

### Time to First Token (TTFT)
During streaming completions, the client measures the wall-clock time from request transmission until the first content token is received via SSE.
- Exposed as a Prometheus histogram `inference_ttft_seconds`
- Tracked inside the `inference-perf` Grafana dashboard

### Percentile Latency Analysis
Locust reports `50%`, `90%`, `95%`, `99%` and `Max` response times for all API endpoints. The custom inference user tracks metrics directly to print a comprehensive summary of LLM response distribution once the swarm completes:
```
  --- Inference Latency (custom tracker) ---
  P50 : 1240 ms
  P90 : 2810 ms
  P95 : 3450 ms
  P99 : 5100 ms
```

---

## ⚠️ Autoscaling & Tuning Recommendations

Based on the performance metrics generated during swarms, consider the following thresholds and actions:

- **High P95 TTFT (> 5s)**:
  - *Cause*: Ollama inference is CPU-bound or queue depth is too high.
  - *Action*: Scale up CPU allocation or add replicas. Consider using a 4-bit quantized model (e.g. `llama3:8b-instruct-q4_K_M`) to reduce context loading overhead.
- **PostgreSQL Pool Exhaustion**:
  - *Cause*: Concurrent connections from API exceed `pool_size` (default 20).
  - *Action*: Increase `DATABASE_POOL_SIZE` in backend configuration and update PostgreSQL's `max_connections` parameter.
- **429 Rate-Limit Spikes**:
  - *Cause*: Org rate limits are configured too low.
  - *Action*: Adjust tenant organization limits (`rate_limit_rpm` / `rate_limit_burst`) inside the Admin panel or database.
