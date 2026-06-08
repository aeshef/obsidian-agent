#!/bin/bash
# Cron: ночное обновление файла «Сегодня» и истории рутин (01:00).
# Crontab: 0 1 * * * cd ${SERVER_BOTS:-/root/bots}/planning_bot && ./scripts/cron_routines.sh >> logs/routines.log 2>&1
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/_cron_common.sh"
if "$PY" -m planning_bot.services.routines_manager; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] routines cron OK"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] routines cron FAILED rc=$?" >&2
  exit 1
fi
