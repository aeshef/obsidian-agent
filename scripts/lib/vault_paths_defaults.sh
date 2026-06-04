# shellcheck shell=bash
# Defaults when export_vault_paths_env.py is unavailable (match config/vault_paths.yaml.example).
vault_paths_apply_defaults() {
  : "${VAULT_FOLDER_TASKS:=100_Задачи}"
  : "${VAULT_FOLDER_GOALS:=200_Цели}"
  : "${VAULT_FOLDER_DASHBOARDS:=300_Дашборды}"
  : "${VAULT_FOLDER_ROUTINES:=400_Рутины}"
  : "${VAULT_FOLDER_HANDWRITTEN:=600_Рукописное}"
  : "${VAULT_DASH_LOGS:=Логи}"
  : "${VAULT_DASH_CHARTS:=Графики}"
  : "${VAULT_DASH_DATA:=Данные}"
  : "${VAULT_PATH_ACTIONS_MAC:=Действия/Mac}"
  : "${VAULT_PATH_ACTIONS_IPHONE:=Действия/IPhone}"
  : "${VAULT_PATH_CONTEXT_TODAY:=Действия/context_today.json}"
  : "${VAULT_PATH_CONTEXT_WEEK:=Действия/context_week.json}"
  : "${VAULT_PATH_IPHONE_TODAY:=Действия/iphone_today.json}"
  : "${VAULT_PATH_IPHONE_WEEK:=Действия/iphone_week.json}"
  : "${VAULT_FILE_CHART_DAILY_ACTIVITY:=Активность_за_день.png}"
  : "${VAULT_FILE_AUDIT_SYSTEM:=Аудит_системы_отчет.md}"
  : "${VAULT_FILE_AUDIT_VAULT:=Аудит_хранилища_отчет.md}"
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
