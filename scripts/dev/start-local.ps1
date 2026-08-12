# Local Development: starts FastAPI (uvicorn --reload) and Vite locally on bare Windows.
# MongoDB and Redis must already be running as locally installed Windows Services
# (standalone Mongo, no replica set - see backend\.env.local and docs\RUN_LOCAL.md for why
# that's safe today). Docker is never started by this script, for anything, under any
# circumstance - deployment\docker-compose.yml itself is never touched here either.
$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$RunDir = Join-Path $PSScriptRoot ".local-run"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

function Test-TcpPort {
    param([string]$HostName, [int]$Port, [int]$TimeoutMs = 1000)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $task = $client.ConnectAsync($HostName, $Port)
        $ok = $task.Wait($TimeoutMs) -and $client.Connected
        $client.Close()
        return $ok
    } catch {
        return $false
    }
}

Write-Host "== MongoDB =="
if (Test-TcpPort -HostName "127.0.0.1" -Port 27017) {
    Write-Host "MongoDB service is running."
} else {
    Write-Host "MongoDB service is not running."
    Write-Host "Please start MongoDB."
    exit 1
}

Write-Host "== Redis =="
if (Test-TcpPort -HostName "127.0.0.1" -Port 6379) {
    Write-Host "Redis service is running."
} else {
    Write-Host "Redis service is not running."
    Write-Host "Please start Redis."
    exit 1
}

Write-Host "== Backend =="
$BackendDir = Join-Path $RootDir "backend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "backend\.venv not found. Create it first: python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -e '.[dev]'"
    exit 1
}

# Copy (not just $env: for this session) so Settings' own env_file=".env" lookup
# (app/config/settings.py) picks this up inside every process - including uvicorn
# --reload's worker, which is re-spawned via Python's multiprocessing on Windows and
# does NOT reliably inherit this session's $env: vars (verified live: it raised
# "Settings: 4 validation errors, Field required" for mongo_uri/mongo_db_name/
# redis_url/jwt_secret_key when only set via $env:). Re-reading its own file
# per-process sidesteps that entirely.
Copy-Item (Join-Path $BackendDir ".env.local") (Join-Path $BackendDir ".env") -Force

# Also set in this session, purely so the status message below can show the values.
Get-Content (Join-Path $BackendDir ".env.local") | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    $parts = $line -split "=", 2
    if ($parts.Length -eq 2) {
        Set-Item -Path "env:$($parts[0].Trim())" -Value $parts[1].Trim()
    }
}

$backendLog = Join-Path $RunDir "backend.log"
$backendProc = Start-Process -FilePath $VenvPython `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000" `
    -WorkingDirectory $BackendDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $backendLog -RedirectStandardError "$backendLog.err"
$backendProc.Id | Out-File -Encoding ascii (Join-Path $RunDir "backend.pid")
Write-Host "Backend starting (PID $($backendProc.Id)) - log: $backendLog"

Write-Host "== Frontend =="
$FrontendDir = Join-Path $RootDir "frontend"
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Error "frontend\node_modules not found. Run 'npm install' first."
    exit 1
}
$npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
if (-not $npmCmd) { $npmCmd = Get-Command npm -ErrorAction Stop }
$frontendLog = Join-Path $RunDir "frontend.log"
$frontendProc = Start-Process -FilePath $npmCmd.Source -ArgumentList "run", "dev" `
    -WorkingDirectory $FrontendDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $frontendLog -RedirectStandardError "$frontendLog.err"
$frontendProc.Id | Out-File -Encoding ascii (Join-Path $RunDir "frontend.pid")
Write-Host "Frontend starting (PID $($frontendProc.Id)) - log: $frontendLog"

Write-Host ""
Write-Host "Development Mode is starting (backend + frontend, running hidden in the background)."
Write-Host "  Frontend:       http://localhost:5173"
Write-Host "  Backend health: http://localhost:8000/api/v1/health"
Write-Host "  Logs:           Get-Content -Wait `"$backendLog`"   /   Get-Content -Wait `"$frontendLog`""
Write-Host "  Worker (only when needed): .\scripts\dev\start-worker.ps1"
Write-Host "  Stop:           .\scripts\dev\stop-local.ps1"
