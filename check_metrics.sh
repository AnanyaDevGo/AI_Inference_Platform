#!/bin/bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090 &
PF_PID=$!
sleep 4

echo "=== Checking active_users_last_15m ==="
curl -s 'http://localhost:9090/api/v1/query?query=active_users_last_15m' | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d, indent=2))"

echo ""
echo "=== Checking db_up ==="
curl -s 'http://localhost:9090/api/v1/query?query=db_up' | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d, indent=2))"

echo ""
echo "=== Checking process_start_time_seconds job label ==="
curl -s 'http://localhost:9090/api/v1/query?query=process_start_time_seconds' | python3 -c "import json,sys; d=json.load(sys.stdin); results=d['data']['result']; [print(r['metric']) for r in results]"

echo ""
echo "=== Checking http_requests_total labels ==="
curl -s 'http://localhost:9090/api/v1/query?query=http_requests_total' | python3 -c "import json,sys; d=json.load(sys.stdin); results=d['data']['result']; print(results[0]['metric'] if results else 'NO DATA')"

kill $PF_PID 2>/dev/null
