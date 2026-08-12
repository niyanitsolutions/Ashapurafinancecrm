# Full Docker Mode - the unchanged, production-shaped stack (Mongo, Redis, Backend,
# Worker, Frontend all containerized). Identical to running docker compose directly;
# this is only a convenience wrapper kept symmetric with the dev-mode scripts.
# deployment/docker-compose.yml itself is never modified by anything in scripts/dev/.
$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RootDir

docker compose -f deployment/docker-compose.yml up -d --build

Write-Host ""
Write-Host "Full Docker Mode is up. Frontend: http://localhost:5173  Backend health: http://localhost:8000/api/v1/health"
