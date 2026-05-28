#!/bin/bash
# Скрипт для запуска knowledge_bot

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
# shellcheck source=../../scripts/lib/bootstrap_python.sh
source "$MONOREPO/scripts/lib/bootstrap_python.sh"
bootstrap_python knowledge_bot

if [ -z "$TELEGRAM_KNOWLEDGE_BOT_TOKEN" ] && [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ Ошибка: TELEGRAM_KNOWLEDGE_BOT_TOKEN или TELEGRAM_BOT_TOKEN не установлен"
    exit 1
fi

if [ -z "$TELEGRAM_USER_ID" ]; then
    echo "❌ Ошибка: TELEGRAM_USER_ID не установлен"
    exit 1
fi

echo "🚀 Запуск knowledge_bot..."
echo ""

mkdir -p logs
exec "$PYTHON_CMD" start_bot.py
