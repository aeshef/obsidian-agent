# shellcheck shell=bash
# Capability gates for obsidian_sync.sh — source after AGENT_ROOT is set.
_cap_python() {
  local root="${AGENT_ROOT:-}" py="${CAPABILITIES_PYTHON:-python3}"
  [[ -z "$root" ]] && return 1
  for candidate in \
    "$root/planning_bot/.venv/bin/python" \
    "$root/finance_bot/.venv/bin/python" \
    "$py"; do
    if [[ -x "$candidate" ]]; then
      CAPABILITIES_PYTHON="$candidate"
      return 0
    fi
  done
  CAPABILITIES_PYTHON="$py"
  return 0
}

cap_load_env() {
  local root="${AGENT_ROOT:-}"
  if [[ -z "$root" ]] || ! _cap_python; then
    return 0
  fi
  local py="${CAPABILITIES_PYTHON}"
  local cap_exporter="$root/scripts/export_capabilities_env.py"
  local vault_exporter="$root/scripts/export_vault_paths_env.py"
  if [[ -f "$cap_exporter" ]]; then
    if ! eval "$("$py" "$cap_exporter" 2>/dev/null)"; then
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
  fi
  if [[ -f "$vault_exporter" ]]; then
    eval "$("$py" "$vault_exporter" 2>/dev/null)" || true
  fi
}

cap_load_vault_paths() {
  cap_load_env
}

cap_step_enabled() {
  local var="CAP_${1}"
  [[ "${!var:-1}" == "1" ]]
}

cap_module_enabled() {
  local var="CAP_MODULE_${1}"
  [[ "${!var:-1}" == "1" ]]
}
