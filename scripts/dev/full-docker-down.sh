#!/usr/bin/env bash
# Stops and removes every Full Docker Mode container (data volumes are kept — pass -v
# to also wipe them). If you were instead in Development Mode, use env-dev-down.sh.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

docker compose -f deployment/docker-compose.yml down
