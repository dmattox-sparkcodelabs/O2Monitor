New-NetFirewallRule -DisplayName "O2Monitor_Caddy" -Direction Inbound -Protocol TCP -LocalPort 7072 -Action Allow -Profile Private
Write-Host "Firewall rule added for port 7072"
Start-Sleep 3
