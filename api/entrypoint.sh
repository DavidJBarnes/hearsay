#!/usr/bin/env bash
# API entrypoint: apply migrations, then serve the gateway.
set -euo pipefail

echo "Applying database migrations..."
alembic upgrade head

echo "Starting Hearsay API on ${HEARSAY_API_HOST:-0.0.0.0}:${HEARSAY_API_PORT:-8000}"
exec uvicorn hearsay_api.main:app \
  --host "${HEARSAY_API_HOST:-0.0.0.0}" \
  --port "${HEARSAY_API_PORT:-8000}"
