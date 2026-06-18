#!/usr/bin/env bash
# =============================================================================
# connectivity-test.sh — Zero-Trust Network Policy Validation
# =============================================================================
# Tests that NetworkPolicy rules are correctly enforced across all services.
# Runs both ALLOWED and BLOCKED connectivity checks and reports results.
#
# Usage:
#   bash scripts/connectivity-test.sh [NAMESPACE]
#
# Default namespace: infervoyage-dev
# Requirements: kubectl configured and pointing to the target cluster
# =============================================================================

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
NAMESPACE="${1:-infervoyage-dev}"
MONITORING_NS="monitoring"
TIMEOUT="5"           # seconds per connection attempt
IMAGE="busybox:1.36"  # lightweight test image
NETCAT_IMAGE="nicolaka/netshoot:latest"  # image with nc, curl, dig
PASS=0
FAIL=0
SKIP=0

# ANSI colours
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Colour

# ── Helpers ───────────────────────────────────────────────────────────────────

log_header() {
  echo ""
  echo -e "${BLUE}${BOLD}══════════════════════════════════════════════════════${NC}"
  echo -e "${BLUE}${BOLD}  $1${NC}"
  echo -e "${BLUE}${BOLD}══════════════════════════════════════════════════════${NC}"
}

log_test() {
  printf "  %-60s" "$1"
}

pass() {
  echo -e "${GREEN}[PASS]${NC}"
  ((PASS++))
}

fail() {
  echo -e "${RED}[FAIL] $1${NC}"
  ((FAIL++))
}

skip() {
  echo -e "${YELLOW}[SKIP] $1${NC}"
  ((SKIP++))
}

# Run a TCP connectivity test from a source pod to host:port
# Returns 0 if connection succeeds, 1 if blocked/timed-out
tcp_test() {
  local source_pod="$1"
  local source_ns="$2"
  local target_host="$3"
  local target_port="$4"

  kubectl exec -n "$source_ns" "$source_pod" -- \
    timeout "$TIMEOUT" sh -c "nc -z -w $TIMEOUT $target_host $target_port" \
    2>/dev/null
}

# Spin up a temporary pod with a given label and image, run a command, then delete
run_ephemeral() {
  local pod_name="$1"
  local ns="$2"
  local label="$3"
  local cmd="$4"

  kubectl run "$pod_name" \
    --namespace="$ns" \
    --image="$NETCAT_IMAGE" \
    --restart=Never \
    --labels="$label" \
    --rm \
    --attach \
    --quiet \
    --command -- sh -c "$cmd" 2>/dev/null
}

# Get the first running pod matching a label selector
get_pod() {
  local ns="$1"
  local selector="$2"
  kubectl get pod -n "$ns" -l "$selector" \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo ""
}

# ── Preflight ─────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}InferVoyage — Zero-Trust Connectivity Test Suite${NC}"
echo -e "Namespace    : ${YELLOW}${NAMESPACE}${NC}"
echo -e "Monitoring NS: ${YELLOW}${MONITORING_NS}${NC}"
echo -e "Timeout      : ${TIMEOUT}s per test"
echo ""

# Check kubectl access
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
  echo -e "${RED}ERROR: Cannot access namespace '$NAMESPACE'. Check kubeconfig.${NC}"
  exit 1
fi

# ── Discover Live Pods ────────────────────────────────────────────────────────
log_header "Discovering live pods"

POD_FRONTEND=$(get_pod "$NAMESPACE" "app=frontend")
POD_API=$(get_pod "$NAMESPACE" "app=api")
POD_POSTGRES=$(get_pod "$NAMESPACE" "app=postgres")
POD_REDIS=$(get_pod "$NAMESPACE" "app=redis")
POD_OLLAMA=$(get_pod "$NAMESPACE" "app=ollama")
POD_LOCUST_MASTER=$(get_pod "$NAMESPACE" "app=locust-master")
POD_PROMETHEUS=$(get_pod "$MONITORING_NS" "app.kubernetes.io/name=prometheus")
POD_GRAFANA=$(get_pod "$MONITORING_NS" "app.kubernetes.io/name=grafana")

