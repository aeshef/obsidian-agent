#!/bin/bash
# Устанавливает cron-задачи planning_bot на сервере (идемпотентно).
# Запуск: ./scripts/install_planning_crontab.sh
#   или:  ssh "$SERVER" 'bash -s' < scripts/install_planning_crontab.sh
set -euo pipefail

BOT_ROOT="${PLANNING_BOT_ROOT:-${SERVER_BOTS:-/opt/obsidian-bots}/planning_bot}"

MARKER="# obsidian-agent planning_bot cron"
TMP="$(mktemp)"
(
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -v 'kanban_monitor_standalone.py' \
        | grep -v 'planning_bot/routines_manager.py' | grep -v 'run_map_missing_goals.sh' \
        | grep -v 'cron_kanban_monitor.sh' | grep -v 'cron_routines.sh' || true
    echo "$MARKER"
    echo "*/2 * * * * cd $BOT_ROOT && ./scripts/cron_kanban_monitor.sh >> logs/kanban_monitor.log 2>&1"
    echo "0 1 * * * cd $BOT_ROOT && ./scripts/cron_routines.sh >> logs/routines.log 2>&1"
    echo "0 * * * * cd $BOT_ROOT && ./scripts/run_map_missing_goals.sh >> logs/map_goals.log 2>&1"
) > "$TMP"
crontab "$TMP"
rm -f "$TMP"
echo "✅ crontab обновлён ($BOT_ROOT):"
crontab -l | grep -A3 "$MARKER"
