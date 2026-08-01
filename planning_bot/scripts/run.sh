#!/bin/bash
# Скрипт для запуска бота планирования

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
# shellcheck source=../../scripts/lib/bootstrap_python.sh
source "$MONOREPO/scripts/lib/bootstrap_python.sh"
bootstrap_python planning_bot

if [ -z "$DEEPSEEK_API_TOKEN" ] && [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "❌ Ошибка: DEEPSEEK_API_TOKEN (или DEEPSEEK_API_KEY) не установлен"
    exit 1
fi

if [ -z "$TELEGRAM_PLANNING_BOT_TOKEN" ] && [ -z "$TELEGRAM_UNIFIED_BOT_TOKEN" ] && [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "Error: TELEGRAM_PLANNING_BOT_TOKEN, TELEGRAM_UNIFIED_BOT_TOKEN, or TELEGRAM_BOT_TOKEN required"
    exit 1
fi

echo "Starting planning host (unified bot with planning token preference)..."
echo ""

if [ -z "$VAULT_PATH" ]; then
    if [ -n "${SERVER_VAULT:-}" ] && [ -d "${SERVER_VAULT}" ]; then
        export VAULT_PATH="$SERVER_VAULT"
    fi
fi

mkdir -p logs
exec "$PYTHON_CMD" -m planning_bot.app.main