printf "  %-30s %s\n" "frontend:"     "${POD_FRONTEND:-<not found>}"
printf "  %-30s %s\n" "api:"          "${POD_API:-<not found>}"
printf "  %-30s %s\n" "postgres:"     "${POD_POSTGRES:-<not found>}"
printf "  %-30s %s\n" "redis:"        "${POD_REDIS:-<not found>}"
printf "  %-30s %s\n" "ollama:"       "${POD_OLLAMA:-<not found>}"
printf "  %-30s %s\n" "locust-master:""${POD_LOCUST_MASTER:-<not found>}"
printf "  %-30s %s\n" "prometheus:"   "${POD_PROMETHEUS:-<not found>}"
printf "  %-30s %s\n" "grafana:"      "${POD_GRAFANA:-<not found>}"

# ── Section 1: API Backend ────────────────────────────────────────────────────
log_header "API Backend — Ingress (should be ALLOWED)"

# Frontend → API :8000
log_test "frontend → api:8000"
if [[ -z "$POD_FRONTEND" || -z "$POD_API" ]]; then
  skip "required pods not found"
elif tcp_test "$POD_FRONTEND" "$NAMESPACE" "api" "8000"; then
  pass
else
  fail "frontend cannot reach api:8000 (policy may be missing/misconfigured)"
fi

# Locust → API :8000
log_test "locust-master → api:8000"
if [[ -z "$POD_LOCUST_MASTER" || -z "$POD_API" ]]; then
  skip "locust pod not found (may be disabled in prod)"
elif tcp_test "$POD_LOCUST_MASTER" "$NAMESPACE" "api" "8000"; then
  pass
else
  fail "locust-master cannot reach api:8000"
fi

log_header "API Backend — Egress (should be ALLOWED)"

# API → Postgres :5432
log_test "api → postgres:5432"
if [[ -z "$POD_API" || -z "$POD_POSTGRES" ]]; then
  skip "required pods not found"
elif tcp_test "$POD_API" "$NAMESPACE" "postgres" "5432"; then
  pass
else
  fail "api cannot reach postgres:5432"
fi

# API → Redis :6379
log_test "api → redis:6379"
if [[ -z "$POD_API" || -z "$POD_REDIS" ]]; then
  skip "required pods not found"
elif tcp_test "$POD_API" "$NAMESPACE" "redis" "6379"; then
  pass
else
  fail "api cannot reach redis:6379"
fi

# API → Ollama :11434
log_test "api → ollama:11434"
if [[ -z "$POD_API" || -z "$POD_OLLAMA" ]]; then
  skip "required pods not found"
elif tcp_test "$POD_API" "$NAMESPACE" "ollama" "11434"; then
  pass
else
  fail "api cannot reach ollama:11434"
fi

# API → External HTTPS (DNS check via curl)
log_test "api → external HTTPS (api.resend.com:443)"
if [[ -z "$POD_API" ]]; then
  skip "api pod not found"
elif kubectl exec -n "$NAMESPACE" "$POD_API" -- \
    timeout "$TIMEOUT" sh -c "curl -s --connect-timeout $TIMEOUT https://api.resend.com -o /dev/null -w '%{http_code}'" \
    2>/dev/null | grep -qE "^[2345]"; then
  pass
else
  fail "api cannot reach external HTTPS endpoint"
fi

# API → DNS resolution
log_test "api → DNS resolution (kube-dns)"
if [[ -z "$POD_API" ]]; then
  skip "api pod not found"
elif kubectl exec -n "$NAMESPACE" "$POD_API" -- \
    timeout "$TIMEOUT" sh -c "nslookup kubernetes.default.svc.cluster.local" \
    2>/dev/null | grep -q "Address"; then
  pass
