#!/bin/zsh
# Синхронизация knowledge_bot на сервер и перезапуск бота (с мака).

set -u
VAULT_PATH="${VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
BOT_DIR="$VAULT_PATH/800_Автоматизация/Agent/knowledge_bot"

cd "$BOT_DIR"
chmod +x scripts/sync_to_server.sh scripts/restart.sh scripts/sync_and_restart.sh 2>/dev/null

"$BOT_DIR/scripts/sync_to_server.sh"
echo ""
"$BOT_DIR/scripts/restart.sh"
