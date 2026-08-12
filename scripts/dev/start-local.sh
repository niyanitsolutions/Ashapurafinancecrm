#!/usr/bin/env bash
# Local Development: starts FastAPI (uvicorn --reload) and Vite locally on bare Windows.
# MongoDB and Redis must already be running as locally installed Windows Services
# (standalone Mongo, no replica set — see backend/.env.local and docs/RUN_LOCAL.md for
# why that's safe today). Docker is never started by this script, for anything, under
# any circumstance — deployment/docker-compose.yml itself is never touched here either.
#
# Process spawning is delegated to a small PowerShell helper (_spawn-hidden.ps1), even
# though this is a bash script — verified live that Git Bash's own `cmd &`/`$!` does not
# reliably identify the real Windows process for a backgrounded uvicorn/npm child (a
# later `taskkill` on that PID misses the actual server), while Start-Process -PassThru
# reliably returns the true PID. Prefers `pwsh` (PowerShell 7) — verified present with an
# unrestricted-for-local-scripts policy; falls back to legacy `powershell.exe` with
# `-ExecutionPolicy Bypass` for this one invocation only (no persistent system change)
# since its default policy blocks running .ps1 files at all on a stock Windows install.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="$ROOT_DIR/scripts/dev/.local-run"
mkdir -p "$RUN_DIR"

ROOT_DIR_WIN="$(cygpath -w "$ROOT_DIR")"
HELPER_WIN="$ROOT_DIR_WIN\\scripts\\dev\\_spawn-hidden.ps1"
if command -v pwsh >/dev/null 2>&1; then
  PWSH_BIN="pwsh"
  PWSH_EXTRA=()
else
  PWSH_BIN="powershell.exe"
  PWSH_EXTRA=("-ExecutionPolicy" "Bypass")
fi

check_tcp() {
  (exec 3<>"/dev/tcp/$1/$2") 2>/dev/null && { exec 3>&- 3<&-; return 0; } || return 1
}

start_hidden() {
  # start_hidden <file> <space-separated-args> <workdir-win> <logfile-win> <pidfile> <pidfile-win>
  # -Arguments:"..." (colon form) is required, not "-Arguments" "...": PowerShell's
  # -File argument parser otherwise mistakes a value starting with "-" (e.g. our own
  # "-m uvicorn ...") for the start of a new, unrecognized parameter — verified live.
  # The PID is read back from a file (not captured via a pipe/$()) — verified live that
  # a long-running grandchild (uvicorn/vite) can inherit pwsh's own stdout handle when
  # Start-Process redirection is used, which would otherwise make `$(...)` hang forever
  # waiting for a pipe close that never happens while that grandchild keeps running.
  "$PWSH_BIN" -NoProfile "${PWSH_EXTRA[@]}" -File "$HELPER_WIN" \
    -FilePath "$1" -Arguments:"$2" -WorkingDirectory "$3" -LogFile "$4" -PidFile:"$6" \
    < /dev/null > /dev/null 2>&1
  cat "$5"
}

echo "== MongoDB =="
if check_tcp 127.0.0.1 27017; then
  echo "MongoDB service is running."
else
  echo "MongoDB service is not running."
  echo "Please start MongoDB."
  exit 1
fi

echo "== Redis =="
if check_tcp 127.0.0.1 6379; then
  echo "Redis service is running."
else
  echo "Redis service is not running."
  echo "Please start Redis."
  exit 1
fi

echo "== Backend =="
BACKEND_DIR="$ROOT_DIR/backend"
if [ ! -f "$BACKEND_DIR/.venv/Scripts/python.exe" ]; then
  echo "backend/.venv not found. Create it first:" >&2
  echo "  python -m venv .venv && source .venv/Scripts/activate && pip install -e '.[dev]'" >&2
  exit 1
fi
# Copy (not shell-export) so Settings' own env_file=".env" lookup (app/config/settings.py)
# picks this up inside every process — including uvicorn --reload's worker, which is
# re-spawned via Python's multiprocessing on Windows and does NOT reliably inherit
# shell-exported env vars (verified live: it raised "Settings: 4 validation errors,
# Field required" for mongo_uri/mongo_db_name/redis_url/jwt_secret_key when only
# exported). Re-reading its own file per-process sidesteps that entirely.
cp "$BACKEND_DIR/.env.local" "$BACKEND_DIR/.env"

VENV_PYTHON_WIN="$ROOT_DIR_WIN\\backend\\.venv\\Scripts\\python.exe"
BACKEND_DIR_WIN="$ROOT_DIR_WIN\\backend"
BACKEND_LOG_WIN="$ROOT_DIR_WIN\\scripts\\dev\\.local-run\\backend.log"
BACKEND_PIDFILE="$RUN_DIR/backend.pid"
BACKEND_PIDFILE_WIN="$ROOT_DIR_WIN\\scripts\\dev\\.local-run\\backend.pid"
BACKEND_PID="$(start_hidden "$VENV_PYTHON_WIN" "-m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" "$BACKEND_DIR_WIN" "$BACKEND_LOG_WIN" "$BACKEND_PIDFILE" "$BACKEND_PIDFILE_WIN")"
echo "Backend starting (PID $BACKEND_PID) — log: $RUN_DIR/backend.log"

echo "== Frontend =="
FRONTEND_DIR="$ROOT_DIR/frontend"
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "frontend/node_modules not found. Run 'npm install' first." >&2
  exit 1
fi
FRONTEND_DIR_WIN="$ROOT_DIR_WIN\\frontend"
FRONTEND_LOG_WIN="$ROOT_DIR_WIN\\scripts\\dev\\.local-run\\frontend.log"
FRONTEND_PIDFILE="$RUN_DIR/frontend.pid"
FRONTEND_PIDFILE_WIN="$ROOT_DIR_WIN\\scripts\\dev\\.local-run\\frontend.pid"
FRONTEND_PID="$(start_hidden "npm.cmd" "run dev" "$FRONTEND_DIR_WIN" "$FRONTEND_LOG_WIN" "$FRONTEND_PIDFILE" "$FRONTEND_PIDFILE_WIN")"
echo "Frontend starting (PID $FRONTEND_PID) — log: $RUN_DIR/frontend.log"

echo
echo "Development Mode is starting (backend + frontend, running hidden in the background)."
echo "  Frontend:       http://localhost:5173"
echo "  Backend health: http://localhost:8000/api/v1/health"
echo "  Logs:           tail -f \"$RUN_DIR/backend.log\"  /  \"$RUN_DIR/frontend.log\""
echo "  Worker (only when needed): bash scripts/dev/start-worker.sh"
echo "  Stop:           bash scripts/dev/stop-local.sh"
