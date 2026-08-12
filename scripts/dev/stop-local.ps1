# Stops the backend/frontend processes started by start-local.ps1. Does NOT touch
# MongoDB or Redis (both are Windows Services managed independently of this script -
# they keep running). Does NOT stop the worker - Ctrl+C that one directly. Never touches
# Docker in any way.
$ErrorActionPreference = "Continue"
$RunDir = Join-Path $PSScriptRoot ".local-run"

function Stop-LocalPid {
    param([string]$Name)
    $pidFile = Join-Path $RunDir "$Name.pid"
    if (-not (Test-Path $pidFile)) {
        Write-Host "$Name`: no PID file found (not started via start-local.ps1, or already stopped)."
        return
    }
    $procId = (Get-Content $pidFile -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($procId)) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        return
    }
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Write-Host "$Name`: process $procId was already stopped."
    } else {
        Write-Host "$Name`: stopping PID $procId (and its child processes)..."
        # taskkill /T kills the whole process tree (npm -> vite, uvicorn --reload's
        # subprocess) - Stop-Process alone often leaves children running on Windows.
        & taskkill /PID $procId /T /F | Out-Null
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

Stop-LocalPid -Name "backend"
Stop-LocalPid -Name "frontend"

# Remove the generated backend\.env (copied from .env.local by start-local.ps1/
# start-worker.ps1) - keeps the working tree clean between sessions. Harmless either
# way: Full Docker Mode never reads this file, and it's already gitignored.
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Remove-Item (Join-Path $RootDir "backend\.env") -Force -ErrorAction SilentlyContinue

Write-Host "Development Mode (backend + frontend) stopped. MongoDB/Redis were left running."
