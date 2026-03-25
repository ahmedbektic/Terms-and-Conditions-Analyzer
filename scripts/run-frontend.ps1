$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Push-Location $repoRoot
try {
    npm run -w frontend dev -- --host 127.0.0.1 --port 5173
}
finally {
    Pop-Location
}
