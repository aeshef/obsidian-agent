#!/bin/bash
# Скрипт для запуска knowledge_bot

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Загружаем переменные окружения из .env если есть
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Проверяем наличие обязательных переменных
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ Ошибка: TELEGRAM_BOT_TOKEN не установлен"
    echo "Создай файл .env или установи переменную окружения"
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

# Устанавливаем PYTHONPATH для относительных импортов
export PYTHONPATH="$ROOT"

# На серверах с ограниченной памятью ASR по умолчанию использует tiny (см. extract.py)
# Для лучшего качества голоса: ASR_MODEL=small (требует больше RAM)
python3 start_bot.py
