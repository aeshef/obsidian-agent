#!/bin/zsh
# Проверка и перезапуск finance_bot (запускай вручную)

echo "🔍 Проверка статуса finance_bot..."
echo ""

# Проверяем процессы на сервере
echo "📊 Процессы на сервере:"
ssh example-server "ps aux | grep -E '[b]ot.main|[w]atchdog' | head -5" || echo "❌ Не удалось подключиться"

echo ""
echo "📋 Последние 30 строк лога:"
ssh example-server "cd ~/bots/finance_bot && tail -30 logs/bot.log 2>/dev/null || echo 'Логи не найдены'"

echo ""
read -q "REPLY? Перезапустить бота? (y/n): "
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🛑 Остановка..."
    ssh example-server "cd ~/bots/finance_bot && pkill -9 -f 'bot.main' 2>/dev/null; pkill -9 -f 'watchdog.sh' 2>/dev/null; sleep 2; true"
    sleep 2

    echo "🚀 Запуск через watchdog..."
    ssh example-server "cd ~/bots/finance_bot && chmod +x scripts/run.sh scripts/watchdog.sh scripts/check_bot.sh 2>/dev/null; mkdir -p logs && nohup ./scripts/watchdog.sh > logs/watchdog.log 2>&1 & sleep 3 && pgrep -f 'bot.main|watchdog' | head -2"

    echo ""
    echo "📋 Новые логи:"
    sleep 2
    ssh example-server "cd ~/bots/finance_bot && tail -20 logs/bot.log 2>/dev/null || tail -20 logs/watchdog.log"
fi
