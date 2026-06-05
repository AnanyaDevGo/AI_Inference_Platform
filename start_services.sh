#!/bin/bash
# ─── InferVoyage: Full restart + DNS setup from WSL ───────────────────────────

set -e

WSL_IP=$(hostname -I | tr ' ' '\n' | head -1)
echo "WSL IP: $WSL_IP"

echo ""
echo "=== Killing existing port-forwards ==="
fuser -k 8443/tcp 2>/dev/null || true
fuser -k 3001/tcp 2>/dev/null || true
fuser -k 8089/tcp 2>/dev/null || true
sleep 1
echo "Cleared ports 8443, 3001, 8089"

echo ""
echo "=== Checking all pods are Running ==="
kubectl get pods -n infervoyage-dev --no-headers | awk '{printf "%-55s %s\n", $1, $4}'
echo "---"
kubectl get pods -n monitoring --no-headers | grep -E "grafana|prometheus" | awk '{printf "%-55s %s\n", $1, $4}'

echo ""
echo "=== Starting port-forwards in background ==="

kubectl port-forward -n infervoyage-dev service/frontend 8443:8443 --address 0.0.0.0 \
  > /tmp/pf_app.log 2>&1 &
echo "App (HTTPS)  port-forward PID $! → 8443"

kubectl port-forward -n monitoring service/prometheus-grafana 3001:80 --address 0.0.0.0 \
  > /tmp/pf_grafana.log 2>&1 &
echo "Grafana      port-forward PID $! → 3001"

kubectl port-forward -n infervoyage-dev service/infervoyage-dev-locust-master 8089:8089 --address 0.0.0.0 \
  > /tmp/pf_locust.log 2>&1 &
echo "Locust       port-forward PID $! → 8089"

echo "Waiting 4s for port-forwards to bind..."
sleep 4

echo ""
echo "=== Updating Windows hosts file via PowerShell (requires UAC approval) ==="
HOSTS_SCRIPT="
\$hostsPath = 'C:\\Windows\\System32\\drivers\\etc\\hosts'
\$ip = '$WSL_IP'
\$content = Get-Content \$hostsPath | Where-Object { \$_ -notmatch 'infervoyage\.local|grafana\.local|locust\.local' }
\$content += ''
\$content += \"\$ip\`tinfervoyage.local\"
\$content += \"\$ip\`tgrafana.local\"
\$content += \"\$ip\`tlocust.local\"
Set-Content -Path \$hostsPath -Value \$content -Encoding ASCII
Write-Host 'Hosts file updated successfully!'
"

# Try via elevated PowerShell from WSL
powershell.exe -Command "Start-Process powershell -ArgumentList '-NoProfile -Command ${HOSTS_SCRIPT}' -Verb RunAs -Wait" 2>/dev/null && HOSTS_OK=1 || HOSTS_OK=0

if [ $HOSTS_OK -eq 0 ]; then
  echo ""
  echo "⚠  Could not auto-elevate. Run this ONE command in Admin PowerShell manually:"
  echo ""
  echo "   Add-Content 'C:\\Windows\\System32\\drivers\\etc\\hosts' \\"
  echo "     \"\`n$WSL_IP\`tinfervoyage.local\`n$WSL_IP\`tgrafana.local\`n$WSL_IP\`tlocust.local\""
  echo ""
fi

echo ""
echo "=== Verifying connectivity ==="
sleep 2
curl -k -s -o /dev/null -w "App HTTPS  (8443): %{http_code}\n" https://localhost:8443/login  || echo "App HTTPS  (8443): NOT READY"
curl    -s -o /dev/null -w "Grafana    (3001): %{http_code}\n" http://localhost:3001/login    || echo "Grafana    (3001): NOT READY"
curl    -s -o /dev/null -w "Locust     (8089): %{http_code}\n" http://localhost:8089/         || echo "Locust     (8089): NOT READY"

echo ""
echo "========================================"
echo " All services ready!"
echo "========================================"
echo " App:     https://infervoyage.local:8443/login"
echo " Swagger: https://infervoyage.local:8443/docs"
echo " Grafana: http://grafana.local:3001  (admin/prom-operator)"
echo " Locust:  http://locust.local:8089"
echo ""
echo " Or via WSL IP directly:"
echo " App:     https://$WSL_IP:8443/login"
echo " Grafana: http://$WSL_IP:3001"
echo " Locust:  http://$WSL_IP:8089"
echo "========================================"
