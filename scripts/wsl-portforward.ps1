# WSL2 Port Forwarding Setup
# Run this script as Administrator whenever WSL2 IP changes or after restart
# Usage: .\scripts\wsl-portforward.ps1

# Get the current WSL IP dynamically
$wslIp = (wsl bash -c "ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d'/' -f1").Trim()

if (-not $wslIp) {
    Write-Error "Could not get WSL IP. Make sure WSL is running."
    exit 1
}

Write-Host "WSL IP: $wslIp" -ForegroundColor Cyan

# Ports to forward: localPort -> WSL port
$ports = @(80, 443, 8000, 8025, 8089, 3001, 9090, 5557)

# Remove existing portproxy rules for these ports
foreach ($port in $ports) {
    netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 2>$null
}

# Add new portproxy rules
foreach ($port in $ports) {
    netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$wslIp
    Write-Host "  Forwarding Windows:$port -> WSL($wslIp):$port" -ForegroundColor Green
}

# Add Windows Firewall rules (ignore if already exists)
$ruleName = "WSL2-AI-Platform"
netsh advfirewall firewall delete rule name=$ruleName 2>$null
netsh advfirewall firewall add rule name=$ruleName dir=in action=allow protocol=TCP localport="80,443,8000,8025,8089,3001,9090,5557"

Write-Host ""
Write-Host "Port forwarding configured!" -ForegroundColor Yellow
Write-Host "Open in browser: http://localhost" -ForegroundColor Green
Write-Host ""
Write-Host "Current portproxy rules:" -ForegroundColor Cyan
netsh interface portproxy show all
