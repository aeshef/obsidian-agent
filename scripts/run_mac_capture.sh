#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"
export AGENT_ROOT="$ROOT"
RUNTIME="$(dirname "$ROOT")"
export PYTHONPATH="$ROOT:$RUNTIME/pydeps/finance:$RUNTIME/pydeps/planning${PYTHONPATH:+:$PYTHONPATH}"
PY="$(common_resolve_python_usable "$ROOT/finance_bot")"
INTERVAL="$("$PY" -c 'from planning_bot.services.mac_capture import enabled,config; print(config()["heartbeat_seconds"] if enabled() else "disabled")')"
[ "$INTERVAL" != disabled ] || exit 0
STATE="${MAC_CAPTURE_STATE:-$HOME/Library/Application Support/obsidian-agent/mac-capture}"
exec "$STATE/mac-capture" "$STATE/outbox" "$INTERVAL"
