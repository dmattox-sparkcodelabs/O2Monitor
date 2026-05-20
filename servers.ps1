# servers.ps1 - Dev server control for O2Monitor
# Usage: .\servers.ps1 <command>
# Commands: start, stop, restart, status

param(
    [Parameter(Position=0)]
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Command = "status"
)

$ProjectRoot = $PSScriptRoot
$NextPort = 6013
$FuncPort = 7071
$CosmosPort = 8081
$CosmosExe = "C:\Program Files\Azure Cosmos DB Emulator\Microsoft.Azure.Cosmos.Emulator.exe"

function Get-ServerStatus {
    $cosmos = try { (Test-NetConnection -ComputerName localhost -Port $CosmosPort -WarningAction SilentlyContinue).TcpTestSucceeded } catch { $false }
    $func = try { (Test-NetConnection -ComputerName localhost -Port $FuncPort -WarningAction SilentlyContinue).TcpTestSucceeded } catch { $false }
    $next = try { (Test-NetConnection -ComputerName localhost -Port $NextPort -WarningAction SilentlyContinue).TcpTestSucceeded } catch { $false }

    Write-Host ""
    Write-Host "  O2Monitor Dev Servers" -ForegroundColor Cyan
    Write-Host "  =====================" -ForegroundColor DarkCyan
    $cosmosLabel = if ($cosmos) { "Running" } else { "Stopped" }; $cosmosColor = if ($cosmos) { "Green" } else { "Red" }
    $funcLabel   = if ($func)   { "Running" } else { "Stopped" }; $funcColor   = if ($func)   { "Green" } else { "Red" }
    $nextLabel   = if ($next)   { "Running" } else { "Stopped" }; $nextColor   = if ($next)   { "Green" } else { "Red" }
    Write-Host "  Cosmos DB Emulator : $cosmosLabel (port $CosmosPort)" -ForegroundColor $cosmosColor
    Write-Host "  Azure Functions API: $funcLabel (port $FuncPort)" -ForegroundColor $funcColor
    Write-Host "  Next.js Frontend   : $nextLabel (port $NextPort)" -ForegroundColor $nextColor
    Write-Host ""
}

function Start-Servers {
    # 1. Cosmos DB Emulator
    $cosmosRunning = try { (Test-NetConnection -ComputerName localhost -Port $CosmosPort -WarningAction SilentlyContinue).TcpTestSucceeded } catch { $false }
    if (-not $cosmosRunning) {
        if (Test-Path $CosmosExe) {
            Write-Host "  Starting Cosmos DB Emulator..." -ForegroundColor Yellow
            & $CosmosExe /NoUI 2>$null
            $timeout = 60
            while ($timeout -gt 0) {
                Start-Sleep -Seconds 2
                $timeout -= 2
                $up = try { (Test-NetConnection -ComputerName localhost -Port $CosmosPort -WarningAction SilentlyContinue).TcpTestSucceeded } catch { $false }
                if ($up) { break }
            }
            if ($timeout -le 0) {
                Write-Host "  Cosmos DB Emulator did not start in time" -ForegroundColor Red
            } else {
                Write-Host "  Cosmos DB Emulator started" -ForegroundColor Green
            }
        } else {
            Write-Host "  Cosmos DB Emulator not found at $CosmosExe" -ForegroundColor Red
        }
    } else {
        Write-Host "  Cosmos DB Emulator already running" -ForegroundColor Green
    }

    # 2. Azure Functions API
    $funcRunning = try { (Test-NetConnection -ComputerName localhost -Port $FuncPort -WarningAction SilentlyContinue).TcpTestSucceeded } catch { $false }
    if (-not $funcRunning) {
        Write-Host "  Starting Azure Functions API..." -ForegroundColor Yellow
        Start-Process pwsh -ArgumentList "-NoProfile", "-Command", "Set-Location '$ProjectRoot\api'; npx func start" -WindowStyle Minimized
        Start-Sleep -Seconds 5
        Write-Host "  Azure Functions API started" -ForegroundColor Green
    } else {
        Write-Host "  Azure Functions API already running" -ForegroundColor Green
    }

    # 3. Next.js Frontend
    $nextRunning = try { (Test-NetConnection -ComputerName localhost -Port $NextPort -WarningAction SilentlyContinue).TcpTestSucceeded } catch { $false }
    if (-not $nextRunning) {
        Write-Host "  Starting Next.js frontend..." -ForegroundColor Yellow
        Start-Process pwsh -ArgumentList "-NoProfile", "-Command", "Set-Location '$ProjectRoot\web'; npx next dev -H 0.0.0.0 -p $NextPort" -WindowStyle Minimized
        Start-Sleep -Seconds 3
        Write-Host "  Next.js frontend started" -ForegroundColor Green
    } else {
        Write-Host "  Next.js frontend already running" -ForegroundColor Green
    }

    Write-Host ""
    Get-ServerStatus
}

function Stop-Servers {
    # Stop Next.js on our port
    $nextPids = (Get-NetTCPConnection -LocalPort $NextPort -ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique
    foreach ($pid in $nextPids) {
        if ($pid -and $pid -ne 0) {
            Write-Host "  Stopping Next.js (PID $pid)..." -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }

    # Stop Azure Functions on our port
    $funcPids = (Get-NetTCPConnection -LocalPort $FuncPort -ErrorAction SilentlyContinue).OwningProcess | Sort-Object -Unique
    foreach ($pid in $funcPids) {
        if ($pid -and $pid -ne 0) {
            Write-Host "  Stopping Azure Functions (PID $pid)..." -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host "  Servers stopped (Cosmos DB Emulator left running)" -ForegroundColor Green
    Write-Host ""
}

switch ($Command) {
    "start"   { Start-Servers }
    "stop"    { Stop-Servers }
    "restart" { Stop-Servers; Start-Sleep -Seconds 2; Start-Servers }
    "status"  { Get-ServerStatus }
}
