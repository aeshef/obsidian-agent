#!/bin/bash
# Маппинг задач к целям (для cron).
# Crontab: 0 * * * * cd ${SERVER_BOTS}/planning_bot && ./scripts/run_map_missing_goals.sh >> logs/map_goals.log 2>&1
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/_cron_common.sh"
exec "$PY" -m planning_bot.tools.map_missing_goals "$@"
