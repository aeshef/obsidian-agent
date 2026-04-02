#!/bin/bash
# Скрипт для запуска бота планирования

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Загружаем переменные окружения из .env если есть
if [ -f .env ]; then
    # Безопасная загрузка переменных из .env
    set -a
    source .env
    set +a
fi

# Проверяем наличие обязательных переменных
if [ -z "$DEEPSEEK_API_TOKEN" ]; then
    echo "❌ Ошибка: DEEPSEEK_API_TOKEN не установлен"
    echo "Создай файл .env или установи переменную окружения"
    echo ""
    echo "Пример .env:"
    echo "DEEPSEEK_API_TOKEN=sk-твой-токен"
    echo "TELEGRAM_PLANNING_BOT_TOKEN=твой-токен-бота"
    exit 1
fi

# Проверяем токен бота (может быть TELEGRAM_PLANNING_BOT_TOKEN или TELEGRAM_BOT_TOKEN)
if [ -z "$TELEGRAM_PLANNING_BOT_TOKEN" ] && [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ Ошибка: TELEGRAM_PLANNING_BOT_TOKEN или TELEGRAM_BOT_TOKEN не установлен"
    echo "Создай файл .env или установи переменную окружения"
    exit 1
fi

echo "🚀 Запуск planning_bot..."
echo ""

# Активируем venv если есть
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Устанавливаем PYTHONPATH для импортов
export PYTHONPATH="$(dirname "$ROOT")${PYTHONPATH:+:$PYTHONPATH}"

# На сервере бот часто в ~/bots/planning_bot, а vault — отдельно. Без VAULT_PATH
# config.py поднимается от planning_bot вверх и получает неверный путь (например /),
# из-за чего «Выполнено за неделю» и логи читаются не из 300_Дашборды и дают 0.
if [ -z "$VAULT_PATH" ]; then
    if [ -d "/root/obsidian-vault" ]; then
        export VAULT_PATH="/root/obsidian-vault"
    fi
fi

# Создаем директорию для логов если нужно
mkdir -p logs

# Запускаем бота
# Используем exec для замены процесса, чтобы сигналы правильно обрабатывались
exec python3 -m planning_bot.app.bot
