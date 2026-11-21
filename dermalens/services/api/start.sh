#!/usr/bin/env sh
# Container start for cloud hosts: create tables, make sure an admin exists,
# load reference data (safe to repeat), then serve on $PORT.
set -e
python -m app.schema_upgrade
if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
  python -m app.create_admin "$ADMIN_EMAIL" "${ADMIN_NAME:-Admin}"
fi
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
