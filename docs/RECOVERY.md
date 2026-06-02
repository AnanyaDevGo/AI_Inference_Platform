# Disaster Recovery & System Stability Playbook

This document details the standard operating procedures (SOPs) for backing up, restoring, and managing the InferVoyage AI Inference Platform dependencies, as well as configuring email DNS authentication (SPF, DKIM, DMARC) to ensure reliable OTP delivery.

---

## 1. Database Backup & Restore (PostgreSQL)

The platform uses a PostgreSQL database instance running as a StatefulSet: `infervoyage-dev-postgres-0` in namespace `infervoyage-dev`.

### 1.1 Creating a Database Backup
To create a complete backup (SQL format) of the `inference_platform` database from the local host:

```bash
# Export schema and data to a local file
kubectl exec -t -n infervoyage-dev infervoyage-dev-postgres-0 -- pg_dump -U appuser -d inference_platform > backup_$(date +%F).sql
```

For binary-compressed format (recommended for larger databases to enable parallel restores):
```bash
kubectl exec -t -n infervoyage-dev infervoyage-dev-postgres-0 -- pg_dump -U appuser -d inference_platform -F c -b -v -f /tmp/backup.dump
kubectl cp infervoyage-dev/infervoyage-dev-postgres-0:/tmp/backup.dump ./backup_$(date +%F).dump
```

### 1.2 Restoring a Database Backup
To restore a plain SQL dump into a clean/fresh database instance:

1. **(Optional) Recreate the Database**:
   ```bash
   kubectl exec -it -n infervoyage-dev infervoyage-dev-postgres-0 -- psql -U appuser -d postgres -c "DROP DATABASE IF EXISTS inference_platform;"
   kubectl exec -it -n infervoyage-dev infervoyage-dev-postgres-0 -- psql -U appuser -d postgres -c "CREATE DATABASE inference_platform WITH OWNER appuser;"
   ```

2. **Apply the Backup SQL file**:
   ```bash
   kubectl exec -i -n infervoyage-dev infervoyage-dev-postgres-0 -- psql -U appuser -d inference_platform < backup_XXXX-XX-XX.sql
   ```

3. **Restore from Binary Format (`pg_restore`)**:
   ```bash
   kubectl cp ./backup_XXXX-XX-XX.dump infervoyage-dev/infervoyage-dev-postgres-0:/tmp/restore.dump
   kubectl exec -it -n infervoyage-dev infervoyage-dev-postgres-0 -- pg_restore -U appuser -d inference_platform -v /tmp/restore.dump
   ```

---

## 2. Redis Cache & Rate-Limiter Recovery

Redis is used for token blacklist storage, session caching, and API rate-limiting coordinates. 

### 2.1 Checking Redis Health & Clients
```bash
kubectl exec -it -n infervoyage-dev deploy/infervoyage-dev-redis -- redis-cli ping
kubectl exec -it -n infervoyage-dev deploy/infervoyage-dev-redis -- redis-cli info clients
```

### 2.2 Purging/Flushing Cache
If rate limit locks occur or stale metadata triggers failures, you can safely flush the Redis cache:
```bash
# Flush all keys (non-destructive to persistent PostgreSQL data)
kubectl exec -it -n infervoyage-dev deploy/infervoyage-dev-redis -- redis-cli flushall
```

---

## 3. Ollama Storage & Model Restoration

Models are stored on a Persistent Volume Claim (PVC) mounted to the Ollama deployment at `/root/.ollama`.

### 3.1 Verifying Cached Models
```bash
kubectl exec -it -n infervoyage-dev deploy/infervoyage-dev-ollama -- ollama list
```

### 3.2 Manual Model Restoration
If a volume is wiped, the API container automatically pulls default models (`gemma2:2b` and `llama3.2`) on startup. You can also manually trigger a background pull:
```bash
kubectl exec -it -n infervoyage-dev deploy/infervoyage-dev-ollama -- ollama pull llama3.2
kubectl exec -it -n infervoyage-dev deploy/infervoyage-dev-ollama -- ollama pull gemma2:2b
```

---

## 4. Email DNS Deliverability: SPF, DKIM, and DMARC

To prevent email providers (such as Gmail, Yahoo, and Outlook) from blocking authentication OTP and registration emails, you must configure DNS authentication records for the sender domain.

### 4.1 SPF (Sender Policy Framework)
An SPF record tells email servers which IPs/hosts are allowed to send mail on behalf of your domain.

Add a **TXT** record at your root domain (or subdomain):
* **Host/Name**: `@` (or subdomain like `mail`)
* **Value/Text**: `v=spf1 include:amazonses.com include:sendgrid.net ~all`
  *(Note: Replace `amazonses.com`/`sendgrid.net` with the SPF record supplied by your SMTP provider, e.g., Resend, Mailgun. If hosting your own SMTP server, use `ip4:YOUR_SERVER_IP ~all`)*

### 4.2 DKIM (DomainKeys Identified Mail)
DKIM adds a cryptographic signature to email headers, verifying that the email was actually sent by the domain owner and not altered in transit.

Your SMTP service provider will generate public-private key pairs. Add the public key as a **TXT** record:
* **Host/Name**: `[selector]._domainkey` (e.g., `resend._domainkey`)
* **Value/Text**: `k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...`

### 4.3 DMARC (Domain-based Message Authentication)
DMARC uses SPF and DKIM to determine the authenticity of an email message and specifies how the receiver should handle failures.

Add a **TXT** record:
* **Host/Name**: `_dmarc` (resolving to `_dmarc.yourdomain.com`)
* **Value/Text**: `v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc-reports@yourdomain.com`
  - `p=quarantine`: Directs receivers to put failing emails in Spam.
  - `pct=100`: Applies to 100% of emails.
  - `rua=...`: Specifies where to send XML compliance reports.
