#!/usr/bin/env bash
# Запуск vault_maintenance при вызове из obsidian_sync (SSH на VPS).
# VAULT_PATH должен совпадать с SERVER_VAULT из корневого .env.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$ROOT/.." && pwd)"
# shellcheck source=../../scripts/lib/bootstrap_python.sh
source "$MONOREPO/scripts/lib/bootstrap_python.sh"
bootstrap_python planning_bot

export VAULT_PATH="${VAULT_PATH:-${SERVER_VAULT:-}}"
export FROM_SYNC=1

LOG="$ROOT/logs/maintenance.log"
mkdir -p "$ROOT/logs"
# Rotate oversized log so SSH/maintenance isn't fighting a 100MB+ append.
if [[ -f "$LOG" ]]; then
  _sz=$(wc -c <"$LOG" 2>/dev/null || echo 0)
  if [[ "${_sz:-0}" -gt 52428800 ]]; then
    mv -f "$LOG" "${LOG}.$(date +%Y%m%d%H%M%S).bak" 2>/dev/null || true
  fi
fi

LOCK="$ROOT/logs/maintenance_from_sync.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') maintenance_from_sync: lock held — skip"
  exit 0
fi

# Heartbeat on stdout (obsidian_sync SSH) so long runs don't look dead; full log still on disk.
(
  "$PYTHON_CMD" -m planning_bot.tools.vault_maintenance
  echo "MAINTENANCE_EXIT:$?"
) 2>&1 | tee -a "$LOG"
# tee masks python exit — recover from marker
_rc=$(tail -n 1 "$LOG" | sed -n 's/^MAINTENANCE_EXIT://p')
exit "${_rc:-1}"
