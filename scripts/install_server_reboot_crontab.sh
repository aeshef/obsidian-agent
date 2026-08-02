#!/usr/bin/env bash
# @reboot cron: поднять unified_bot после перезагрузки VPS.
#
# Локально (через SSH):
#   ./scripts/install_server_reboot_crontab.sh
# На сервере:
#   SERVER_BOTS=/path/to/bots bash /path/to/bots/scripts/install_server_reboot_crontab.sh
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

if [[ -f "$ROOT/scripts/lib/capabilities.sh" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/scripts/lib/capabilities.sh"
  export AGENT_ROOT="$ROOT"
  # Only skip when export succeeds and the profile is truly all-off.
  # cap_load_env failure used to call cap_disable_all → false skip of @reboot.
  if cap_load_env; then
    if ! cap_module_enabled FINANCE && ! cap_module_enabled PLANNING && ! cap_module_enabled KNOWLEDGE; then
      echo "install_server_reboot_crontab: skip — all CAP_MODULE_* are off"
      exit 0
    fi
  else
    echo "install_server_reboot_crontab: warn — cap_load_env failed; installing @reboot anyway" >&2
  fi
fi

MARKER="# obsidian-agent bots @reboot"
BOTS_ROOT="$(common_server_bots)"

_install_crontab() {
  local tmp
  tmp="$(mktemp)"
  mkdir -p "$BOTS_ROOT/logs"
  (
    crontab -l 2>/dev/null | grep -vF "$MARKER" \
      | grep -v 'start_watchdog_detached.sh' \
      | grep -v 'unified_bot.main' || true
    echo "$MARKER"
    echo "@reboot sleep 30 && cd $BOTS_ROOT && set -a && . ./.env && set +a && DEPLOY_MODE=single PYTHONPATH=$BOTS_ROOT:$BOTS_ROOT/finance_bot:$BOTS_ROOT/knowledge_bot:$BOTS_ROOT/planning_bot AGENT_ROOT=$BOTS_ROOT nohup $BOTS_ROOT/finance_bot/.venv/bin/python -m unified_bot.main >> $BOTS_ROOT/logs/reboot.log 2>&1"
  ) > "$tmp"
  crontab "$tmp"
  rm -f "$tmp"
  echo "✅ @reboot crontab ($BOTS_ROOT):"
  crontab -l | grep -A4 "$MARKER"
}

if [ -n "${SERVER:-}" ] && [ "${INSTALL_REBOOT_LOCAL:-0}" != 1 ]; then
  common_require_server
  echo "📡 Установка @reboot cron на $SERVER ..."
  ssh "$SERVER" "INSTALL_REBOOT_LOCAL=1 SERVER_BOTS='$BOTS_ROOT' bash $BOTS_ROOT/scripts/install_server_reboot_crontab.sh"
else
  _install_crontab
fi
