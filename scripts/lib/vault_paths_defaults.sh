# shellcheck shell=bash
# Defaults when export_vault_paths_env.py is unavailable (match config/vault_paths.yaml.example).
vault_paths_apply_defaults() {
  : "${VAULT_FOLDER_TASKS:=100_Tasks}"
  : "${VAULT_FOLDER_GOALS:=200_Goals}"
  : "${VAULT_FOLDER_DASHBOARDS:=300_Dashboards}"
  : "${VAULT_FOLDER_ROUTINES:=400_Routines}"
  : "${VAULT_FOLDER_HANDWRITTEN:=600_Handwritten}"
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

vault_paths_load_from_agent() {
  local root="${1:-}"
  [[ -z "$root" ]] && return 0
  if [[ -f "$root/scripts/lib/capabilities.sh" ]]; then
    # shellcheck disable=SC1091
    source "$root/scripts/lib/capabilities.sh"
    export AGENT_ROOT="$root"
    cap_load_vault_paths 2>/dev/null || true
  fi
  vault_paths_apply_defaults
}
