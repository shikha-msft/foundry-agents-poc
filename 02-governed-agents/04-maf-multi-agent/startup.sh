#!/usr/bin/env sh
set -eu

exec python -m gunicorn \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-180}" \
  --worker-class uvicorn_worker.UvicornWorker \
  app.main:app
