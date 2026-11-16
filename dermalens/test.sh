#!/usr/bin/env bash
# Run every Python test suite.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT/packages/rules:$ROOT/services/inference:$ROOT/services/api"
(cd "$ROOT/packages/rules" && python -m pytest -q)
(cd "$ROOT/services/inference" && python -m pytest -q)
(cd "$ROOT/services/api" && python -m pytest -q -p no:warnings)
(cd "$ROOT/ml" && python -m pytest -q)
