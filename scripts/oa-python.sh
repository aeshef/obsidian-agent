#!/usr/bin/env bash
# Run a Python script with repo venv + .env loaded (onboarding-safe).
# Usage: ./scripts/oa-python.sh scripts/onboarding_interview.py next
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/setup/load_env.sh
source "$ROOT/scripts/setup/load_env.sh"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
PY="$(common_resolve_python "$ROOT/finance_bot")"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" "$@"
