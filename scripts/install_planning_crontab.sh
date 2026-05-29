#!/usr/bin/env bash
# Устанавливает cron-задачи planning_bot на сервере (идемпотентно).
#
#   ./scripts/install_planning_crontab.sh
#   ssh "$SERVER" "bash ${SERVER_BOTS}/scripts/install_planning_crontab.sh"
set -euo pipefail

if [ -n "${SERVER_BOTS:-}" ] && [ -f "${SERVER_BOTS}/scripts/lib/common.sh" ]; then
  ROOT="${SERVER_BOTS}"
  # shellcheck source=/dev/null
  source "${SERVER_BOTS}/scripts/lib/common.sh"
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  # shellcheck source=scripts/lib/common.sh
  source "$ROOT/scripts/lib/common.sh"
  common_load_env "$ROOT"
fi

BOT_ROOT="${PLANNING_BOT_ROOT:-$(common_server_bots)/planning_bot}"

if [ -n "${SERVER:-}" ] && [ "${INSTALL_CRON_LOCAL:-0}" != 1 ]; then
  common_require_server
  BOTS="$(common_server_bots)"
  echo "📡 install planning crontab on $SERVER ..."
  ssh "$SERVER" "INSTALL_CRON_LOCAL=1 PLANNING_BOT_ROOT='$BOTS/planning_bot' bash $BOTS/scripts/install_planning_crontab.sh"
  exit 0
fi

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
