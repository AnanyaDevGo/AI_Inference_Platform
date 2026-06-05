#!/bin/bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090 &
PF_PID=$!
sleep 4
curl -s 'http://localhost:9090/api/v1/targets' | python3 -c "
import json, sys
data = json.load(sys.stdin)
targets = data['data']['activeTargets']
for t in targets:
    pool = t.get('scrapePool', '')
    if 'infervoyage' in pool or 'infervoyage' in str(t.get('labels', {})):
        print('=== POOL:', pool)
        print('  URL:', t.get('scrapeUrl'))
        print('  Health:', t.get('health'))
        print('  Labels:', json.dumps(t.get('labels'), indent=4))
        print('  Last Error:', t.get('lastError', 'none'))
        print()
"
kill $PF_PID 2>/dev/null
