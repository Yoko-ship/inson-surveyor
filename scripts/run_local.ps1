$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    $localUv = Join-Path $projectRoot '.tools\uv-package\bin\uv.exe'
    if ($uvCommand) {
        $uvPath = $uvCommand.Source
    } elseif (Test-Path -LiteralPath $localUv) {
        $uvPath = $localUv
    } else {
        throw 'uv is required. Install it with: python -m pip install uv; then reopen PowerShell.'
    }
    & $uvPath sync --frozen --cache-dir (Join-Path $projectRoot '.tools\uv-cache')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') scripts/run_local.py
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
