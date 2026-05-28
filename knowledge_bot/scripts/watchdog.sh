#!/usr/bin/env bash
# Watchdog knowledge_bot → единый scripts/watchdog.sh (supervisor mode + flock)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
export WATCHDOG_BOT_ROOT="$ROOT"
export WATCHDOG_MODE=supervisor
export WATCHDOG_RUN_SCRIPT='./scripts/run.sh'
export WATCHDOG_LOG='logs/watchdog.log'
export WATCHDOG_LOCK_FILE='/tmp/knowledge_bot_watchdog.lock'
export WATCHDOG_INITIAL_BACKOFF=2
export WATCHDOG_MAX_BACKOFF=60
exec "$MONOREPO/scripts/watchdog.sh"
