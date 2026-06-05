# Run this ONCE in an Admin PowerShell to set up DNS names for InferVoyage
# After this, use: https://infervoyage.local:8443/login

# ─── Get WSL IP dynamically ───────────────────────────────────────────────────
$wslIp = (wsl hostname -I).Trim().Split(" ")[0]
Write-Host "WSL IP: $wslIp" -ForegroundColor Cyan

# ─── Update Windows hosts file ────────────────────────────────────────────────
$hostsPath = "C:\Windows\System32\drivers\etc\hosts"
$entries = @(
    "$wslIp`tinfervoyage.local",
    "$wslIp`tgrafana.local",
    "$wslIp`tlocust.local"
)

# Remove any old InferVoyage entries
$existing = Get-Content $hostsPath | Where-Object { $_ -notmatch "infervoyage\.local|grafana\.local|locust\.local" }
$newContent = $existing + $entries
Set-Content -Path $hostsPath -Value $newContent -Encoding ASCII
Write-Host "Hosts file updated." -ForegroundColor Green

# ─── Set up port proxies so localhost works too ───────────────────────────────
# Remove old rules first
netsh interface portproxy delete v4tov4 listenport=8443 listenaddress=127.0.0.1 2>$null
netsh interface portproxy delete v4tov4 listenport=3001 listenaddress=127.0.0.1 2>$null
netsh interface portproxy delete v4tov4 listenport=8089 listenaddress=127.0.0.1 2>$null

# Add new rules pointing to WSL
netsh interface portproxy add v4tov4 listenport=8443 listenaddress=127.0.0.1 connectport=8443 connectaddress=$wslIp
netsh interface portproxy add v4tov4 listenport=3001 listenaddress=127.0.0.1 connectport=3001 connectaddress=$wslIp
netsh interface portproxy add v4tov4 listenport=8089 listenaddress=127.0.0.1 connectport=8089 connectaddress=$wslIp
Write-Host "Port proxies set up." -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host " DONE! Use these URLs in your browser:" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host " App:     https://infervoyage.local:8443/login" -ForegroundColor Green
Write-Host " Swagger: https://infervoyage.local:8443/docs"  -ForegroundColor Green
Write-Host " Grafana: http://grafana.local:3001"            -ForegroundColor Green
Write-Host " Locust:  http://locust.local:8089"             -ForegroundColor Green
Write-Host ""
Write-Host " Also works via localhost:" -ForegroundColor Cyan
Write-Host " App:     https://localhost:8443/login"         -ForegroundColor Cyan
Write-Host " Grafana: http://localhost:3001"                -ForegroundColor Cyan
Write-Host " Locust:  http://localhost:8089"                -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Yellow
