# Development Mode: run the Arq worker locally, in the foreground - start only when
# testing reminder/notification (Module 6D) or communication (Module 9C) features,
# since those are the only things that depend on its cron jobs. Ctrl+C to stop; not
# tracked by stop-local.ps1 (that only manages backend/frontend). Requires MongoDB
# (local Windows Service) and Redis already reachable - run start-local.ps1 first, or
# ensure both are up yourself.
$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location (Join-Path $RootDir "backend")

if (-not (Test-Path ".venv")) {
    Write-Error "backend\.venv not found - see start-local.ps1 for setup."
    exit 1
}
& .\.venv\Scripts\Activate.ps1

# Copy (not just $env: for this session) so Settings' own env_file=".env" lookup picks
# this up reliably - see start-local.ps1 for why session env vars alone aren't safe on
# Windows for a re-spawned Python process.
Copy-Item ".env.local" ".env" -Force

Write-Host "Starting Arq worker (foreground - Ctrl+C to stop), config from backend\.env.local"
arq app.worker.worker_settings.WorkerSettings
