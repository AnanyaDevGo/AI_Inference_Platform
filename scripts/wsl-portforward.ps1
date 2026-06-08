# WSL2 + Minikube Port Forwarding Setup
# Run this script as Administrator after every WSL/Minikube restart
# Usage: PowerShell (Admin) > .\scripts\wsl-portforward.ps1

$minikubeIp      = "192.168.49.2"
$ingressHttpPort  = "30228"    # NodePort for HTTP  (update if Minikube is recreated)
$ingressHttpsPort = "32464"    # NodePort for HTTPS (update if Minikube is recreated)

Write-Host "Minikube IP       : $minikubeIp"       -ForegroundColor Cyan
Write-Host "Ingress HTTP port : $ingressHttpPort"  -ForegroundColor Cyan
Write-Host "Ingress HTTPS port: $ingressHttpsPort" -ForegroundColor Cyan
Write-Host ""

# ── Remove old rules ───────────────────────────────────────────────────────────
$listenPorts = @(80, 443, 3000, 8000)
foreach ($port in $listenPorts) {
    netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 2>$null | Out-Null
}

# ── Add new portproxy rules ────────────────────────────────────────────────────
netsh interface portproxy add v4tov4 listenport=80   listenaddress=0.0.0.0 connectport=$ingressHttpPort  connectaddress=$minikubeIp
Write-Host "  Forwarding Windows:80   -> Minikube($minikubeIp):$ingressHttpPort  [Ingress HTTP]"  -ForegroundColor Green

netsh interface portproxy add v4tov4 listenport=443  listenaddress=0.0.0.0 connectport=$ingressHttpsPort connectaddress=$minikubeIp
Write-Host "  Forwarding Windows:443  -> Minikube($minikubeIp):$ingressHttpsPort [Ingress HTTPS]" -ForegroundColor Green

netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 connectport=$ingressHttpPort  connectaddress=$minikubeIp
Write-Host "  Forwarding Windows:3000 -> Minikube($minikubeIp):$ingressHttpPort  [Ingress HTTP alt]" -ForegroundColor Green

netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=$ingressHttpPort  connectaddress=$minikubeIp
Write-Host "  Forwarding Windows:8000 -> Minikube($minikubeIp):$ingressHttpPort  [API via Ingress]" -ForegroundColor Green

# ── Firewall rule ──────────────────────────────────────────────────────────────
$ruleName = "WSL2-Minikube-InferVoyage"
netsh advfirewall firewall delete rule name=$ruleName 2>$null | Out-Null
netsh advfirewall firewall add rule name=$ruleName dir=in action=allow protocol=TCP localport="80,443,3000,8000" | Out-Null
Write-Host "  Firewall rule '$ruleName' updated." -ForegroundColor Green

Write-Host ""
Write-Host "Port forwarding configured!" -ForegroundColor Yellow
Write-Host ""
Write-Host "Open in browser:" -ForegroundColor White
Write-Host "  http://localhost          (frontend home)" -ForegroundColor Green
Write-Host "  http://localhost/register (register page)" -ForegroundColor Green
Write-Host "  http://localhost:3000     (alt URL)"       -ForegroundColor Green
Write-Host ""
Write-Host "Current portproxy rules:" -ForegroundColor Cyan
netsh interface portproxy show all
