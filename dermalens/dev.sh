#!/usr/bin/env bash
# Run the API locally with SQLite and the in-process stub model.
#   ./dev.sh            -> API on http://localhost:8000 (docs at /docs)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT/packages/rules:$ROOT/services/inference:$ROOT/services/api"
cd "$ROOT/services/api"
python -m app.seed
exec uvicorn app.main:app --reload --port 8000
