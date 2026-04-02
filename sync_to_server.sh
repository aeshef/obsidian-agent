#!/bin/zsh
# Синхронизация изменений на сервер

[REDACTED]
BOT_DIR="$VAULT_PATH/800_Автоматизация/Agent/knowledge_bot"

echo "🔄 Синхронизация knowledge_bot на сервер..."
echo ""

cd "$BOT_DIR"

# Синхронизируем код (исключаем venv, логи, кэш)
rsync -avz -e 'ssh -o UseKeychain=yes' --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='logs' --exclude='.env' \
    "$BOT_DIR/" example-server:~/bots/knowledge_bot/

echo ""
echo "✅ Синхронизация завершена"
echo ""
echo "Для перезапуска бота выполни:"
echo "  ./check_and_restart.sh"
