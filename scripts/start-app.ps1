[CmdletBinding()]
param(
    [switch]$ResetDatabase
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

if ($ResetDatabase) {
    Write-Warning "Resetting Docker Compose data for YAWN. This deletes local PostgreSQL data."
    Invoke-Checked { docker compose down --volumes --remove-orphans } "Unable to reset Docker Compose services."
}

Invoke-Checked { docker compose up --build --detach --wait } "Unable to build and start the Docker Compose application."

Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend:  http://localhost:8000/health/"
Write-Host "Admin:    http://localhost:8000/admin/"
Write-Host "Containers: docker compose ps"
Write-Host "Logs:       docker compose logs --follow"
Write-Host "Create admin: docker compose exec backend python manage.py createsuperuser"
