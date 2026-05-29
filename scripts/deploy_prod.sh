#!/usr/bin/env bash
# Одна команда: дописать agent-переменные на сервер + залить код + перезапустить боты.
#
#   ./scripts/deploy_prod.sh
#   ./scripts/deploy_prod.sh --install-deps
#   ./scripts/deploy_prod.sh --dry-run
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"
common_require_server

SERVER_BOTS="$(common_server_bots)"
EXTRA=()
DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1; EXTRA+=("$arg") ;;
    --install-deps|--no-restart) EXTRA+=("$arg") ;;
    *) echo "Неизвестный флаг: $arg (допустимо: --install-deps, --dry-run, --no-restart)" >&2; exit 2 ;;
  esac
done

EXCLUDES=(
  --exclude='.git' --exclude='.DS_Store' --exclude='__pycache__/' --exclude='*.pyc'
  --exclude='venv/' --exclude='.venv/' --exclude='.venv' --exclude='venv' --exclude='.cache/'
  --exclude='logs/' --exclude='data/' --exclude='.env'
  --exclude='*.db' --exclude='*.db-shm' --exclude='*.db-wal'
)

_rsync_extra() {
  local name="$1"
  local src="$ROOT/$name/"
  local dst="$SERVER:$SERVER_BOTS/$name/"
  local flags="-avz"
  [ "$DRY" = 1 ] && flags="-navz"
  if [ "$DRY" = 0 ]; then
    common_ssh "mkdir -p '$SERVER_BOTS/$name'"
  fi
  echo "🔄 rsync $name → $dst"
  rsync $flags "${EXCLUDES[@]}" "$src" "$dst"
}

echo "════════════════ deploy_prod ════════════════"

if [ "$DRY" = 1 ]; then
  "$ROOT/scripts/patch_server_env.sh" --dry-run
else
  "$ROOT/scripts/patch_server_env.sh"
fi

_rsync_extra "config/agent"
_rsync_extra "unified_bot"

if [ ${#EXTRA[@]} -gt 0 ]; then
  "$ROOT/scripts/deploy.sh" --component all "${EXTRA[@]}"
else
  "$ROOT/scripts/deploy.sh" --component all
fi

echo "✅ deploy_prod готово"
echo "   Серверный .env: $SERVER:$SERVER_BOTS/.env"
echo "   Unified-бот (опционально): ssh $SERVER 'cd $SERVER_BOTS && set -a && source .env && set +a && export DEPLOY_MODE=single PYTHONPATH=$SERVER_BOTS:$SERVER_BOTS/finance_bot:$SERVER_BOTS/knowledge_bot:$SERVER_BOTS/planning_bot && finance_bot/.venv/bin/python -m unified_bot.main'"