else
  fail "api cannot resolve DNS"
fi

# ── Section 2: Blocked Paths (negative tests) ─────────────────────────────────
log_header "Blocked Paths — Direct Pod-to-Pod (should be DENIED)"

# Postgres → API (postgres should not initiate connections outward)
log_test "postgres → api:8000  [MUST be blocked]"
if [[ -z "$POD_POSTGRES" || -z "$POD_API" ]]; then
  skip "required pods not found"
elif ! tcp_test "$POD_POSTGRES" "$NAMESPACE" "api" "8000"; then
  pass
else
  fail "postgres CAN reach api:8000 — policy not enforced!"
fi

# Redis → API (redis should not initiate connections)
log_test "redis → api:8000  [MUST be blocked]"
if [[ -z "$POD_REDIS" || -z "$POD_API" ]]; then
  skip "required pods not found"
elif ! tcp_test "$POD_REDIS" "$NAMESPACE" "api" "8000"; then
  pass
else
  fail "redis CAN reach api:8000 — policy not enforced!"
fi

# Ollama → Postgres (ollama has no reason to talk to DB)
log_test "ollama → postgres:5432  [MUST be blocked]"
if [[ -z "$POD_OLLAMA" || -z "$POD_POSTGRES" ]]; then
  skip "required pods not found"
elif ! tcp_test "$POD_OLLAMA" "$NAMESPACE" "postgres" "5432"; then
  pass
else
  fail "ollama CAN reach postgres:5432 — policy not enforced!"
fi

# Frontend → Postgres (frontend should only talk to API)
log_test "frontend → postgres:5432  [MUST be blocked]"
if [[ -z "$POD_FRONTEND" || -z "$POD_POSTGRES" ]]; then
  skip "required pods not found"
elif ! tcp_test "$POD_FRONTEND" "$NAMESPACE" "postgres" "5432"; then
  pass
else
  fail "frontend CAN reach postgres:5432 — policy not enforced!"
fi

# Frontend → Redis
log_test "frontend → redis:6379  [MUST be blocked]"
if [[ -z "$POD_FRONTEND" || -z "$POD_REDIS" ]]; then
  skip "required pods not found"
elif ! tcp_test "$POD_FRONTEND" "$NAMESPACE" "redis" "6379"; then
  pass
else
  fail "frontend CAN reach redis:6379 — policy not enforced!"
fi

# Frontend → Ollama (direct, bypassing API)
log_test "frontend → ollama:11434  [MUST be blocked]"
if [[ -z "$POD_FRONTEND" || -z "$POD_OLLAMA" ]]; then
  skip "required pods not found"
elif ! tcp_test "$POD_FRONTEND" "$NAMESPACE" "ollama" "11434"; then
  pass
else
  fail "frontend CAN reach ollama:11434 — policy not enforced!"
fi

# API → private RFC1918 range (SSRF check)
log_test "api → 10.0.0.1:80 (private IP)  [MUST be blocked]"
if [[ -z "$POD_API" ]]; then
  skip "api pod not found"
elif ! kubectl exec -n "$NAMESPACE" "$POD_API" -- \
    timeout "$TIMEOUT" sh -c "nc -z -w $TIMEOUT 10.0.0.1 80" 2>/dev/null; then
  pass
else
  fail "api CAN reach private RFC1918 IP — SSRF risk!"
fi

# ── Section 3: Frontend ───────────────────────────────────────────────────────
log_header "Frontend — Allowed Paths"

# Frontend → API :8000 (already tested above, quick re-confirm)
log_test "frontend → api:8000"
if [[ -z "$POD_FRONTEND" || -z "$POD_API" ]]; then
  skip "required pods not found"
elif tcp_test "$POD_FRONTEND" "$NAMESPACE" "api" "8000"; then
  pass
else
  fail "frontend cannot reach api:8000"
fi

