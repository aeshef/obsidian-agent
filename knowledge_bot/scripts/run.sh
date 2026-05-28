#!/bin/bash
# Скрипт для запуска knowledge_bot

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Загружаем переменные окружения: общий монорепо ../.env (если есть), затем локальный .env (оверрайд)
if [ -f "$ROOT/../.env" ]; then
    set -a; source "$ROOT/../.env"; set +a
fi
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Проверяем наличие обязательных переменных (поддержка единого .env: KNOWLEDGE-токен или общий)
if [ -z "$TELEGRAM_KNOWLEDGE_BOT_TOKEN" ] && [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ Ошибка: TELEGRAM_KNOWLEDGE_BOT_TOKEN или TELEGRAM_BOT_TOKEN не установлен"
    exit 1
fi

if [ -z "$TELEGRAM_USER_ID" ]; then
    echo "❌ Ошибка: TELEGRAM_USER_ID не установлен"
    echo "Создай файл .env или установи переменную окружения"
    exit 1
fi

echo "🚀 Запуск knowledge_bot..."
echo ""

# Активируем venv если есть
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# PYTHONPATH: сам бот + родитель (там лежит shared/ — общий пакет монорепо)
export PYTHONPATH="$ROOT:$(dirname "$ROOT")${PYTHONPATH:+:$PYTHONPATH}"

# На серверах с ограниченной памятью ASR по умолчанию использует tiny (см. services/extract/asr.py)
# Для лучшего качества голоса: ASR_MODEL=small (требует больше RAM)
python3 start_bot.py
