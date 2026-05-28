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
ssh "$SERVER" "bash ${SERVER_BOTS}/scripts/start_watchdog_detached.sh ${SERVER_BOTS}/knowledge_bot
  sleep 2
  pgrep -f 'start_bot.py' | head -1 || echo 'бот ещё не поднялся (poll interval ~60s)'"
