#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

# Single instance lock to avoid duplicate watchdogs (cron/@reboot/manual).
exec 9>/tmp/knowledge_bot_watchdog.lock
if command -v flock >/dev/null 2>&1; then
  flock -n 9 || exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') | watchdog | started"

# Не использовать только pgrep -f start_bot.py: в cmdline попадают bash/grep с тем же подстрочным фрагментом.
kb_running() {
  for pid in $(pgrep -f "start_bot.py" 2>/dev/null || true); do
    [ -r "/proc/${pid}/exe" ] || continue
    readlink -f "/proc/${pid}/exe" 2>/dev/null | grep -qE '(python|python3)$' || continue
    tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null | grep -qF "start_bot.py" || continue
    return 0
  done
  return 1
}

backoff=2
max_backoff=60

while true; do
  # If bot already running (e.g. started manually), just wait and re-check.
  if kb_running; then
    sleep 10
    continue
  fi

  echo "$(date '+%Y-%m-%d %H:%M:%S') | watchdog | launching ./scripts/run.sh"

  # Run in foreground so we can detect exit and restart.
  set +e
  ./scripts/run.sh >> logs/bot.log 2>&1
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

