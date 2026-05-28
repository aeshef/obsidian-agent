#!/usr/bin/env bash
# Запуск vault_maintenance при вызове из obsidian_sync (SSH на VPS).
# VAULT_PATH должен совпадать с SERVER_VAULT из корневого .env.

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
cd "$ROOT"

for envf in "$ROOT/.env" "$MONOREPO/.env"; do
  if [ -f "$envf" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$envf"
    set +a
    break
  fi
done

export VAULT_PATH="${VAULT_PATH:-${SERVER_VAULT:-/opt/obsidian-vault}}"
export FROM_SYNC=1

if [ -d venv ]; then source venv/bin/activate; fi
export PYTHONPATH="$(dirname "$ROOT")${PYTHONPATH:+:$PYTHONPATH}"
exec python -m planning_bot.tools.vault_maintenance
