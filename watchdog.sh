#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p logs

# Single instance lock to avoid duplicate watchdogs (cron/@reboot/manual).
exec 9>/tmp/knowledge_bot_watchdog.lock
if command -v flock >/dev/null 2>&1; then
  flock -n 9 || exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') | watchdog | started"

backoff=2
max_backoff=60

while true; do
  # If bot already running (e.g. started manually), just wait and re-check.
  if pgrep -f "start_bot.py" >/dev/null 2>&1; then
    sleep 10
    continue
  fi

  echo "$(date '+%Y-%m-%d %H:%M:%S') | watchdog | launching ./run.sh"

  # Run in foreground so we can detect exit and restart.
  set +e
  ./run.sh >> logs/bot.log 2>&1
  code=$?
  set -e

  # Common cases:
  # - 137: SIGKILL (often OOM-kill)
  # - 143: SIGTERM
  echo "$(date '+%Y-%m-%d %H:%M:%S') | watchdog | bot exited code=${code}; sleeping ${backoff}s"
  sleep "${backoff}"
  if [ "${backoff}" -lt "${max_backoff}" ]; then
    backoff=$((backoff * 2))
    if [ "${backoff}" -gt "${max_backoff}" ]; then
      backoff="${max_backoff}"
    fi
  fi
done

