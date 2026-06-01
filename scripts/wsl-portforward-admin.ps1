$wslIp = (wsl bash -c "hostname -I").Split()[0].Trim()
Write-Host "WSL IP: $wslIp" -ForegroundColor Cyan

$ports = @(80, 443, 8000, 8025, 8089, 3001, 9090)

foreach ($port in $ports) {
    netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 2>$null
    netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$wslIp
    Write-Host "  [OK] localhost:$port -> WSL($wslIp):$port" -ForegroundColor Green
}

netsh advfirewall firewall delete rule name="WSL2-AI-Platform" 2>$null
netsh advfirewall firewall add rule name="WSL2-AI-Platform" dir=in action=allow protocol=TCP localport="80,443,8000,8025,8089,3001,9090" | Out-Null

Write-Host ""
Write-Host "All ports forwarded successfully!" -ForegroundColor Yellow
Write-Host ""
Write-Host "Open in browser: http://localhost" -ForegroundColor Green
Write-Host ""
Write-Host "Current rules:" -ForegroundColor Cyan
netsh interface portproxy show all
Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
