#!/bin/bash
# Скрипт для запуска finance_bot

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
# shellcheck source=../../scripts/lib/bootstrap_python.sh
source "$MONOREPO/scripts/lib/bootstrap_python.sh"
bootstrap_python finance_bot

if [ -z "$TELEGRAM_FINANCE_BOT_TOKEN" ] && [ -z "$TELEGRAM_UNIFIED_BOT_TOKEN" ] && [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "Error: TELEGRAM_FINANCE_BOT_TOKEN, TELEGRAM_UNIFIED_BOT_TOKEN, or TELEGRAM_BOT_TOKEN required"
    exit 1
fi

if [ -z "$DEEPSEEK_API_KEY" ] && [ -z "$DEEPSEEK_API_TOKEN" ]; then
    echo "Error: DEEPSEEK_API_KEY (or DEEPSEEK_API_TOKEN) required"
    exit 1
fi

echo "Starting finance host (unified bot with finance token preference)..."
echo ""

mkdir -p logs
exec "$PYTHON_CMD" -m bot.main
