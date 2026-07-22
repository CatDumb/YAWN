[CmdletBinding()]
param(
    [switch]$ResetDatabase,
    [switch]$WithRedis
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $PSScriptRoot

function Assert-Command([string]$name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "Required command '$name' was not found in PATH."
    }
}

function Invoke-Checked([scriptblock]$command, [string]$failureMessage) {
    & $command
    if ($LASTEXITCODE -ne 0) {
        throw $failureMessage
    }
}

Assert-Command docker
Set-Location -LiteralPath $repositoryRoot

Invoke-Checked { docker compose version } "Docker Compose v2 is required. Start Docker Desktop, then run this script again."

$legacyComposeContainers = & docker compose --project-name wio-tracker ps --all --quiet
if ($LASTEXITCODE -ne 0) {
    throw "Unable to query the legacy WIO Tracker Compose project."
}

if ($ResetDatabase) {
    Write-Warning "Resetting Docker Compose data for YAWN. This deletes local PostgreSQL data."
    Invoke-Checked { docker compose down --volumes --remove-orphans } "Unable to reset Docker Compose services."
    if ($legacyComposeContainers) {
        Invoke-Checked { docker compose --project-name wio-tracker down --volumes --remove-orphans } "Unable to reset the legacy WIO Tracker Compose services."
    }

    # Remove only the legacy database made by the older launcher, if present.
    $legacyContainer = & docker ps --all --filter "name=^/wio-postgres$" --format "{{.Names}}"
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to query Docker for the legacy local database."
    }
    if ($legacyContainer -eq "wio-postgres") {
        Invoke-Checked { docker rm --force wio-postgres } "Unable to remove the legacy local database container."
        & docker volume rm wio-postgres-data 2>$null | Out-Null
    }
}
elseif ($legacyComposeContainers) {
    throw "Legacy WIO Tracker containers are still present and may hold ports 3000/8000. Stop them manually to keep their data, or rerun with -ResetDatabase to remove their local data before starting YAWN."
}

$composeArguments = @("compose", "up", "--build", "--detach", "--wait")
if ($WithRedis) {
    $composeArguments = @("compose", "--profile", "redis", "up", "--build", "--detach", "--wait")
}
Invoke-Checked { docker @composeArguments } "Unable to build and start the Docker Compose application."

Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend:  http://localhost:8000/health/"
Write-Host "Admin:    http://localhost:8000/admin/"
Write-Host "Containers: docker compose ps"
Write-Host "Logs:       docker compose logs --follow"
Write-Host "Create admin: docker compose exec backend python manage.py createsuperuser"
