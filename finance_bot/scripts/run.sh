#!/bin/bash
# Скрипт для запуска finance_bot

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Загружаем переменные окружения: общий монорепо ../.env, затем локальный .env (оверрайд)
if [ -f "$ROOT/../.env" ]; then
    set -a; source "$ROOT/../.env"; set +a
fi
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Проверяем наличие обязательных переменных (поддержка единого .env: FINANCE-токен или общий)
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

# Активируем venv если есть
if [ -d ".venv" ]; then
    PYTHON_CMD=".venv/bin/python"
else
    PYTHON_CMD="python3"
fi

# PYTHONPATH: finance_bot + родитель (shared/ в /root/bots)
export PYTHONPATH="$(cd "$(dirname "$0")/.." && pwd):$(cd "$(dirname "$0")/../.." && pwd)${PYTHONPATH:+:$PYTHONPATH}"

# Создаем директорию для логов если нужно
mkdir -p logs

# Запускаем бота
exec $PYTHON_CMD -m bot.main
