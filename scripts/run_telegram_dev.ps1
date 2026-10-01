$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Run .\scripts\run_local.ps1 first to install the project dependencies.'
}
Push-Location $projectRoot
try {
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue) -and
        -not (Test-Path -LiteralPath (Join-Path $projectRoot '.tools\cloudflared.exe'))) {
        & $pythonPath scripts/install_cloudflared.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    & $pythonPath scripts/run_telegram_dev.py
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
