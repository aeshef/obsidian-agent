#!/bin/zsh
# Просмотр логов finance_bot в реальном времени

echo "📺 Отслеживание логов finance_bot..."
echo "Нажми Ctrl+C для выхода"
echo ""

ssh example-server "cd ~/bots/finance_bot && tail -f logs/bot.log 2>/dev/null || echo 'Логи не найдены. Возможно бот не запущен.'"
