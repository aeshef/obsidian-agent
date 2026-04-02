#!/bin/zsh
# Синхронизация изменений finance_bot на сервер (без перезапуска)

[REDACTED]
BOT_DIR="$VAULT_PATH/800_Автоматизация/Agent/finance_bot"

echo "🔄 Синхронизация finance_bot на сервер..."
echo ""

cd "$BOT_DIR"

# Синхронизируем код (исключаем venv, логи, БД, .env)
rsync -avz --delete -e 'ssh -o UseKeychain=yes' \
  --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='logs' --exclude='finance.db' --exclude='.env' \
  --exclude='.git' \
  "$BOT_DIR/" example-server:~/bots/finance_bot/

echo ""
echo "✅ Синхронизация завершена"
echo ""
echo "Для перезапуска бота выполни:"
echo "  ./check_and_restart.sh"
