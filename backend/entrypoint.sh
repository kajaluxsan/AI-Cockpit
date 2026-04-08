#!/usr/bin/env bash
# RecruiterAI backend container entrypoint.
#
# 1. Wait for Postgres to accept connections (so the very first compose-up
#    doesn't race the DB).
# 2. Run `alembic upgrade head` so any pending migrations (e.g. the CRM
#    extension migration) are applied automatically.
# 3. Hand off to the app process (uvicorn by default; overridable via $@).

set -euo pipefail

DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-recruiterai}"
DB_NAME="${POSTGRES_DB:-recruiterai}"

echo "[entrypoint] Waiting for Postgres at ${DB_HOST}:${DB_PORT}..."
for i in $(seq 1 60); do
  if (echo > /dev/tcp/"${DB_HOST}"/"${DB_PORT}") 2>/dev/null; then
    echo "[entrypoint] Postgres is reachable"
    break
  fi
  if [ "$i" = "60" ]; then
    echo "[entrypoint] ERROR: Postgres at ${DB_HOST}:${DB_PORT} not reachable after 60s" >&2
    exit 1
  fi
  sleep 1
done

echo "[entrypoint] Running alembic upgrade head"
uv run alembic upgrade head

echo "[entrypoint] Starting application: $*"
exec "$@"
