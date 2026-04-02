#!/bin/bash
# Скрипт для запуска finance_bot

cd "$(dirname "$0")"

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

if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "❌ Ошибка: DEEPSEEK_API_KEY не установлен"
    echo "Создай файл .env или установи переменную окружения"
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

# Создаем директорию для логов если нужно
mkdir -p logs

# Запускаем бота
exec $PYTHON_CMD -m bot.main
