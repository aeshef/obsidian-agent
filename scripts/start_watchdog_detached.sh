#!/usr/bin/env bash
# Запуск watchdog бота, отвязанный от SSH-сессии (setsid).
# Usage: start_watchdog_detached.sh /path/to/bot_root
set -euo pipefail

BOT_ROOT="${1:?Usage: start_watchdog_detached.sh /path/to/bot_root}"
cd "$BOT_ROOT"
mkdir -p logs

if [ -f logs/watchdog.pid ]; then
  old_pid="$(cat logs/watchdog.pid)"
  kill "$old_pid" 2>/dev/null || true
  sleep 1
fi

setsid bash ./scripts/watchdog.sh >> logs/watchdog.log 2>&1 < /dev/null &
sleep 2

if [ -f logs/watchdog.pid ]; then
  echo "watchdog started pid=$(cat logs/watchdog.pid)"
else
  echo "watchdog failed to write logs/watchdog.pid" >&2
  exit 1
fi
