#!/bin/bash
WSL_IP=$(hostname -I | tr ' ' '\n' | head -1)
HOSTS=/mnt/c/Windows/System32/drivers/etc/hosts

echo "WSL IP: $WSL_IP"

# Remove old entries, write new ones
grep -v -E "infervoyage\.local|grafana\.local|locust\.local" "$HOSTS" > /root/hosts_new
printf "\n%s\tinfervoyage.local\n%s\tgrafana.local\n%s\tlocust.local\n" "$WSL_IP" "$WSL_IP" "$WSL_IP" >> /root/hosts_new
cp /root/hosts_new "$HOSTS" && echo "SUCCESS: Hosts file updated!" || echo "FAILED: Permission denied"
