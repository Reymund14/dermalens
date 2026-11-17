#!/usr/bin/env bash
# Run the API locally with SQLite and the in-process stub model.
#   ./dev.sh            -> API on http://localhost:8000 (docs at /docs)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT/packages/rules:$ROOT/services/inference:$ROOT/services/api"
# Throwaway secrets kept in a gitignored file so local data survives restarts.
# Real deployments set their own and never use this file.
SECRETS="$ROOT/services/api/.dev-secrets"
if [ ! -f "$SECRETS" ]; then
  printf 'JWT_SECRET=%s\nDATA_KEY=%s\n' \
    "$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
    "$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')" > "$SECRETS"
fi
export JWT_SECRET="${JWT_SECRET:-$(grep '^JWT_SECRET=' "$SECRETS" | cut -d= -f2-)}"
export DATA_KEY="${DATA_KEY:-$(grep '^DATA_KEY=' "$SECRETS" | cut -d= -f2-)}"
export SEED_DEV_ACCOUNTS="${SEED_DEV_ACCOUNTS:-1}"
cd "$ROOT/services/api"
python -m app.seed
exec uvicorn app.main:app --reload --port 8000
