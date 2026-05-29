#!/usr/bin/env bash
# Запуск vault_maintenance при вызове из obsidian_sync (SSH на VPS).
# VAULT_PATH должен совпадать с SERVER_VAULT из корневого .env.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
# shellcheck source=../../scripts/lib/bootstrap_python.sh
source "$MONOREPO/scripts/lib/bootstrap_python.sh"
bootstrap_python planning_bot

export VAULT_PATH="${VAULT_PATH:-${SERVER_VAULT:-}}"
export FROM_SYNC=1
exec "$PYTHON_CMD" -m planning_bot.tools.vault_maintenance
