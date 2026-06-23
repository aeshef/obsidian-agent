# shellcheck shell=bash
# Capability gates for obsidian_sync.sh — source after AGENT_ROOT is set.
_cap_python() {
  local root="${AGENT_ROOT:-}" py="${CAPABILITIES_PYTHON:-python3}" candidate
  [[ -z "$root" ]] && return 1
  if [[ ! -t 0 ]]; then
    for candidate in python3.12 python3; do
      if command -v "$candidate" >/dev/null 2>&1; then
        CAPABILITIES_PYTHON="$(command -v "$candidate")"
        return 0
      fi
    done
  fi
  for candidate in \
    "$root/finance_bot/.venv/bin/python" \
    "$root/planning_bot/.venv/bin/python" \
    "$py"; do
    if [[ -x "$candidate" ]]; then
      CAPABILITIES_PYTHON="$candidate"
      return 0
    fi
  done
  CAPABILITIES_PYTHON="$py"
  return 0
}

_cap_run_py() {
  local py="$1" script="$2"
  if [[ ! -t 0 && -f "$script" ]]; then
    cat "$script" | "$py" -u - 2>/dev/null
  else
    "$py" "$script" 2>/dev/null
  fi
}

cap_disable_all() {
  export CAPABILITIES_SYNC_PROFILE="${CAPABILITIES_SYNC_PROFILE:-disabled}"
  export CAP_MODULE_FINANCE=0
  export CAP_MODULE_PLANNING=0
  export CAP_MODULE_KNOWLEDGE=0
  export CAP_SYNC_MAC_IPHONE=0
  export CAP_SYNC_GMAIL_HEALTH=0
  export CAP_SYNC_PLANNING_CHARTS=0
  export CAP_SYNC_CALENDAR=0
  export CAP_SYNC_NUTRITION=0
  export CAP_SYNC_HEALTH_ANALYTICS=0
  export CAP_SYNC_CROSS_ANALYTICS=0
  export CAP_SYNC_KB_MAINTENANCE=0
  export CAP_SYNC_FINANCE_DASHBOARD=0
  export CAP_SYNC_VAULT_AUDIT_HEAVY=0
  export CAP_FEATURE_HEALTH_BODY_METRICS=0
  export CAP_FEATURE_HEALTH_NUTRITION_CHART=0
}

cap_load_env() {
  local root="${AGENT_ROOT:-}"
  if [[ -z "$root" ]] || ! _cap_python; then
    cap_disable_all
    return 1
  fi
  local py="${CAPABILITIES_PYTHON}"
  local cap_exporter="$root/scripts/export_capabilities_env.py"
  local vault_exporter="$root/scripts/export_vault_paths_env.py"
  if [[ -f "$cap_exporter" ]]; then
    if ! eval "$(_cap_run_py "$py" "$cap_exporter")"; then
      cap_disable_all
      return 1
    fi
  else
    cap_disable_all
    return 1
  fi
  if [[ -f "$vault_exporter" ]]; then
    eval "$(_cap_run_py "$py" "$vault_exporter")" || true
  fi
}

cap_load_vault_paths() {
  cap_load_env
}

_cap_var_is_one() {
  # Bash ${!name} breaks under zsh (obsidian_sync.sh); eval works in both.
  local val
  eval "val=\${${1}:-0}"
  [[ "$val" == "1" ]]
}

cap_step_enabled() {
  _cap_var_is_one "CAP_${1}"
}

cap_module_enabled() {
  _cap_var_is_one "CAP_MODULE_${1}"
}
