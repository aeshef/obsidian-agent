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
cd "$ROOT"

if [[ -z "${VAULT_PATH:-}" ]]; then
  if [[ -d "$HOME/Documents/Obsidian Vault" ]]; then
    VAULT_PATH="$HOME/Documents/Obsidian Vault"
  else
    VAULT_PATH="$HOME/Obsidian Vault"
  fi
fi

DB_PATH="${FINANCE_DB_PATH:-$VAULT_PATH/300_Дашборды/Данные/finance.db}"
USER_ID="${FINANCE_DASHBOARD_USER_ID:-1}"

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  if [[ -x "$ROOT/venv/bin/python" ]]; then
    PY="$ROOT/venv/bin/python"
  else
    echo "ERROR: нет виртуального окружения в $ROOT/.venv (или $ROOT/venv)." >&2
    echo "Создай: cd \"$ROOT\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
  fi
fi

if ! "$PY" -c "import matplotlib" 2>/dev/null; then
  echo "ERROR: в venv нет matplotlib (графики PNG не соберутся)." >&2
  echo "Установи в этот же интерпретатор:" >&2
  echo "  \"$ROOT/.venv/bin/pip\" install -r \"$ROOT/requirements.txt\"" >&2
  echo "или только: \"$ROOT/.venv/bin/pip\" install matplotlib" >&2
  exit 1
fi

exec "$PY" scripts/build_finance_dashboard.py \
  --vault "$VAULT_PATH" \
  --db "$DB_PATH" \
  --user-id "$USER_ID" \
  "$@"
