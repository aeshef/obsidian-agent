#!/bin/bash
# Скрипт для синхронизации и перезапуска бота на сервере (с мака).
# Задай корень vault: export LOCAL_VAULT=/path/to/Obsidian\ Vault
# или VAULT_PATH — иначе по умолчанию ~/Documents/Obsidian Vault (подставь свой путь).
#
# Синкает: planning_bot → ~/bots/planning_bot; knowledge_bot → ~/bots/knowledge_bot
# и зеркало в дереве vault на VPS (для 5b.2b / obsidian_sync): REMOTE_VAULT/800_Автоматизация/Agent/{knowledge_bot,obsidian_sync.sh}
# REMOTE_VAULT по умолчанию /root/obsidian-vault — переопредели при другом пути на сервере.

set -u
: "${LOCAL_VAULT:=${VAULT_PATH:-$HOME/Documents/Obsidian Vault}}"
VAULT_PATH="$LOCAL_VAULT"
AGENT_DIR="$VAULT_PATH/800_Автоматизация/Agent"
BOT_DIR="$AGENT_DIR/planning_bot"
KN_DIR="$AGENT_DIR/knowledge_bot"
: "${REMOTE_VAULT:=/root/obsidian-vault}"

RSYNC_KN_EX=(
  --exclude='.git/' --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc'
  --exclude='logs/' --exclude='.env' --exclude='data/'
)

cd "$VAULT_PATH" || exit 1

echo "🔄 Синхронизация planning_bot → ~/bots/planning_bot ..."
rsync -avz --delete --exclude='.git' --exclude='node_modules' --exclude='.DS_Store' \
  --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' \
  --exclude='logs/' --exclude='CHAT_ID.txt' \
  --exclude='.env' --exclude='.env.local' \
  --exclude='goals_context.md' \
  --exclude='📊 Рутины_2026-*.md' --exclude='📋 Шаблон_Рутин.md' \
  --exclude='📊 Прогресс_2026.md' \
  -e 'ssh -o UseKeychain=yes' \
  "$BOT_DIR/" example-server:~/bots/planning_bot/

echo ""
echo "🔄 Синхронизация knowledge_bot → ~/bots/knowledge_bot ..."
rsync -avz --delete -e 'ssh -o UseKeychain=yes' "${RSYNC_KN_EX[@]}" \
  "$KN_DIR/" example-server:~/bots/knowledge_bot/

echo ""
echo "🔄 Синхронизация knowledge_bot + obsidian_sync.sh → серверный vault ($REMOTE_VAULT) ..."
rsync -avz --delete -e 'ssh -o UseKeychain=yes' "${RSYNC_KN_EX[@]}" \
  "$KN_DIR/" "example-server:${REMOTE_VAULT}/800_Автоматизация/Agent/knowledge_bot/"
scp -o UseKeychain=yes "$AGENT_DIR/obsidian_sync.sh" \
  "example-server:${REMOTE_VAULT}/800_Автоматизация/Agent/obsidian_sync.sh"

echo ""
echo "🔄 Перезапуск бота на сервере..."
ssh example-server "cd ~/bots/planning_bot && chmod +x scripts/run.sh scripts/restart_bot.sh scripts/watchdog.sh 2>/dev/null; ./scripts/restart_bot.sh 2>/dev/null || (pkill -9 -f 'planning_bot.app.bot' || true; sleep 2; mkdir -p logs; nohup ./scripts/run.sh > logs/bot.log 2>&1 & echo \$! > logs/bot.pid; echo '✅ Бот запущен, PID:' \$(cat logs/bot.pid); sleep 2; tail -20 logs/bot.log)"
