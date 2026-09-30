#!/usr/bin/env bash
# Run unified bot against the English demo vault — does NOT edit .env.
#
# Order:
#   1) source .env          → tokens / LLM / your normal secrets
#   2) source .env.demo     → overlay VAULT_PATH, AGENT_LOCALE=en, FINANCE_DB_PATH, …
#   3) start unified_bot
#
# Setup once:
#   cp .env.demo.example .env.demo
#   # edit DEMO vault path if needed
#   PYTHONPATH=. ./scripts/oa-python.sh scripts/seed_demo_vault.py --vault "…/demo-vault-en"
#
# Usage:
#   ./scripts/run_unified_bot_demo.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "missing $ROOT/.env (need tokens). Demo overlay alone is not enough." >&2
  exit 1
fi
if [[ ! -f "$ROOT/.env.demo" ]]; then
  echo "missing $ROOT/.env.demo — copy from .env.demo.example and set vault paths." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
# Overlay AFTER .env so demo paths win for this process only.
# shellcheck disable=SC1091
source "$ROOT/.env.demo"
set +a

export AGENT_ROOT="${AGENT_ROOT:-$ROOT}"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
PY="$(common_resolve_python "$ROOT/finance_bot")"
export PYTHONPATH="$ROOT:$ROOT/finance_bot${PYTHONPATH:+:$PYTHONPATH}"

if [[ -z "${TELEGRAM_UNIFIED_BOT_TOKEN:-}" && -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
  echo "TELEGRAM_UNIFIED_BOT_TOKEN missing in .env" >&2
  exit 1
fi
if [[ -z "${VAULT_PATH:-}" ]]; then
  echo "VAULT_PATH empty after .env.demo overlay" >&2
  exit 1
fi

echo "demo mode: VAULT_PATH=$VAULT_PATH"
echo "demo mode: AGENT_LOCALE=${AGENT_LOCALE:-?} AGENT_EN_STRICT=${AGENT_EN_STRICT:-?} BASE_CURRENCY=${BASE_CURRENCY:-?}"
echo "demo mode: FINANCE_DB_PATH=${FINANCE_DB_PATH:-default}"
echo "(your .env file on disk was not modified)"
cd "$ROOT"
exec "$PY" -m unified_bot.main
