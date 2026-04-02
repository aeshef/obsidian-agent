#!/bin/zsh
# Просмотр логов knowledge_bot в реальном времени

echo "📺 Отслеживание логов knowledge_bot..."
echo "Нажми Ctrl+C для выхода"
echo ""

ssh example-server "cd ~/bots/knowledge_bot && tail -f logs/bot.log 2>/dev/null || echo 'Логи не найдены. Возможно бот не запущен.'"
