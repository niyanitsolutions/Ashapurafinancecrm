#!/usr/bin/env bash
# Development Mode: run the Arq worker locally, in the foreground — start only when
# testing reminder/notification (Module 6D) or communication (Module 9C) features,
# since those are the only things that depend on its cron jobs. Ctrl+C to stop; not
# tracked by stop-local.sh (that only manages backend/frontend). Requires MongoDB
# (local Windows Service) and Redis already reachable — run start-local.sh first, or
# ensure both are up yourself.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR/backend"

if [ ! -d .venv ]; then
  echo "backend/.venv not found — see scripts/dev/start-local.sh for setup." >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/Scripts/activate

# Copy (not shell-export) so Settings' own env_file=".env" lookup picks this up
# reliably — see start-local.sh for why exporting into the shell alone isn't safe on
# Windows for a re-spawned Python process.
cp .env.local .env

echo "Starting Arq worker (foreground — Ctrl+C to stop), config from backend/.env.local"
exec arq app.worker.worker_settings.WorkerSettings
