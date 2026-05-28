#!/bin/bash
# Скрипт для запуска finance_bot

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
# shellcheck source=../../scripts/lib/bootstrap_python.sh
source "$MONOREPO/scripts/lib/bootstrap_python.sh"
bootstrap_python finance_bot

if [ -z "$TELEGRAM_FINANCE_BOT_TOKEN" ] && [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ Ошибка: TELEGRAM_FINANCE_BOT_TOKEN или TELEGRAM_BOT_TOKEN не установлен"
    exit 1
fi

if [ -z "$DEEPSEEK_API_KEY" ] && [ -z "$DEEPSEEK_API_TOKEN" ]; then
    echo "❌ Ошибка: DEEPSEEK_API_KEY (или DEEPSEEK_API_TOKEN) не установлен"
    exit 1
fi

echo "🚀 Запуск finance_bot..."
echo ""

mkdir -p logs
exec "$PYTHON_CMD" -m bot.main
