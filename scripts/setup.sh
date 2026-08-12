#!/usr/bin/env bash
# One-shot local bootstrap: env files + bring up the Docker stack.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

for stage in development staging production; do
  if [ ! -f "backend/.env.${stage}" ]; then
    cp backend/.env.example "backend/.env.${stage}"
    echo "Created backend/.env.${stage} from example — fill in real values before non-local use."
  fi
done

if [ ! -f "frontend/.env.development" ]; then
  cp frontend/.env.example frontend/.env.development
fi

echo "Starting Docker stack (mongo, mongo-init, redis, backend, worker, frontend)..."
docker compose -f deployment/docker-compose.yml up -d

echo "Done. Frontend: http://localhost:5173  Backend health: http://localhost:8000/api/v1/health"
