# Launch the Flask viewer for captured baseline data.
# Open http://localhost:5050 once it starts.

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $projectRoot 'windows\.venv'
$python = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path $python)) {
    Write-Host "Creating venv at $venv..."
    python -m venv $venv
    & $python -m pip install --upgrade pip
    & $python -m pip install -r (Join-Path $projectRoot 'windows\requirements.txt')
}

Set-Location $projectRoot
& $python -m windows.viewer
