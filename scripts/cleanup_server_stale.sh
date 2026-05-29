#!/usr/bin/env bash
# Удаляет устаревшие скрипты с VPS (Mac-only / legacy per-bot deploy wrappers).
#
#   ./scripts/cleanup_server_stale.sh          # через SSH на $SERVER
#   RUN_LOCAL=1 ./scripts/cleanup_server_stale.sh  # на самом сервере
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"

BOTS="$(common_server_bots)"

_stale_paths() {
  cat <<EOF
$BOTS/scripts/ensure_server_python310.sh
$BOTS/scripts/obsidian_sync.sh
$BOTS/scripts/export_mobile_vault.sh
$BOTS/scripts/install_launchagent.sh
$BOTS/scripts/merge_env_from_server.sh
$BOTS/finance_bot/scripts/sync_to_server.sh
$BOTS/finance_bot/scripts/check_and_restart.sh
$BOTS/finance_bot/scripts/deploy.sh
$BOTS/knowledge_bot/scripts/sync_to_server.sh
$BOTS/knowledge_bot/scripts/sync_and_restart.sh
$BOTS/knowledge_bot/scripts/check_and_restart.sh
$BOTS/knowledge_bot/scripts/restart.sh
$BOTS/planning_bot/scripts/sync_and_restart.sh
$BOTS/planning_bot/scripts/restart_bot.sh
EOF
}

_cleanup() {
  local removed=0
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    if [ -e "$path" ]; then
      rm -f "$path"
      echo "  removed $path"
      removed=$((removed + 1))
    fi
  done < <(_stale_paths)
  if [ "$removed" -eq 0 ]; then
    echo "  (nothing to remove)"
  else
    echo "✅ removed $removed stale file(s)"
  fi
}

if [ "${RUN_LOCAL:-0}" = 1 ]; then
  BOTS="${SERVER_BOTS:-$BOTS}"
  echo "🧹 cleanup stale scripts on server ($BOTS)..."
  _cleanup
elif [ -n "${SERVER:-}" ]; then
  common_require_server
  echo "🧹 cleanup stale scripts on $SERVER ..."
  ssh "$SERVER" "RUN_LOCAL=1 SERVER_BOTS='$BOTS' bash -s" <<'EOF'
set -euo pipefail
BOTS="${SERVER_BOTS:?SERVER_BOTS required}"
_stale_paths() {
  cat <<EOP
$BOTS/scripts/ensure_server_python310.sh
$BOTS/scripts/obsidian_sync.sh
$BOTS/scripts/export_mobile_vault.sh
$BOTS/scripts/install_launchagent.sh
$BOTS/scripts/merge_env_from_server.sh
$BOTS/finance_bot/scripts/sync_to_server.sh
$BOTS/finance_bot/scripts/check_and_restart.sh
$BOTS/finance_bot/scripts/deploy.sh
$BOTS/knowledge_bot/scripts/sync_to_server.sh
$BOTS/knowledge_bot/scripts/sync_and_restart.sh
$BOTS/knowledge_bot/scripts/check_and_restart.sh
$BOTS/knowledge_bot/scripts/restart.sh
$BOTS/planning_bot/scripts/sync_and_restart.sh
$BOTS/planning_bot/scripts/restart_bot.sh
EOP
}
removed=0
while IFS= read -r path; do
  [ -n "$path" ] || continue
  if [ -e "$path" ]; then
    rm -f "$path"
    echo "  removed $path"
    removed=$((removed + 1))
  fi
done < <(_stale_paths)
[ "$removed" -eq 0 ] && echo "  (nothing to remove)" || echo "✅ removed $removed stale file(s)"
EOF
else
  echo "❌ Set SERVER in .env or RUN_LOCAL=1 on VPS" >&2
  exit 1
fi
