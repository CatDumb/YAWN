[CmdletBinding()]
param(
    [switch]$ContainerBuild
)

$ErrorActionPreference = "Stop"

function Invoke-Check {
    param([string]$Name, [scriptblock]$Command)

    Write-Host "== $Name =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $repositoryRoot "backend")
try {
    Invoke-Check "Backend Ruff" { uv run ruff check . }
    Invoke-Check "Backend format" { uv run ruff format --check . }
    Invoke-Check "Backend tests" { uv run pytest -p no:cacheprovider }
    Invoke-Check "Migration drift" {
        uv run python manage.py makemigrations --check --dry-run --settings=config.settings.test
    }
    Invoke-Check "Django checks" { uv run python manage.py check --settings=config.settings.test }
    Invoke-Check "OpenAPI schema" {
        uv run python manage.py spectacular --validate --file schema.generated.yml --settings=config.settings.test
    }
} finally {
    Remove-Item -LiteralPath "schema.generated.yml" -ErrorAction SilentlyContinue
    Pop-Location
}

Push-Location (Join-Path $repositoryRoot "frontend")
try {
    Invoke-Check "Frontend format" { npm run format:check }
    Invoke-Check "Frontend lint" { npm run lint }
    Invoke-Check "Frontend types" { npm run typecheck }
    Invoke-Check "Frontend tests" { npm run test:coverage }
    Invoke-Check "Frontend build" { npm run build }
} finally {
    Pop-Location
}

if ($ContainerBuild) {
    Push-Location $repositoryRoot
    try {
        Invoke-Check "Container build" { docker compose build }
    } finally {
        Pop-Location
    }
}
