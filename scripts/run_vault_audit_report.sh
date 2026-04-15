#!/usr/bin/env bash
# Read-only отчёт по 700_База_Данных → 300_Дашборды/Аудит_хранилища_отчет.md
# Та же команда, что в obsidian_sync.sh (шаг 5b.2), удобно для ручного прогона.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_DIR="$(cd "$BOT_DIR/.." && pwd)"

VAULT="${1:-${VAULT_PATH:-}}"
if [ -z "$VAULT" ]; then
  echo "Usage: VAULT_PATH=/path/to/vault $0"
  echo "   or: $0 /path/to/vault"
  exit 1
fi

export PYTHONPATH="$AGENT_DIR${PYTHONPATH:+:$PYTHONPATH}"
cd "$BOT_DIR"
exec python3 tools/analyze_vault_report.py \
  --vault "$VAULT" \
  --out "$VAULT/300_Дашборды/Аудит_хранилища_отчет.md"
