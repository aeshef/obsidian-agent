#!/bin/zsh
# Полный цикл: синк БД с сервера + сборка дашборда.
# Для cron / launchd. Запускать из finance_bot.

set -e
BOT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$BOT_ROOT/.." && pwd)"
cd "$BOT_ROOT"

# shellcheck source=../../scripts/lib/common.sh
source "$MONOREPO/scripts/lib/common.sh"

# VAULT_PATH: из env или на 3 уровня вверх от finance_bot (finance_bot -> Agent -> 800_Автоматизация -> Vault)
VAULT_PATH="${VAULT_PATH:-$(cd "$BOT_ROOT/../../.." && pwd)}"
export VAULT_PATH

# obsidian_sync (шаг 6) сбрасывает PYTHONPATH — выставляем заново (shared + site-packages venv).
common_export_bot_pythonpath "$BOT_ROOT" "$MONOREPO"

# Чтобы matplotlib не падал под launchd (нет доступа к ~/.matplotlib)
export MPLCONFIGDIR="${MPLCONFIGDIR:-$BOT_ROOT/.cache/matplotlib}"
mkdir -p "$MPLCONFIGDIR"

LOG_DIR="$BOT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/finance_dashboard_daily.log"
exec 1> >(tee -a "$LOG_FILE") 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] VAULT_PATH=$VAULT_PATH MPLCONFIGDIR=$MPLCONFIGDIR"

export FINANCE_BUILD_DASHBOARD_AFTER_PULL=0
./scripts/sync_finance_db.sh

PYTHON="$(common_resolve_python_usable "$BOT_ROOT")"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PYTHON=$PYTHON"
"$PYTHON" scripts/build_finance_dashboard.py --vault "$VAULT_PATH"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK"
# Маркеры для check_sync_health: при ручном запуске или из obsidian_sync — отчёт видит последний успех
SYNC_DIR="$VAULT_PATH/.sync"
mkdir -p "$SYNC_DIR"
echo "$(date +%Y-%m-%d)" > "$SYNC_DIR/finance_dashboard_date.txt"
echo "$(date +%Y-%m-%dT%H:%M:%S)" > "$SYNC_DIR/finance_dashboard_last_ok.txt"
