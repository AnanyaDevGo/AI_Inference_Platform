$ip = (wsl hostname -I).Trim().Split(" ")[0]
$hostsPath = "C:\Windows\System32\drivers\etc\hosts"

# Remove old entries
$lines = Get-Content $hostsPath | Where-Object { $_ -notmatch "infervoyage\.local|grafana\.local|locust\.local" }

# Append new entries
$lines += ""
$lines += "$ip`tinfervoyage.local"
$lines += "$ip`tgrafana.local"
$lines += "$ip`tlocust.local"

Set-Content -Path $hostsPath -Value $lines -Encoding ASCII
Write-Host "SUCCESS: Hosts file updated with WSL IP $ip" -ForegroundColor Green
Write-Host ""
Write-Host "Open in browser:" -ForegroundColor Cyan
Write-Host "  https://infervoyage.local:8443/login"
Write-Host "  http://grafana.local:3001"
Write-Host "  http://locust.local:8089"
