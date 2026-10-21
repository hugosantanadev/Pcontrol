# Libera o PControl no Firewall do Windows (precisa rodar como administrador).
# Só aceita conexões da rede local e do Tailscale; o resto da internet continua bloqueado.
param([int]$Port = 8765, [int]$DiscoveryPort = 8766)

$remote = @("LocalSubnet", "100.64.0.0/10")
Get-NetFirewallRule -DisplayName "PControl*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "PControl (app)" -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort $Port -RemoteAddress $remote -Profile Any | Out-Null
New-NetFirewallRule -DisplayName "PControl (busca na rede)" -Direction Inbound -Action Allow -Protocol UDP `
    -LocalPort $DiscoveryPort -RemoteAddress $remote -Profile Any | Out-Null
Write-Host "Firewall liberado para o PControl (portas $Port/TCP e $DiscoveryPort/UDP)."
