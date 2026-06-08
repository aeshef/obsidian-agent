#!/usr/bin/env zsh
# Пересборка markdown + PNG дашборда из finance.db (не делает sync с сервера).
# Запуск из каталога finance_bot:
#   ./scripts/run_finance_dashboard.sh
# Переменные:
#   VAULT_PATH — корень Obsidian (иначе ~/Documents/Obsidian Vault или ~/Obsidian Vault)
#   FINANCE_DB_PATH — явный путь к finance.db (по умолчанию $VAULT_PATH/300_Дашборды/Данные/finance.db)
#   FINANCE_DASHBOARD_USER_ID — user_id в БД (по умолчанию 1)
# Доп. аргументы передаются в build_finance_dashboard.py, например: --out /tmp/x.md

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
cd "$ROOT"

# shellcheck source=../../scripts/lib/common.sh
source "$MONOREPO/scripts/lib/common.sh"
# shellcheck source=../../scripts/lib/vault_paths_defaults.sh
source "$MONOREPO/scripts/lib/vault_paths_defaults.sh"
vault_paths_load_from_agent "$MONOREPO" || true

if [[ -z "${VAULT_PATH:-}" ]]; then
  if [[ -d "$HOME/Documents/Obsidian Vault" ]]; then
    VAULT_PATH="$HOME/Documents/Obsidian Vault"
  else
    VAULT_PATH="$HOME/Obsidian Vault"
  fi
fi

DB_PATH="${FINANCE_DB_PATH:-$VAULT_PATH/${VAULT_FOLDER_DASHBOARDS:-300_Dashboards}/${VAULT_DASH_DATA:-Data}/finance.db}"
USER_ID="${FINANCE_DASHBOARD_USER_ID:-1}"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.cache/matplotlib}"
mkdir -p "$MPLCONFIGDIR"

common_export_bot_pythonpath "$ROOT" "$MONOREPO"
PY="$(common_resolve_python_usable "$ROOT")"

if ! "$PY" -c "import matplotlib" 2>/dev/null; then
  echo "ERROR: matplotlib недоступен для $PY (LaunchAgent: нужен Homebrew python той же версии, что venv)." >&2
  echo "Проверь: \"$PY\" -c 'import matplotlib' и site-packages в PYTHONPATH." >&2
  exit 1
fi

exec "$PY" scripts/build_finance_dashboard.py \
  --vault "$VAULT_PATH" \
  --db "$DB_PATH" \
  --user-id "$USER_ID" \
  "$@"
