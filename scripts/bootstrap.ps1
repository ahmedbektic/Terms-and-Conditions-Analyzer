param(
    [switch]$SkipNpm
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPath = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

Write-Host "Repository root: $repoRoot"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment at $venvPath"
    py -3.10 -m venv $venvPath
}

Write-Host "Installing backend Python dependencies"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $repoRoot "backend\requirements.txt")
& $venvPython -m pip install pytest black

if (-not $SkipNpm) {
    Write-Host "Installing frontend/workspace npm dependencies"
    Push-Location $repoRoot
    try {
        npm install
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "Skipping npm install"
}

Write-Host "Bootstrap complete."
Write-Host "Backend run command:"
Write-Host "$venvPython -m uvicorn app.main:app --app-dir backend --reload --env-file backend/.env --host 127.0.0.1 --port 8000"
Write-Host "Frontend run command:"
Write-Host "npm exec -w frontend vite -- --host 127.0.0.1 --port 5173"
