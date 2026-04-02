#!/bin/zsh
# Запуск knowledge_bot на сервере

echo "🚀 Запуск knowledge_bot на сервере..."
echo ""

ssh example-server << 'EOF'
cd ~/bots/knowledge_bot

# Проверяем что процесс не запущен
if pgrep -f 'knowledge_bot|start_bot' > /dev/null; then
    echo "⚠️  Бот уже запущен, останавливаю старый процесс..."
    pkill -9 -f 'knowledge_bot/watchdog.sh' || true
    pkill -9 -f 'knowledge_bot|start_bot' || true
    sleep 2
fi

# Создаем директории если нужно
mkdir -p logs

# Запускаем watchdog (он поднимет бота и будет перезапускать при падении)
echo "🚀 Запускаю watchdog..."
chmod +x watchdog.sh run.sh 2>/dev/null
nohup ./watchdog.sh > logs/watchdog.log 2>&1 &
WD_PID=$!

sleep 3

# Проверяем что процесс запустился
if pgrep -f 'knowledge_bot/watchdog.sh' > /dev/null; then
    ACTUAL_WD_PID=$(pgrep -f 'knowledge_bot/watchdog.sh' | head -1)
    ACTUAL_BOT_PID=$(pgrep -f 'start_bot.py' | head -1 || true)
    echo $ACTUAL_WD_PID > logs/watchdog.pid
    if [ -n "$ACTUAL_BOT_PID" ]; then
        echo $ACTUAL_BOT_PID > logs/bot.pid
    fi
    echo "✅ Watchdog запущен, PID: $ACTUAL_WD_PID"
    if [ -n "$ACTUAL_BOT_PID" ]; then
        echo "✅ Бот запущен, PID: $ACTUAL_BOT_PID"
    else
        echo "⚠️  Бот ещё не поднялся (watchdog запущен) — см. logs/watchdog.log"
    fi
    echo ""
    echo "📋 Последние 20 строк лога:"
    tail -20 logs/bot.log
else
    echo "❌ Watchdog не запустился! Проверь логи:"
    tail -30 logs/watchdog.log || true
fi
EOF

echo ""
echo "✅ Готово!"
