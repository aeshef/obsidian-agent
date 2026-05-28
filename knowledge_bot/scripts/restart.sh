#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"
common_require_server
SERVER_BOTS="${SERVER_BOTS:-/opt/obsidian-bots}"

echo "🛑 Остановка knowledge_bot..."
ssh "$SERVER" "set -e
  cd ${SERVER_BOTS}/knowledge_bot
  if [ -f logs/watchdog.pid ]; then kill \"\$(cat logs/watchdog.pid)\" 2>/dev/null || true; fi
  pkill -f 'start_bot.py' 2>/dev/null || true
  sleep 2
  pgrep -af 'start_bot|watchdog' || echo 'Процессов нет'"

echo "🚀 Запуск knowledge_bot..."
ssh "$SERVER" "cd ${SERVER_BOTS}/knowledge_bot && chmod +x scripts/watchdog.sh scripts/run.sh 2>/dev/null
  mkdir -p logs && nohup ./scripts/watchdog.sh >> logs/watchdog.log 2>&1 &
  sleep 2
  echo 'Watchdog PID:' \$(cat logs/watchdog.pid 2>/dev/null || echo '?')
  pgrep -f 'start_bot.py' | head -1"
