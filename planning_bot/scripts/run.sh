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

if [ -z "$TELEGRAM_PLANNING_BOT_TOKEN" ] && [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ Ошибка: TELEGRAM_PLANNING_BOT_TOKEN или TELEGRAM_BOT_TOKEN не установлен"
    exit 1
fi

echo "🚀 Запуск planning_bot..."
echo ""

if [ -z "$VAULT_PATH" ]; then
    if [ -n "${SERVER_VAULT:-}" ] && [ -d "${SERVER_VAULT}" ]; then
        export VAULT_PATH="$SERVER_VAULT"
    fi
fi

mkdir -p logs
exec "$PYTHON_CMD" -m planning_bot.app.main
