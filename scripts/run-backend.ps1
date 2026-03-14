$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$envFile = Join-Path $repoRoot "backend\.env"

if (-not (Test-Path $venvPython)) {
    throw "Missing virtual environment Python at $venvPython. Run scripts/bootstrap.ps1 first."
}

if (-not (Test-Path $envFile)) {
    Write-Warning "backend/.env not found. Using process environment only."
    & $venvPython -m uvicorn app.main:app --app-dir (Join-Path $repoRoot "backend") --reload --host 127.0.0.1 --port 8000
    exit $LASTEXITCODE
}

& $venvPython -m uvicorn app.main:app --app-dir (Join-Path $repoRoot "backend") --reload --env-file $envFile --host 127.0.0.1 --port 8000

