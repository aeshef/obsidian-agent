#!/bin/bash
# Cron: ночное обновление файла «Сегодня» и истории рутин (01:00).
# Crontab: 0 1 * * * cd /root/bots/planning_bot && ./scripts/cron_routines.sh >> logs/routines.log 2>&1
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/_cron_common.sh"
exec "$PY" -m planning_bot.services.routines_manager
