# Network Policies — Zero-Trust Pod Communication

## Overview

InferVoyage adopts a **zero-trust networking model** for its Kubernetes deployment. Every pod-to-pod and pod-to-external communication path is explicitly denied by default, and only the minimum required traffic is permitted through individual `NetworkPolicy` resources.

> **CNI Requirement:** Your cluster must use a CNI plugin that enforces `NetworkPolicy` resources (e.g., [Calico](https://www.tigera.io/project-calico/), [Cilium](https://cilium.io/), or [Flannel + Calico overlay](https://docs.projectcalico.org/getting-started/kubernetes/)). The default `kubenet` plugin in many managed clusters does **not** enforce network policies.

---

## Architecture: Allowed Communication Paths

```
Internet / External Users
         │ HTTPS (443)
         ▼
  ┌─────────────────┐
  │  NGINX Ingress   │  (namespace: ingress-nginx)
  │  Controller      │
  └────────┬────────┘
           │ HTTP (80)
           ▼
  ┌─────────────────┐
  │    Frontend     │  (React / Next.js)
  │    :3000        │
  └────────┬────────┘
           │ HTTP (8000)
           ▼
  ┌─────────────────┐        ┌──────────────┐
  │   API Backend   │───────▶│   Postgres   │ :5432
  │   FastAPI :8000 │        └──────────────┘
  └────────┬────────┘
           │                 ┌──────────────┐
           ├────────────────▶│    Redis     │ :6379
           │                 └──────────────┘
           │                 ┌──────────────┐
           └────────────────▶│    Ollama    │ :11434
                             └──────────────┘
  ┌─────────────────┐
  │ Locust Master   │──────▶ API :8000
  │ Locust Workers  │
  └─────────────────┘

  ┌─────────────────────────────────────────┐
  │       Monitoring  (namespace: monitoring)│
  │  Prometheus ──scrapes──▶ all pods :8000  │
  │  Grafana    ◀──query──  Prometheus :9090  │
  │  Alertmanager ◀─alerts─ Prometheus :9093  │
  └─────────────────────────────────────────┘
```

---

## Policy Inventory

| Policy File | Namespace | Applies To | Key Rules |
|---|---|---|---|
| `default-deny.yaml` | `infervoyage-dev` | All pods | Deny all ingress + egress |
| `frontend/networkpolicy.yaml` | `infervoyage-dev` | `app: frontend` | Ingress from ingress-nginx; Egress to API |
| `api/networkpolicy.yaml` | `infervoyage-dev` | `app: api` | Ingress from frontend + locust + prometheus; Egress to postgres/redis/ollama/DNS/external HTTPS |
| `postgres/networkpolicy.yaml` | `infervoyage-dev` | `app: postgres` | Ingress from API only |
| `redis/networkpolicy.yaml` | `infervoyage-dev` | `app: redis` | Ingress from API only |
| `ollama/networkpolicy.yaml` | `infervoyage-dev` | `app: ollama` | Ingress from API only; Egress to external HTTPS for model pulls |
| `locust/networkpolicy.yaml` | `infervoyage-dev` | `app: locust-*` | Egress to API only |
| `observability/default-deny.yaml` | `monitoring` | All pods | Deny all ingress + egress |
| `observability/prometheus-networkpolicy.yaml` | `monitoring` | Prometheus | Scrape all namespaces; Egress to Alertmanager/Grafana |
| `observability/grafana-networkpolicy.yaml` | `monitoring` | Grafana | Ingress from ingress-nginx; Egress to Prometheus |
| `observability/alertmanager-networkpolicy.yaml` | `monitoring` | Alertmanager | Ingress from Prometheus; Egress to external HTTPS |
| `observability/exporters-networkpolicy.yaml` | `monitoring` | node-exporter / kube-state-metrics | Ingress from Prometheus only |

---

## Helm Configuration

Network policies are controlled via the `networkPolicies` key in your values files.

### Default (`values.yaml`)

```yaml
networkPolicies:
  enabled: true
  ingressControllerNamespace: "ingress-nginx"
  monitoringNamespace: "monitoring"
  dnsNamespace: "kube-system"
  externalEgress:
    cidr: "0.0.0.0/0"
    exceptCIDRs:
      - "10.0.0.0/8"
      - "172.16.0.0/12"
      - "192.168.0.0/16"
```

### To disable (development only)

```yaml
# values-dev-override.yaml
networkPolicies:
  enabled: false
```

### Applying with Helm

```bash
# Dev
helm upgrade --install infervoyage ./deploy/helm/infervoyage \
  -n infervoyage-dev --create-namespace

# Staging
helm upgrade --install infervoyage ./deploy/helm/infervoyage \
  -n infervoyage-staging --create-namespace \
  -f deploy/helm/infervoyage/values-staging.yaml

# Production
helm upgrade --install infervoyage ./deploy/helm/infervoyage \
  -n infervoyage-prod --create-namespace \
  -f deploy/helm/infervoyage/values-prod.yaml
```

### Applying raw manifests (dev)

```bash
# Apply default-deny first, then all policies
kubectl apply -f deploy/kubernetes/default-deny.yaml
kubectl apply -f deploy/kubernetes/frontend/networkpolicy.yaml
kubectl apply -f deploy/kubernetes/api/networkpolicy.yaml
kubectl apply -f deploy/kubernetes/postgres/networkpolicy.yaml
kubectl apply -f deploy/kubernetes/redis/networkpolicy.yaml
kubectl apply -f deploy/kubernetes/ollama/networkpolicy.yaml
kubectl apply -f deploy/kubernetes/locust/networkpolicy.yaml

# Observability namespace
kubectl apply -f deploy/kubernetes/observability/default-deny.yaml
kubectl apply -f deploy/kubernetes/observability/prometheus-networkpolicy.yaml
kubectl apply -f deploy/kubernetes/observability/grafana-networkpolicy.yaml
kubectl apply -f deploy/kubernetes/observability/alertmanager-networkpolicy.yaml
kubectl apply -f deploy/kubernetes/observability/exporters-networkpolicy.yaml
```

---

## Policy Details

### 1. Default Deny (namespace-wide)

**Files:**
- `deploy/kubernetes/default-deny.yaml`
- `deploy/kubernetes/observability/default-deny.yaml`

Catches all pods with an empty `podSelector: {}`. Blocks both ingress and egress by declaring both `policyTypes` with no rules.

```yaml
spec:
  podSelector: {}      # Selects ALL pods in namespace
  policyTypes:
    - Ingress
    - Egress
  # No ingress/egress rules = deny all
```

---

### 2. Frontend Policy

**Ingress:** Accepts traffic from the NGINX Ingress Controller pod (namespace: `ingress-nginx`).  
**Egress:** Sends traffic only to the API backend on port `8000`, plus DNS (`kube-system:53`).

---

### 3. API Backend Policy

**Ingress allowed from:**
| Source | Port |
|---|---|
| `app: frontend` pods | 8000 |
| `app: locust-master` pods | 8000 |
| `app: locust-worker` pods | 8000 |
| Prometheus (`monitoring` namespace) | 8000 |

**Egress allowed to:**
| Destination | Port | Protocol |
|---|---|---|
| `kube-system` DNS | 53 | UDP + TCP |
| `app: postgres` | 5432 | TCP |
| `app: redis` | 6379 | TCP |
| `app: ollama` | 11434 | TCP |
| External public IPs (excluding RFC1918) | 443, 80 | TCP |

The external egress rule enables: **Google OAuth**, **Resend email API**, and any other SaaS endpoints.

---

### 4. Postgres Policy

**Ingress:** Only from `app: api` pods on port `5432`.  
**Egress:** DNS only. Postgres does not initiate outbound connections.

---

### 5. Redis Policy

**Ingress:** Only from `app: api` pods on port `6379`.  
**Egress:** DNS only.

---

### 6. Ollama Policy

**Ingress:** Only from `app: api` pods on port `11434`.  
**Egress:** DNS + external HTTPS (port `443`) to allow pulling models from `ollama.com` / HuggingFace.

---

### 7. Locust Policy

**Ingress (master):** From locust-worker pods on ports `5557–5558` (Locust distributed communication).  
**Egress:** To `app: api` on port `8000` and DNS.

---

### 8. Prometheus Policy

**Egress scrape targets:**
- All namespaces (`infervoyage-*`, `monitoring`) on pod port `8000` and Kubernetes metrics ports `9100`, `8443`, `10250`.
- Alertmanager on port `9093`.

**Ingress:** From Grafana on port `9090`.

---

### 9. Grafana Policy

**Ingress:** From NGINX Ingress Controller (for UI access).  
**Egress:** To Prometheus on port `9090` and DNS.

---

### 10. Alertmanager Policy

**Ingress:** From Prometheus on port `9093`.  
**Egress:** External HTTPS (port `443`) for webhook/email notifications + DNS.

---

## Troubleshooting

### Verify policies are active

```bash
kubectl get networkpolicies -n infervoyage-dev
kubectl get networkpolicies -n monitoring
```

### Describe a policy

```bash
kubectl describe networkpolicy api-networkpolicy -n infervoyage-dev
```

### Test connectivity (automated)

```bash
# Run the full connectivity test suite
bash scripts/connectivity-test.sh
```

### Common Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| Frontend gets 503 from API | API ingress rule missing frontend label | Verify `app: frontend` label on frontend pod |
| Prometheus shows targets as DOWN | Prometheus egress/ingress not matching | Check monitoring namespace label + prometheus pod selector |
| Ollama model pull fails | Ollama external egress blocked | Verify `externalEgress.exceptCIDRs` doesn't block your model registry |
| Email sending fails | API external egress blocked | Resend.com is HTTPS (443) — should be allowed by default rule |
| Google OAuth login fails | API external egress blocked | Google APIs are public IPs — allowed by the external egress rule |
| DNS resolution fails | DNS egress not in policy | Every policy includes `kube-system:53` DNS egress |

### Temporarily disable a policy (debugging)

```bash
# Delete and re-apply when done
kubectl delete networkpolicy api-networkpolicy -n infervoyage-dev

# Restore
kubectl apply -f deploy/kubernetes/api/networkpolicy.yaml
```

---

## Security Notes

1. **Private IP exception** — The external egress rule blocks RFC1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) to prevent SSRF attacks where an external-looking request routes to an internal cluster service.

2. **Namespace isolation** — The `monitoring` namespace has its own default-deny policy, ensuring monitoring pods are isolated from application pods except via explicitly permitted scrape paths.

3. **No wildcard pod selectors in allows** — Every `from`/`to` rule uses specific `matchLabels`, not empty selectors.

4. **Production Locust is disabled** — `values-prod.yaml` sets `locust.enabled: false`, so no locust pods or network policies are deployed to production.
