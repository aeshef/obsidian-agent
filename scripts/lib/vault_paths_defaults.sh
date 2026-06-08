# shellcheck shell=bash
# Fallback when export_vault_paths_env.py is unavailable (EN layout; RU via vault_paths.ru.yaml).
vault_paths_apply_defaults() {
  : "${VAULT_FOLDER_TASKS:=100_Tasks}"
  : "${VAULT_FOLDER_GOALS:=200_Goals}"
  : "${VAULT_FOLDER_DASHBOARDS:=300_Dashboards}"
  : "${VAULT_FOLDER_ROUTINES:=400_Routines}"
  : "${VAULT_FOLDER_HANDWRITTEN:=600_Handwritten}"
  : "${VAULT_FOLDER_AUTOMATION:=800_Automation}"
  : "${VAULT_DASH_LOGS:=Logs}"
  : "${VAULT_DASH_CHARTS:=Charts}"
  : "${VAULT_DASH_DATA:=Data}"
  : "${VAULT_PATH_ACTIONS_MAC:=Actions/Mac}"
  : "${VAULT_PATH_ACTIONS_IPHONE:=Actions/IPhone}"
  : "${VAULT_PATH_CONTEXT_TODAY:=Actions/context_today.json}"
  : "${VAULT_PATH_CONTEXT_WEEK:=Actions/context_week.json}"
  : "${VAULT_PATH_IPHONE_TODAY:=Actions/iphone_today.json}"
  : "${VAULT_PATH_IPHONE_WEEK:=Actions/iphone_week.json}"
  : "${VAULT_FILE_CHART_DAILY_ACTIVITY:=Daily_activity.png}"
  : "${VAULT_FILE_AUDIT_SYSTEM:=System_audit_report.md}"
  : "${VAULT_FILE_AUDIT_VAULT:=Vault_audit_report.md}"
}

_vault_segment_sane() {
  local val="$1"
  [[ -n "$val" && "$val" != /* && "$val" != *".."* && "$val" != *"/"* ]]
}

_vault_sanitize_exported_segments() {
  local -a keys=(
    VAULT_FOLDER_TASKS VAULT_FOLDER_GOALS VAULT_FOLDER_DASHBOARDS
    VAULT_FOLDER_ROUTINES VAULT_FOLDER_HANDWRITTEN VAULT_FOLDER_AUTOMATION
    VAULT_DASH_LOGS VAULT_DASH_CHARTS VAULT_DASH_DATA
  )
  local k v
  for k in "${keys[@]}"; do
    if [[ -n "${ZSH_VERSION:-}" ]]; then
      v="${(P)k-}"
    else
      v="${!k:-}"
    fi
    if [[ -n "$v" ]] && ! _vault_segment_sane "$v"; then
      echo "vault_paths: drop invalid $k=$v" >&2
      unset "$k"
    fi
  done
}

_vault_yaml_field() {
  local section="$1" key="$2" file="$3"
  awk -v sec="$section" -v k="$key" '
    BEGIN { in_sec=0 }
    $0 ~ "^" sec ":" { in_sec=1; next }
    in_sec && /^[^ #\t]/ && $0 !~ /^  / { in_sec=0 }
    in_sec && $0 ~ "^  " k ":" {
      sub(/^[^:]+:[ \t]*/, "", $0)
      gsub(/^["'\'']|["'\'']$/, "", $0)
      print $0
      exit
    }
  ' "$file"
}

_vault_paths_try_python_export() {
  local root="$1" py exporter="$root/scripts/export_vault_paths_env.py"
  [[ -f "$exporter" ]] || return 1
  for py in \
    "$root/finance_bot/.venv/bin/python" \
    "$root/planning_bot/.venv/bin/python" \
    /opt/homebrew/bin/python3 \
    python3; do
    [[ -x "$py" ]] || continue
    if eval "$("$py" "$exporter" 2>/dev/null)" && [[ -n "${VAULT_FOLDER_TASKS:-}" ]]; then
      return 0
    fi
  done
  return 1
}

