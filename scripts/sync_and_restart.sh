#!/bin/bash
# Скрипт для синхронизации и перезапуска бота на сервере

[REDACTED]
BOT_DIR="$VAULT_PATH/800_Автоматизация/Agent/planning_bot"

cd "$VAULT_PATH"

echo "🔄 Синхронизация файлов..."
rsync -avz --delete --exclude='.git' --exclude='node_modules' --exclude='.DS_Store' \
  --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' \
  --exclude='📊 Рутины_2026-*.md' --exclude='📋 Шаблон_Рутин.md' \
  --exclude='📊 Прогресс_2026.md' \
  "$BOT_DIR/" example-server:~/bots/planning_bot/

echo ""
echo "🔄 Перезапуск бота на сервере..."
ssh example-server "cd ~/bots/planning_bot && chmod +x scripts/run.sh scripts/restart_bot.sh scripts/watchdog.sh 2>/dev/null; ./scripts/restart_bot.sh 2>/dev/null || (pkill -9 -f 'planning_bot.app.bot' || true; sleep 2; mkdir -p logs; nohup ./scripts/run.sh > logs/bot.log 2>&1 & echo \$! > logs/bot.pid; echo '✅ Бот запущен, PID:' \$(cat logs/bot.pid); sleep 2; tail -20 logs/bot.log)"
