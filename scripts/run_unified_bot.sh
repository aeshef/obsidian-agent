#!/usr/bin/env bash
# Start unified Telegram bot (loads .env, uses finance_bot venv).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/setup/load_env.sh
source "$ROOT/scripts/setup/load_env.sh"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
PY="$(common_resolve_python "$ROOT/finance_bot")"
export PYTHONPATH="$ROOT:$ROOT/finance_bot${PYTHONPATH:+:$PYTHONPATH}"
if [[ -z "${TELEGRAM_UNIFIED_BOT_TOKEN:-}" && -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "TELEGRAM_UNIFIED_BOT_TOKEN missing — run: ./scripts/oa-python.sh scripts/setup/env_tools.py set TELEGRAM_UNIFIED_BOT_TOKEN '...'" >&2
  exit 1
fi
cd "$ROOT"
exec "$PY" -m unified_bot.main
