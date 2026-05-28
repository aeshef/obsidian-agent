#!/usr/bin/env bash
# Запуск vault_maintenance при вызове из obsidian_sync.
# Обязательно выставляет VAULT_PATH (по умолчанию /root/obsidian-vault), чтобы
# сортировка писала в тот же каталог, откуда rsync забирает файлы.

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Путь к vault на сервере должен совпадать с SERVER_VAULT в obsidian_sync.sh
export VAULT_PATH="${VAULT_PATH:-/root/obsidian-vault}"
export FROM_SYNC=1

if [ -d venv ]; then source venv/bin/activate; fi
export PYTHONPATH="$(dirname "$ROOT")${PYTHONPATH:+:$PYTHONPATH}"
exec python -m planning_bot.tools.vault_maintenance
