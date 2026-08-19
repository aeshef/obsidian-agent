#!/usr/bin/env zsh
# Пересборка markdown + PNG дашборда из finance.db (не делает sync с сервера).
# Запуск из каталога finance_bot:
#   ./scripts/run_finance_dashboard.sh
# Переменные:
#   VAULT_PATH — Obsidian vault root; env/platform config is required.
#   FINANCE_DB_PATH — явный путь к finance.db (по умолчанию $VAULT_PATH/300_Дашборды/Данные/finance.db)
#   FINANCE_DASHBOARD_USER_ID — user_id в БД (по умолчанию 1)
# Доп. аргументы передаются в build_finance_dashboard.py, например: --out /tmp/x.md

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
cd "$ROOT"

# shellcheck source=../../scripts/lib/common.sh
source "$MONOREPO/scripts/lib/common.sh"
common_load_env "$MONOREPO" || true
# shellcheck source=../../scripts/lib/vault_paths_defaults.sh
source "$MONOREPO/scripts/lib/vault_paths_defaults.sh"
vault_paths_load_from_agent "$MONOREPO" || true

if [[ -z "${VAULT_PATH:-}" ]]; then
  VAULT_PATH="$(common_resolve_vault "$MONOREPO" 2>/dev/null || true)"
fi
if [[ -z "${VAULT_PATH:-}" ]]; then
  echo "run_finance_dashboard: VAULT_PATH is not configured" >&2
  exit 1
fi

# Defaults follow vault_paths.yaml (ru: 300_Дашборды/Данные) — never English ghosts.
_DB_DASH="${VAULT_FOLDER_DASHBOARDS:-}"
_DB_DATA="${VAULT_DASH_DATA:-}"
if [[ -z "$_DB_DASH" || -z "$_DB_DATA" ]]; then
  echo "run_finance_dashboard: vault dashboards/data paths unset after vault_paths_load" >&2
  exit 1
fi
DB_PATH="${FINANCE_DB_PATH:-$VAULT_PATH/$_DB_DASH/$_DB_DATA/finance.db}"
USER_ID="${FINANCE_DASHBOARD_USER_ID:-1}"

export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/.cache/matplotlib}"
mkdir -p "$MPLCONFIGDIR"

common_export_bot_pythonpath "$ROOT" "$MONOREPO"
PY="$(common_resolve_python_usable "$ROOT")"

if ! "$PY" -c "import matplotlib" 2>/dev/null; then
  echo "ERROR: matplotlib is unavailable for $PY (LaunchAgent needs a compatible runtime Python)." >&2
  echo "Check: \"$PY\" -c 'import matplotlib' and site-packages in PYTHONPATH." >&2
  exit 1
fi

common_run_python_script "$PY" "$ROOT/scripts/build_finance_dashboard.py" \
  --vault "$VAULT_PATH" \
  --db "$DB_PATH" \
  --user-id "$USER_ID" \
  "$@"

SYNC_DIR="$VAULT_PATH/.sync"
mkdir -p "$SYNC_DIR"
date +%Y-%m-%d > "$SYNC_DIR/finance_dashboard_date.txt"
date +%Y-%m-%dT%H:%M:%S > "$SYNC_DIR/finance_dashboard_last_ok.txt"
