#!/bin/bash
# Перезапуск бота на сервере. Запускать из корня проекта: ./scripts/restart_bot.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "🛑 Остановка бота..."
pkill -9 -f 'planning_bot.app.bot' || true
pkill -9 -f 'python3 bot.py' || true
pkill -9 -f 'python.*bot.py' || true
sleep 2

echo "🚀 Запуск бота через scripts/run.sh..."
mkdir -p logs

nohup ./scripts/run.sh > logs/bot.log 2>&1 &
NOHUP_PID=$!
sleep 2

BOT_PID=$(pgrep -f 'python.*planning_bot.app.bot' | head -1)
[ -z "$BOT_PID" ] && BOT_PID=$(pgrep -f 'planning_bot.app.bot' | head -1)

if [ -n "$BOT_PID" ]; then
    echo $BOT_PID > logs/bot.pid
    echo "✅ Бот запущен, PID: $BOT_PID (nohup PID: $NOHUP_PID)"
else
    echo $NOHUP_PID > logs/bot.pid
    BOT_PID=$NOHUP_PID
    echo "⚠️ Не удалось найти PID процесса planning_bot.app.bot"
fi

echo ""
echo "📋 Последние строки лога:"
sleep 1
tail -20 logs/bot.log

echo ""
echo "🔍 Проверка процесса:"
ps aux | grep -E "[$BOT_PID]|planning_bot.app.bot" | grep -v grep || echo "⚠️ Процесс не найден"
