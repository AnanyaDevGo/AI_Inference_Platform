# InferVoyage — Kubernetes-Native Deployment & Operations Guide

This directory houses the manifests, configurations, and Helm charts required to transition the **InferVoyage** platform from a local Docker Compose stack into a highly scalable, production-ready **Kubernetes-Native** architecture.

---

## 🏗️ System Architecture & Routing

```
                              [ Internet ]
                                   │
                                   ▼
                       [ Nginx Ingress Controller ]
                     (TLS Offloading & Rate Limiting)
                                   │
            ┌──────────────────────┴──────────────────────┐
            │ / (React Web App)                           │ /v1 & /auth (FastAPI)
            ▼                                             ▼
  [ Frontend Service ]                             [ API Service ]
   (ClusterIP: 80)                                 (ClusterIP: 8000)
            │                                             │
            ├─────────────── (Internal DNS) ──────────────┤
            ▼                                             ▼
  [ Redis Service ]                                [ Ollama Service ]
   (ClusterIP: 6379)                                (ClusterIP: 11434)
            │                                             │
            ▼                                             ▼
  [ Redis Pods ]                                   [ Ollama GPU/CPU Pods ]
(Ephemeral Rate Limits)                            (Cached GGUF PVC Storage)
            │                                             │
            ▼                                             ▼
  [ Postgres StatefulSet ]                        [ PersistentVolumeClaims ]
   (ClusterIP: 5432)                               (Postgres/Ollama Data)
```

---

## 📂 Directories

- **`kubernetes/`**: Contains raw, environment-independent Kubernetes manifests.
  - `namespaces.yaml`: Structural layout for isolated environments (`dev`, `staging`, `prod`).
  - `postgres/`: StatefulSet and Service definition with `postgres-exporter` sidecar.
  - `redis/`: Redis deployment, local memory-limiting configmaps, and `redis-exporter` sidecar.
  - `ollama/`: Model caching storage PVCs, scale-out HPAs, and GPU/CPU deployment switches.
  - `api/`: FastAPI deployment, HPAs, and cluster secrets mapping.
  - `frontend/`: React Caddy/Nginx serving configuration.
  - `ingress/`: Host-based routing rules and IP-based rate limiting.
  - `locust/`: Scalable, distributed master/worker swarming setup.
  - `observability/`: ServiceMonitor files for cluster metrics integration.
- **`helm/`**: Configurable package manager for InferVoyage installations.
  - `Chart.yaml`: Helm package metadata.
  - `values.yaml`: Default local/development values.
  - `values-staging.yaml`: Staging environment configs.
  - `values-prod.yaml`: Production environment configs.
  - `templates/`: Dynamic parameterized resource definitions.

---

## 🚀 Quickstart Deployment

### Prerequisites
- Active Kubernetes cluster (Minikube, Kind, GKE, EKS).
- Helm v3 installed.
- **Nginx Ingress Controller** running inside the cluster:
  ```bash
  helm upgrade --install ingress-nginx ingress-nginx \
    --repo https://kubernetes.github.io/ingress-nginx \
    --namespace ingress-nginx --create-namespace
  ```

### Local Dev Setup via Helm
1. Run a dry-run check to verify templating outputs:
   ```bash
   helm install infervoyage-dev deploy/helm/infervoyage -f deploy/helm/infervoyage/values.yaml --dry-run
   ```
2. Install the chart to the dev namespace:
   ```bash
   helm upgrade --install infervoyage-dev deploy/helm/infervoyage \
     --namespace infervoyage-dev --create-namespace
   ```
3. Add the hostname mapping to your local `/etc/hosts` file (or Windows `hosts` file):
   ```
   127.0.0.1 infervoyage.local
   ```
4. Access the portal at **[http://infervoyage.local](http://infervoyage.local)**.

---

## ⚡ GPU Scheduling (Production Readiness)

Production environments require GPU instances to handle concurrent AI inference with acceptable token latencies.

1. Install the **Nvidia Device Plugin** in your cluster:
   ```bash
   kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.0/nvidia-device-plugin.yml
   ```
2. Apply the production values file during deployment:
   ```bash
   helm upgrade --install infervoyage-prod deploy/helm/infervoyage \
     --namespace infervoyage-prod --create-namespace \
     -f deploy/helm/infervoyage/values-prod.yaml
   ```
   This automatically injects GPU resource requests, Nvidia node tolerations, and schedules Ollama pods on GPU-backed worker pools.

---

## 📈 Autoscaling Recommendations

### 1. API Horizontal Pod Autoscaler
Scaled dynamically via HPA based on CPU constraints:
```yaml
  minReplicas: 4
  maxReplicas: 20
  targetCPUUtilizationPercentage: 70
```

### 2. Ollama Queue-aware Autoscaling (Recommended)
While the provided `hpa.yaml` scales Ollama based on CPU utilization, inference CPU usage spikes to 100% immediately on single request streams. For advanced production scaling, install **KEDA** (Kubernetes Event-driven Autoscaling) to scale Ollama replicas based on active concurrent queue metrics scraped from Prometheus:
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: ollama-scaledobject
  namespace: infervoyage-prod
spec:
  scaleTargetRef:
    name: ollama
  minReplicaCount: 2
  maxReplicaCount: 6
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-k8s.monitoring.svc.cluster.local:9090
        metricName: http_requests_in_flight
        query: sum(http_requests_in_flight{component="ollama"})
        threshold: '5' # Scale out an extra replica for every 5 requests queued
```

---

## 📋 Production Best Practices

- **Stateful Persistence**: Never deploy PostgreSQL or Redis on local storage classes in production. Override `.Values.postgres.storageClass` and `.Values.redis.storageClass` to point to redundant cloud block storage (e.g. `gp3` on AWS, `premium-rwo` on GCP).
- **Secrets Management**: Do not check real base64 credentials into Git. Set `postgres.password` and `api.secretKey` via Helm command line flags `--set` or inject them directly from secure vaults (e.g. HashiCorp Vault, AWS Secrets Manager) using an External Secrets Operator (ESO).
- **Probes**: Both liveness and readiness probes are integrated for all components. The API pod will not receive traffic until PostgreSQL, Redis, and Ollama connections pass their readiness checks.
