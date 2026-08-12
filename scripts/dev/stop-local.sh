#!/usr/bin/env bash
# Stops the backend/frontend processes started by start-local.sh. Does NOT touch
# MongoDB or Redis (both are Windows Services managed independently of this script —
# they keep running). Does NOT stop the worker — Ctrl+C that one directly. Never touches
# Docker in any way.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="$ROOT_DIR/scripts/dev/.local-run"

stop_pidfile() {
  local name="$1" pidfile="$RUN_DIR/$1.pid"
  if [ ! -f "$pidfile" ]; then
    echo "$name: no PID file found (not started via start-local.sh, or already stopped)."
    return
  fi
  local pid
  pid="$(cat "$pidfile")"
  if [ -z "$pid" ]; then
    rm -f "$pidfile"
    return
  fi
  echo "$name: stopping PID $pid..."
  # taskkill //T kills the whole process tree (npm -> vite, uvicorn -> reload workers) —
  # a plain `kill` often leaves child processes running on Windows.
  if command -v taskkill >/dev/null 2>&1; then
    taskkill //PID "$pid" //T //F >/dev/null 2>&1 || echo "$name: process $pid was already stopped."
  else
    kill "$pid" 2>/dev/null || echo "$name: process $pid was already stopped."
  fi
  rm -f "$pidfile"
}

stop_pidfile backend
stop_pidfile frontend

# Remove the generated backend/.env (copied from .env.local by start-local.sh/
# start-worker.sh) — keeps the working tree clean between sessions. Harmless either
# way: Full Docker Mode never reads this file, and it's already gitignored.
rm -f "$ROOT_DIR/backend/.env"

echo "Development Mode (backend + frontend) stopped. MongoDB/Redis were left running."
