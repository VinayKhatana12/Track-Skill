#!/usr/bin/env bash
# Production entrypoint (Render / any container host).
#
# Runs migrations and the idempotent demo seed before serving, so free tiers
# without shell access still get a migrated, seeded database on every deploy.
set -euo pipefail

echo "[start] applying migrations..."
python -m alembic upgrade head

echo "[start] seeding demo data (idempotent — safe on every restart)..."
python -m app.seed

echo "[start] launching uvicorn on port ${PORT:-8000}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
