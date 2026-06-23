#!/bin/bash
# Cron: мониторинг изменений kanban-доски (каждые 2 мин).
# Crontab: */2 * * * * cd ${SERVER_BOTS}/planning_bot && ./scripts/cron_kanban_monitor.sh >> logs/kanban_monitor.log 2>&1
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/_cron_common.sh"
exec "$PY" -m planning_bot.services.kanban_monitor
