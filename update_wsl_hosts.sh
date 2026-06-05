#!/bin/bash
# Run in WSL to auto-update Windows hosts file with current WSL IP
# Usage: bash /mnt/c/Users/AnanyaPradeep/AI_Inference_Platform/update_wsl_hosts.sh

WSL_IP=$(hostname -I | awk '{print $1}')
HOSTS_FILE="/mnt/c/Windows/System32/drivers/etc/hosts"

echo "WSL IP: $WSL_IP"

# Remove old entries
grep -v -E "infervoyage\.local|grafana\.local|locust\.local" "$HOSTS_FILE" > /tmp/hosts_new 2>/dev/null

# Add fresh entries
cat >> /tmp/hosts_new <<EOF
$WSL_IP	infervoyage.local
$WSL_IP	grafana.local
$WSL_IP	locust.local
EOF

cp /tmp/hosts_new "$HOSTS_FILE"
echo "Hosts file updated with WSL IP $WSL_IP"

echo ""
echo "URLs:"
echo "  https://infervoyage.local:8443/login"
echo "  http://grafana.local:3001"
echo "  http://locust.local:8089"
