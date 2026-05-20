# Operations Runbook

This guide covers common operational tasks for the AI Inference Platform.

## 1. Cold Start Procedure

**Goal:** Start the entire platform from a completely stopped state in under 5 minutes.

1. **Verify Ollama is running:**
   ```bash
   # On host machine
   ollama serve
   ```
2. **Pre-warm the target model:**
   ```bash
   ollama run llama3.2:3b ""
   ```
   *Note: Pre-warming loads the model into RAM/VRAM, eliminating the 10-30s "first request" delay.*
3. **Start the Docker Stack:**
   ```bash
   docker compose up -d
   ```
4. **Verify Health Checks:**
   ```bash
   docker compose ps
   # Ensure all containers report "healthy"
   ```

## 2. Model Swapping

**Goal:** Change the model used for inference.

1. **Pull the new model on the host:**
   ```bash
   ollama pull new-model-name
   ```
2. **Pre-warm the new model:**
   ```bash
   ollama run new-model-name ""
   ```
3. **Update client applications:**
   Ensure that any application making requests to the `/v1/chat/completions` endpoint updates the `"model"` field in their JSON payload to `new-model-name`.

## 3. Key Rotation

**Goal:** Invalidate a compromised or stale API key and issue a new one.

**Via the Admin UI:**
1. Navigate to **http://localhost** and sign in as an Admin or Team Lead.
2. Go to the **API Keys** tab.
3. Locate the key to rotate and click **Rotate**.
4. Securely copy the newly generated plaintext key and update it in your client applications. 
   *(Warning: The old key will immediately return 401 Unauthorized).*

**Via the API directly:**
```bash
curl -X POST http://localhost/admin/api-keys/{key_id}/rotate \
  -H "Authorization: Bearer <JWT_TOKEN>"
```

## 4. Disaster Recovery

**Goal:** Recover from corrupted state or completely reset the environment.

1. **Destroy all containers and volumes:**
   ```bash
   docker compose down -v
   ```
   *WARNING: This deletes the PostgreSQL database, Redis cache, and all Grafana/Prometheus data!*
2. **Re-initialize:**
   Follow the Cold Start Procedure. The backend API container will automatically run Alembic migrations on startup to recreate the database tables.
