param(
    [string]$Action = "help",
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Show-Usage {
    Write-Host "Usage:"
    Write-Host "  ./scripts/dev.ps1 run docker"
    Write-Host "  ./scripts/dev.ps1 run preview"
    Write-Host "  ./scripts/dev.ps1 rebuild extension"
    Write-Host "  ./scripts/dev.ps1 rebuild docker"
}

function Invoke-InRepo([scriptblock]$Command) {
    Push-Location $repoRoot
    try {
        & $Command
    }
    finally {
        Pop-Location
    }
}

switch ($Action.ToLowerInvariant()) {
    "help" {
        Show-Usage
    }
    "run" {
        switch ($Target.ToLowerInvariant()) {
            "docker" {
                Invoke-InRepo { docker compose up }
            }
            "preview" {
                Invoke-InRepo { npm run preview:frontend }
            }
            default {
                throw "Unsupported run target '$Target'. Use docker or preview."
            }
        }
    }
    "rebuild" {
        switch ($Target.ToLowerInvariant()) {
            "extension" {
                Invoke-InRepo { npm install --prefix extension --no-audit --no-fund }
            }
            "docker" {
                Invoke-InRepo { docker compose build backend frontend }
            }
            default {
                throw "Unsupported rebuild target '$Target'. Use extension or docker."
            }
        }
    }
    default {
        throw "Unsupported action '$Action'. Use run, rebuild, or help."
    }
}