# ── Section 4: Observability ──────────────────────────────────────────────────
log_header "Observability — Prometheus Scrape (should be ALLOWED)"

# Prometheus → API :8000 (metrics scraping)
log_test "prometheus → api:8000 (metrics)"
if [[ -z "$POD_PROMETHEUS" ]]; then
  skip "prometheus pod not found (check monitoring namespace)"
elif kubectl exec -n "$MONITORING_NS" "$POD_PROMETHEUS" -- \
    timeout "$TIMEOUT" sh -c \
    "curl -s --connect-timeout $TIMEOUT http://api.$NAMESPACE.svc.cluster.local:8000/metrics -o /dev/null -w '%{http_code}'" \
    2>/dev/null | grep -qE "^[23]"; then
  pass
else
  fail "prometheus cannot scrape api:8000/metrics"
fi

# Grafana → Prometheus :9090
log_test "grafana → prometheus:9090"
if [[ -z "$POD_GRAFANA" || -z "$POD_PROMETHEUS" ]]; then
  skip "grafana or prometheus pod not found"
elif tcp_test "$POD_GRAFANA" "$MONITORING_NS" "prometheus-operated" "9090"; then
  pass
else
  fail "grafana cannot reach prometheus:9090"
fi

log_header "Observability — Blocked Paths"

# Grafana → API direct (grafana should only query prometheus)
log_test "grafana → api:8000  [MUST be blocked]"
if [[ -z "$POD_GRAFANA" || -z "$POD_API" ]]; then
  skip "required pods not found"
elif ! kubectl exec -n "$MONITORING_NS" "$POD_GRAFANA" -- \
    timeout "$TIMEOUT" sh -c \
    "nc -z -w $TIMEOUT api.$NAMESPACE.svc.cluster.local 8000" 2>/dev/null; then
  pass
else
  fail "grafana CAN reach api:8000 directly — cross-namespace policy breach!"
fi

# ── Network Policy Manifest Validation ───────────────────────────────────────
log_header "Manifest Validation — kubectl dry-run"

MANIFESTS=(
  "deploy/kubernetes/default-deny.yaml"
  "deploy/kubernetes/frontend/networkpolicy.yaml"
  "deploy/kubernetes/api/networkpolicy.yaml"
  "deploy/kubernetes/postgres/networkpolicy.yaml"
  "deploy/kubernetes/redis/networkpolicy.yaml"
  "deploy/kubernetes/ollama/networkpolicy.yaml"
  "deploy/kubernetes/locust/networkpolicy.yaml"
  "deploy/kubernetes/observability/default-deny.yaml"
  "deploy/kubernetes/observability/prometheus-networkpolicy.yaml"
  "deploy/kubernetes/observability/grafana-networkpolicy.yaml"
  "deploy/kubernetes/observability/alertmanager-networkpolicy.yaml"
  "deploy/kubernetes/observability/exporters-networkpolicy.yaml"
)

for manifest in "${MANIFESTS[@]}"; do
  log_test "dry-run: $manifest"
  if kubectl apply --dry-run=client -f "$manifest" &>/dev/null; then
    pass
  else
    fail "manifest failed dry-run validation"
  fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
log_header "Test Summary"

TOTAL=$((PASS + FAIL + SKIP))
echo ""
echo -e "  Total Tests : ${BOLD}${TOTAL}${NC}"
echo -e "  ${GREEN}Passed      : ${PASS}${NC}"
echo -e "  ${RED}Failed      : ${FAIL}${NC}"
echo -e "  ${YELLOW}Skipped     : ${SKIP}${NC} (pods not running)"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
  echo -e "${RED}${BOLD}✗ ${FAIL} test(s) failed. Review network policies and pod labels.${NC}"
  echo -e "  See: docs/NETWORK-POLICIES.md — Troubleshooting section"
  exit 1
else
  echo -e "${GREEN}${BOLD}✓ All connectivity tests passed!${NC}"
  exit 0
fi
