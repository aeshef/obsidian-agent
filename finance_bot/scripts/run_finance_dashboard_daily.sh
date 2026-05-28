#!/bin/zsh
# Полный цикл: синк БД с сервера + сборка дашборда.
# Для cron / launchd. Запускать из finance_bot.

set -e
BOT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BOT_ROOT"

# VAULT_PATH: из env или на 3 уровня вверх от finance_bot (finance_bot -> Agent -> 800_Автоматизация -> Vault)
VAULT_PATH="${VAULT_PATH:-$(cd "$BOT_ROOT/../../.." && pwd)}"
export VAULT_PATH

# obsidian_sync (и др.) могут оставить PYTHONPATH с чужим venv (например knowledge_bot).
# Тогда python3 из Homebrew подтягивает numpy из site-packages другой версии Python → ImportError в matplotlib.
unset PYTHONPATH

# Чтобы matplotlib не падал под launchd (нет доступа к ~/.matplotlib)
export MPLCONFIGDIR="${MPLCONFIGDIR:-$BOT_ROOT/.cache/matplotlib}"
mkdir -p "$MPLCONFIGDIR"

LOG_DIR="$BOT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/finance_dashboard_daily.log"
exec 1> >(tee -a "$LOG_FILE") 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] VAULT_PATH=$VAULT_PATH MPLCONFIGDIR=$MPLCONFIGDIR"

./scripts/sync_finance_db.sh
# Используем .venv если есть (содержит sqlalchemy + matplotlib), иначе системный python3
PYTHON="${BOT_ROOT}/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"
"$PYTHON" scripts/build_finance_dashboard.py --vault "$VAULT_PATH"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK"
# Маркеры для check_sync_health: при ручном запуске или из obsidian_sync — отчёт видит последний успех
SYNC_DIR="$VAULT_PATH/.sync"
mkdir -p "$SYNC_DIR"
echo "$(date +%Y-%m-%d)" > "$SYNC_DIR/finance_dashboard_date.txt"
echo "$(date +%Y-%m-%dT%H:%M:%S)" > "$SYNC_DIR/finance_dashboard_last_ok.txt"
