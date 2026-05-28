#!/bin/bash
# Watchdog planning_bot → единый scripts/watchdog.sh (poll mode)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
export WATCHDOG_BOT_ROOT="$ROOT"
export WATCHDOG_MODE=poll
export WATCHDOG_PGREP_PATTERN='python.*planning_bot.app.bot'
export WATCHDOG_PGREP_FALLBACK='planning_bot.app.bot'
export WATCHDOG_RUN_SCRIPT='./scripts/run.sh'
export WATCHDOG_LOG='logs/watchdog.log'
exec "$MONOREPO/scripts/watchdog.sh"
