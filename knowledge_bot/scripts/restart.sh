#!/bin/zsh
# Перезапуск knowledge_bot на сервере

echo "🛑 Остановка knowledge_bot..."
# Останавливаем корректно: TERM -> ждём -> KILL (если не завершился)
ssh example-server 'set -e; \
  wd_pids="$(pgrep -f "knowledge_bot/watchdog.sh" || true)"; \
  bot_pids="$(pgrep -f "start_bot.py" || true)"; \
  if [ -n "$wd_pids" ]; then kill -TERM $wd_pids 2>/dev/null || true; fi; \
  if [ -n "$bot_pids" ]; then kill -TERM $bot_pids 2>/dev/null || true; fi; \
  for i in 1 2 3 4 5; do \
    if pgrep -f "knowledge_bot/watchdog.sh" >/dev/null 2>&1 || pgrep -f "start_bot.py" >/dev/null 2>&1; then sleep 1; else break; fi; \
  done; \
  wd_pids2="$(pgrep -f "knowledge_bot/watchdog.sh" || true)"; \
  bot_pids2="$(pgrep -f "start_bot.py" || true)"; \
  if [ -n "$wd_pids2" ]; then kill -KILL $wd_pids2 2>/dev/null || true; fi; \
  if [ -n "$bot_pids2" ]; then kill -KILL $bot_pids2 2>/dev/null || true; fi; \
  sleep 1; \
  pgrep -af "start_bot|watchdog" || echo "Процессов нет"'
sleep 1

echo "🚀 Запуск knowledge_bot..."
ssh example-server "cd ~/bots/knowledge_bot && chmod +x scripts/watchdog.sh scripts/run.sh 2>/dev/null; mkdir -p logs && nohup ./scripts/watchdog.sh > logs/watchdog.log 2>&1 & sleep 2 && echo 'Watchdog PID:' && pgrep -f 'knowledge_bot/watchdog.sh' | head -1 && echo 'Bot PID:' && pgrep -f 'start_bot.py' | head -1"

echo ""
echo "📋 Последние строки лога:"
sleep 1
ssh example-server "cd ~/bots/knowledge_bot && tail -20 logs/bot.log 2>/dev/null || echo 'Логи пока пусты'"
