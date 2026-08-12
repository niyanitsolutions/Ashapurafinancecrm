#!/usr/bin/env bash
# Full Docker Mode — the unchanged, production-shaped stack (Mongo, Redis, Backend,
# Worker, Frontend all containerized). Identical to running docker compose directly;
# this is only a convenience wrapper kept symmetric with the dev-mode scripts.
# deployment/docker-compose.yml itself is never modified by anything in scripts/dev/.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

docker compose -f deployment/docker-compose.yml up -d --build

echo
echo "Full Docker Mode is up. Frontend: http://localhost:5173  Backend health: http://localhost:8000/api/v1/health"