_vault_paths_yaml_shell_fallback() {
  local root="$1" yaml="$root/config/vault_paths.yaml"
  [[ -f "$yaml" ]] || return 1
  local v
  v="$(_vault_yaml_field folders tasks "$yaml")" && [[ -n "$v" ]] && export VAULT_FOLDER_TASKS="$v"
  v="$(_vault_yaml_field folders goals "$yaml")" && [[ -n "$v" ]] && export VAULT_FOLDER_GOALS="$v"
  v="$(_vault_yaml_field folders dashboards "$yaml")" && [[ -n "$v" ]] && export VAULT_FOLDER_DASHBOARDS="$v"
  v="$(_vault_yaml_field folders routines "$yaml")" && [[ -n "$v" ]] && export VAULT_FOLDER_ROUTINES="$v"
  v="$(_vault_yaml_field folders handwritten "$yaml")" && [[ -n "$v" ]] && export VAULT_FOLDER_HANDWRITTEN="$v"
  v="$(_vault_yaml_field folders automation "$yaml")" && [[ -n "$v" ]] && export VAULT_FOLDER_AUTOMATION="$v"
  v="$(_vault_yaml_field dashboards logs "$yaml")" && [[ -n "$v" ]] && export VAULT_DASH_LOGS="$v"
  v="$(_vault_yaml_field dashboards charts "$yaml")" && [[ -n "$v" ]] && export VAULT_DASH_CHARTS="$v"
  v="$(_vault_yaml_field dashboards data "$yaml")" && [[ -n "$v" ]] && export VAULT_DASH_DATA="$v"
  v="$(_vault_yaml_field paths actions_mac "$yaml")" && [[ -n "$v" ]] && export VAULT_PATH_ACTIONS_MAC="$v"
  v="$(_vault_yaml_field paths actions_iphone "$yaml")" && [[ -n "$v" ]] && export VAULT_PATH_ACTIONS_IPHONE="$v"
  v="$(_vault_yaml_field paths context_today_json "$yaml")" && [[ -n "$v" ]] && export VAULT_PATH_CONTEXT_TODAY="$v"
  v="$(_vault_yaml_field paths context_week_json "$yaml")" && [[ -n "$v" ]] && export VAULT_PATH_CONTEXT_WEEK="$v"
  v="$(_vault_yaml_field paths iphone_today_json "$yaml")" && [[ -n "$v" ]] && export VAULT_PATH_IPHONE_TODAY="$v"
  v="$(_vault_yaml_field paths iphone_week_json "$yaml")" && [[ -n "$v" ]] && export VAULT_PATH_IPHONE_WEEK="$v"
  v="$(_vault_yaml_field files calendar_json "$yaml")" && [[ -n "$v" ]] && export VAULT_FILE_CALENDAR_JSON="$v"
  v="$(_vault_yaml_field files chart_daily_activity_png "$yaml")" && [[ -n "$v" ]] && export VAULT_FILE_CHART_DAILY_ACTIVITY="$v"
  v="$(_vault_yaml_field files chart_calendar_week_png "$yaml")" && [[ -n "$v" ]] && export VAULT_FILE_CHART_CALENDAR_WEEK_PNG="$v"
  v="$(_vault_yaml_field files chart_nutrition_png "$yaml")" && [[ -n "$v" ]] && export VAULT_FILE_CHART_NUTRITION_PNG="$v"
  v="$(_vault_yaml_field files system_audit_report_md "$yaml")" && [[ -n "$v" ]] && export VAULT_FILE_AUDIT_SYSTEM="$v"
  v="$(_vault_yaml_field files vault_audit_report_md "$yaml")" && [[ -n "$v" ]] && export VAULT_FILE_AUDIT_VAULT="$v"
  v="$(_vault_yaml_field finance chart_daily_categories_png "$yaml")" && [[ -n "$v" ]] && export VAULT_FIN_CHART_DAILY_CATEGORIES_PNG="$v"
  [[ -n "${VAULT_FOLDER_TASKS:-}" ]]
}

vault_paths_load_from_agent() {
  local root="${1:-}"
  [[ -z "$root" ]] && return 0
  local yaml="$root/config/vault_paths.yaml"
  if [[ -f "$root/scripts/lib/capabilities.sh" ]]; then
    # shellcheck disable=SC1091
    source "$root/scripts/lib/capabilities.sh"
    export AGENT_ROOT="$root"
    cap_load_vault_paths 2>/dev/null || true
  fi
  if [[ -f "$yaml" && -z "${VAULT_FOLDER_TASKS:-}" ]]; then
    _vault_paths_try_python_export "$root" || _vault_paths_yaml_shell_fallback "$root" || {
      echo "vault_paths: export failed for $yaml (LaunchAgent: grant Full Disk Access to zsh or run sync from Terminal)" >&2
      return 1
    }
    echo "vault_paths: used shell YAML fallback (python export unavailable)" >&2
  fi
  vault_paths_apply_defaults
  _vault_sanitize_exported_segments
}
