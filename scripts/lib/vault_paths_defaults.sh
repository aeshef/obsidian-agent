# shellcheck shell=bash
# Fallback when export_vault_paths_env.py is unavailable (RU layout; EN in vault_paths.en.yaml.example).
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

_vault_segment_sane() {
  local val="$1"
  [[ -n "$val" && "$val" != /* && "$val" != *".."* && "$val" != *"/"* ]]
}

_vault_sanitize_exported_segments() {
  local -a keys=(
    VAULT_FOLDER_TASKS VAULT_FOLDER_GOALS VAULT_FOLDER_DASHBOARDS
    VAULT_FOLDER_ROUTINES VAULT_FOLDER_HANDWRITTEN
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
  _vault_sanitize_exported_segments
}
