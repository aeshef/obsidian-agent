#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"
export AGENT_ROOT="$ROOT"
export VAULT_PATH="$(common_resolve_vault "$ROOT")"
export LOCAL_VAULT="$VAULT_PATH"
RUNTIME="$(dirname "$ROOT")"
export PYTHONPATH="$ROOT:$RUNTIME/pydeps/finance:$RUNTIME/pydeps/planning${PYTHONPATH:+:$PYTHONPATH}"
PY="$(common_resolve_python_usable "$ROOT/finance_bot")"
exec "$PY" "$ROOT/scripts/mac_capture_worker.py"
