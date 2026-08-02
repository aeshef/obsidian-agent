#!/bin/bash
# Cron: heal sync-orphaned kanban tasks (last 7 days, skip task_deleted).
# Crontab: 15 * * * * cd ${SERVER_BOTS}/planning_bot && ./scripts/cron_kanban_orphan_heal.sh >> logs/kanban_orphan_heal.log 2>&1
set -euo pipefail
# shellcheck disable=SC1091
source "$(dirname "$0")/_cron_common.sh"
exec "$PY" -m planning_bot.services.kanban_orphan_heal --days 7
