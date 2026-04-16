#!/bin/zsh
# Синхронизация изменений на сервер

# Задай свой путь: export VAULT_PATH=... или поправь дефолт ниже.
VAULT_PATH="${VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
BOT_DIR="$VAULT_PATH/800_Автоматизация/Agent/knowledge_bot"

echo "🔄 Синхронизация knowledge_bot на сервер..."
echo ""

cd "$BOT_DIR"

# Синхронизируем код (исключаем venv, логи, кэш) и удаляем на сервере файлы,
# которых больше нет локально. Это важно после структурных рефакторингов.
rsync -avz --delete -e 'ssh -o UseKeychain=yes' \
    --exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='logs' --exclude='.env' \
    "$BOT_DIR/" example-server:~/bots/knowledge_bot/

echo ""
echo "✅ Синхронизация завершена"
echo ""
echo "Для перезапуска бота выполни:"
echo "  ./scripts/check_and_restart.sh"
