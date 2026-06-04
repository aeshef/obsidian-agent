# shellcheck shell=bash
# Capability gates for obsidian_sync.sh — source after AGENT_ROOT is set.
cap_load_env() {
  local root="${AGENT_ROOT:-}"
  local py="${CAPABILITIES_PYTHON:-python3}"
  if [[ -z "$root" ]]; then
    return 0
  fi
  local exporter="$root/scripts/export_capabilities_env.py"
  if [[ ! -f "$exporter" ]]; then
    return 0
  fi
  for candidate in \
    "$root/planning_bot/.venv/bin/python" \
    "$root/finance_bot/.venv/bin/python" \
    "$py"; do
    if [[ -x "$candidate" ]]; then
      py="$candidate"
      break
    fi
  done
  if ! eval "$("$py" "$exporter" 2>/dev/null)"; then
    export CAPABILITIES_SYNC_PROFILE="${CAPABILITIES_SYNC_PROFILE:-full}"
    export CAP_MODULE_FINANCE="${CAP_MODULE_FINANCE:-1}"
    export CAP_MODULE_PLANNING="${CAP_MODULE_PLANNING:-1}"
    export CAP_MODULE_KNOWLEDGE="${CAP_MODULE_KNOWLEDGE:-1}"
    export CAP_SYNC_MAC_IPHONE="${CAP_SYNC_MAC_IPHONE:-1}"
    export CAP_SYNC_GMAIL_HEALTH="${CAP_SYNC_GMAIL_HEALTH:-1}"
    export CAP_SYNC_PLANNING_CHARTS="${CAP_SYNC_PLANNING_CHARTS:-1}"
    export CAP_SYNC_CALENDAR="${CAP_SYNC_CALENDAR:-1}"
    export CAP_SYNC_NUTRITION="${CAP_SYNC_NUTRITION:-1}"
    export CAP_SYNC_KB_MAINTENANCE="${CAP_SYNC_KB_MAINTENANCE:-1}"
    export CAP_SYNC_FINANCE_DASHBOARD="${CAP_SYNC_FINANCE_DASHBOARD:-1}"
    export CAP_SYNC_VAULT_AUDIT_HEAVY="${CAP_SYNC_VAULT_AUDIT_HEAVY:-1}"
  fi
}

cap_step_enabled() {
  local var="CAP_${1}"
  [[ "${!var:-1}" == "1" ]]
}

cap_module_enabled() {
  local var="CAP_MODULE_${1}"
  [[ "${!var:-1}" == "1" ]]
}
