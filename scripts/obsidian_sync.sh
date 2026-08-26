#!/bin/zsh
_LAUNCH_AGENT_ROOT="${AGENT_ROOT:-}"
AGENT_ROOT="${0:A:h}/.."
if [[ -n "$_LAUNCH_AGENT_ROOT" && -f "$_LAUNCH_AGENT_ROOT/config/vault_paths.yaml" ]]; then
  AGENT_ROOT="$_LAUNCH_AGENT_ROOT"
fi
export AGENT_ROOT
if [[ -f "$AGENT_ROOT/.env" ]]; then
  set -a
  source "$AGENT_ROOT/.env"
  set +a
fi

# Лог каждого запуска в /tmp (доступно и из launchd) — смотреть: tail -f /tmp/obsidian_sync_debug.log
DEBUG_LOG="/tmp/obsidian_sync_debug.log"
SYNC_OK=1
SYNC_FAIL_STEP=""

_sync_fail() {
  SYNC_OK=0
  SYNC_FAIL_STEP="${1:-unknown}"
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ FAIL step=${SYNC_FAIL_STEP}" >> "$DEBUG_LOG" 2>/dev/null || true
  # Persist last critical fail step for check_sync_health (not only debug log).
  if [ -n "${SYNC_DIR:-}" ]; then
    echo "${SYNC_FAIL_STEP}" > "$SYNC_DIR/last_sync_fail_step.txt" 2>/dev/null || true
    echo "$(date '+%Y-%m-%dT%H:%M:%S') ${SYNC_FAIL_STEP}" >> "$SYNC_DIR/sync_fail_steps.log" 2>/dev/null || true
  fi
}

# Без set -e: ошибка одной папки не останавливает синк остальных
# Путь к vault: из env или по расположению скрипта (чтобы LaunchAgent работал и для ~/Obsidian Vault после миграции без правки plist)
if [[ -n "${0:A}" && -f "${0:A}" ]]; then
  # Если скрипт запущен из /tmp (устаревшая схема с копией), не трогаем vault и выходим.
  if [[ "${0:A}" == "/tmp/obsidian_sync.sh" ]]; then
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ $(sh_msg scripts.obsidian_sync.skip_tmp_copy)" >> "$DEBUG_LOG" 2>/dev/null || true
    exit 0
  fi
  _SDIR="$(dirname "${0:A}")"
  if [[ "$(basename "$_SDIR")" == "scripts" ]]; then
    P="$(cd "$_SDIR/../../.." 2>/dev/null && pwd)"
    if [[ -z "$_LAUNCH_AGENT_ROOT" ]]; then
      AGENT_ROOT="$(cd "$_SDIR/.." && pwd)"
    fi
  else
    P="$(cd "$_SDIR/../.." 2>/dev/null && pwd)"
    if [[ -z "$_LAUNCH_AGENT_ROOT" ]]; then
      AGENT_ROOT="$_SDIR"
    fi
  fi
  [[ -n "$P" && -d "$P/.obsidian" ]] && LOCAL_VAULT="$P"
fi
unset _LAUNCH_AGENT_ROOT
if [[ -n "${OBSIDIAN_AGENT_RUNTIME_ROOT:-}" && -f "${OBSIDIAN_AGENT_RUNTIME_ROOT}/agent/config/vault_paths.yaml" ]]; then
  AGENT_ROOT="${OBSIDIAN_AGENT_RUNTIME_ROOT}/agent"
fi
AGENT_ROOT="${AGENT_ROOT:-${AGENT_ROOT}}"
export AGENT_ROOT LOCAL_VAULT

# shellcheck source=scripts/lib/sh_msg.sh
source "$AGENT_ROOT/scripts/lib/sh_msg.sh"
# shellcheck source=scripts/lib/common.sh
source "$AGENT_ROOT/scripts/lib/common.sh"
if [[ -z "${LOCAL_VAULT:-}" ]]; then
  LOCAL_VAULT="$(common_resolve_vault "$AGENT_ROOT" 2>/dev/null || true)"
fi
if [[ -z "${LOCAL_VAULT:-}" ]]; then
  echo "$(sh_msg scripts.obsidian_sync.local_vault_missing)" >&2
  exit 1
fi
export LOCAL_VAULT
mkdir -p \
  "$AGENT_ROOT/planning_bot/logs" \
  "$AGENT_ROOT/knowledge_bot/logs" \
  "$AGENT_ROOT/finance_bot/logs" \
  2>/dev/null || true

# До cap_load: LaunchAgent PATH без pyenv — иначе planning .venv → pyenv shim падает на export_vault_paths.
unset PYENV_VERSION PYENV_VIRTUAL_ENV PYENV_SHELL
if [[ ":$PATH:" == *":${HOME}/.pyenv/"* ]]; then
  PATH="$(printf '%s' "$PATH" | awk -v RS=':' -v ORS=':' 'NF && $0 !~ /\.pyenv\/(shims|versions)/' | sed 's/:$//')"
  export PATH
fi

# shellcheck source=scripts/lib/capabilities.sh
# Product manifest: optional sync steps. Export failures are fail-closed.
if [[ -f "$AGENT_ROOT/scripts/lib/capabilities.sh" ]]; then
  # shellcheck disable=SC1091
  source "$AGENT_ROOT/scripts/lib/capabilities.sh"
  cap_load_env || echo "$(sh_msg scripts.obsidian_sync.capabilities_fail_closed)" >&2
  cap_load_vault_paths 2>/dev/null || true
fi
# shellcheck source=scripts/lib/vault_paths_defaults.sh
source "$AGENT_ROOT/scripts/lib/vault_paths_defaults.sh"
vault_paths_load_from_agent "$AGENT_ROOT" || {
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ ABORT: vault_paths export failed" >> "$DEBUG_LOG" 2>/dev/null || true
  echo "obsidian_sync: vault_paths export failed — sync aborted" >&2
  exit 1
}
# shellcheck source=scripts/lib/sync_runtime_from_vault.sh
source "$AGENT_ROOT/scripts/lib/sync_runtime_from_vault.sh"
# shellcheck source=scripts/lib/sync_recent_paths.sh
source "$AGENT_ROOT/scripts/lib/sync_recent_paths.sh"
# shellcheck source=scripts/lib/sync_server_authority.sh
source "$AGENT_ROOT/scripts/lib/sync_server_authority.sh"
# shellcheck source=scripts/lib/sync_steps_charts.sh
source "$AGENT_ROOT/scripts/lib/sync_steps_charts.sh"
# shellcheck source=scripts/lib/sync_steps_maintenance.sh
source "$AGENT_ROOT/scripts/lib/sync_steps_maintenance.sh"
sync_runtime_from_vault
# 0g. Drop empty wrong-locale top folders (300_Dashboards when locale=ru, etc.)
if [[ -d "$AGENT_ROOT/shared" ]]; then
  export VAULT_PATH="$LOCAL_VAULT" PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$AGENT_ROOT" && PYTHONUNBUFFERED=1 ./scripts/oa-python.sh -c "
from shared.capabilities.vault_paths_locale import cleanup_ghost_locale_folders
for line in cleanup_ghost_locale_folders('${LOCAL_VAULT}'):
    print('[ghost]', line)
" ) 2>/dev/null || true
fi
# Fallback: no manifest exporter → disable optional steps.
if ! typeset -f cap_step_enabled >/dev/null 2>&1; then
  cap_step_enabled() { return 1; }
  cap_module_enabled() { return 1; }
  echo "$(sh_msg scripts.obsidian_sync.capabilities_fail_closed)" >&2
fi

# Python sync plan (shared/sync) — refresh CAP_SYNC_* from capabilities profile.
if [[ -d "$AGENT_ROOT/shared/sync" ]]; then
  _SYNC_PLAN="$("$AGENT_ROOT/scripts/oa-python.sh" "$AGENT_ROOT/scripts/run_sync_plan.py" 2>/dev/null || true)"
  if [[ -n "$_SYNC_PLAN" ]]; then
    eval "$_SYNC_PLAN"
  fi
  unset _SYNC_PLAN
fi

VAULT_TEST="${AGENT_ROOT}/scripts/obsidian_sync.sh"
if ! test -r "$VAULT_TEST" 2>/dev/null || ! head -c1 "$VAULT_TEST" >/dev/null 2>/dev/null; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ $(sh_msg scripts.obsidian_sync.skip_no_vault_fda)" >> "$DEBUG_LOG" 2>/dev/null || true
  exit 0
fi

# Когда LaunchAgent не может писать в vault (Documents), маркеры и логи пишем в домашнюю папку
SYNC_DIR="${SYNC_STATE_DIR:-$LOCAL_VAULT/.sync}"
mkdir -p "$SYNC_DIR" 2>/dev/null || true
# Проверка именно перезаписи (launchd может разрешать append, но не overwrite в Documents)
if ! ( echo 1 > "$SYNC_DIR/.write_test" 2>/dev/null ); then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ $(sh_msg scripts.obsidian_sync.fallback_no_sync)" >> "$DEBUG_LOG" 2>/dev/null || true
  SYNC_DIR="$HOME/.sync/obsidian"
  SYNC_STATE_DIR="$SYNC_DIR"
  mkdir -p "$SYNC_DIR"
fi
rm -f "$SYNC_DIR/.write_test" 2>/dev/null
# Один экземпляр sync за раз (два LaunchAgent/plist → гонка и ложные critical fail).
SYNC_LOCK="$SYNC_DIR/obsidian_sync.lock"
if [ -d "$SYNC_LOCK" ]; then
  _sync_lock_age="$(
    (cd "$AGENT_ROOT" && ./scripts/oa-python.sh -c "
from pathlib import Path
from shared.sync.lock import lock_age_seconds
print(lock_age_seconds(Path(r'''${SYNC_LOCK}''')))
") 2>/dev/null || echo 0
  )"
  if [ "${_sync_lock_age:-0}" -gt "${OBSIDIAN_SYNC_LOCK_STALE_SEC:-7200}" ]; then
    rmdir "$SYNC_LOCK" 2>/dev/null || true
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ removed stale sync lock age=${_sync_lock_age}s" >> "$DEBUG_LOG" 2>/dev/null || true
  fi
  unset _sync_lock_age
fi
if ! mkdir "$SYNC_LOCK" 2>/dev/null; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ SKIP lock held ($SYNC_LOCK)" >> "$DEBUG_LOG" 2>/dev/null || true
  exit 0
fi
_obsidian_sync_cleanup() {
  [ -n "${VM_LOCK:-}" ] && rmdir "$VM_LOCK" 2>/dev/null || true
  rmdir "$SYNC_LOCK" 2>/dev/null || true
}
trap '_obsidian_sync_cleanup' EXIT INT TERM
SYNC_START_EPOCH="$(date +%s)"
echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ START" >> "$DEBUG_LOG" 2>/dev/null || true
# LaunchAgent без FDA не может писать в ~/Documents — не крутим rsync впустую
if [[ "$SYNC_DIR" == "$HOME/.sync/obsidian"* ]] && [[ "$LOCAL_VAULT" == *"/Documents/"* ]]; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ $(sh_msg scripts.obsidian_sync.skip_no_documents)" >> "$DEBUG_LOG" 2>/dev/null || true
  exit 0
fi
# Каждый запуск (cron или вручную) — одна строка в лог; по нему видно, срабатывает ли cron каждые 5 мин (см. plist StartInterval)
echo "$(date '+%Y-%m-%dT%H:%M:%S')" >> "$SYNC_DIR/cron_runs.log" 2>/dev/null || true

SERVER="${SERVER:-}"
SERVER_VAULT="${SERVER_VAULT:-$(common_server_vault "$AGENT_ROOT")}"
SERVER_BOTS="${SERVER_BOTS:-$(common_server_bots "$AGENT_ROOT")}"
if [ -z "$SERVER" ]; then
  echo "$(sh_msg scripts.obsidian_sync.server_missing)" >&2
  exit 1
fi
if [ -z "$SERVER_VAULT" ] || [ -z "$SERVER_BOTS" ]; then
  echo "$(sh_msg scripts.obsidian_sync.server_paths_missing)" >&2
  exit 1
fi
# LaunchAgent не видит SSH-агент; ключ из Keychain нужен явно. Иначе rsync/ssh падают с Permission denied.
export RSYNC_RSH="${RSYNC_RSH:-ssh -o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3}"
SSH_OPTS=(-o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
# shellcheck source=scripts/lib/vault_knowledge_dir.sh
source "${AGENT_ROOT}/scripts/lib/vault_knowledge_dir.sh"
KNOWLEDGE_SUBDIR="$(vault_knowledge_subdir)"

_cleanup_remote_deleted_from_manifest() {
  local label="${1:-manifest}" manifest="$SYNC_DIR/last_maintenance_deleted_paths.json"
  [ -f "$manifest" ] || return 0
  [ -n "${SERVER:-}" ] || return 0
  local deleted_lines
  deleted_lines=$(
    python3 "${AGENT_ROOT}/knowledge_bot/tools/print_deleted_manifest.py" \
      "$manifest" "$LOCAL_VAULT" 2>/dev/null
  )
  [ -n "$deleted_lines" ] || return 0
  local maintenance_log="${AGENT_ROOT}/planning_bot/logs/vault_write_maintenance.log"
  mkdir -p "$(dirname "$maintenance_log")" 2>/dev/null || true
  # If a previous failed/old sync already pulled deleted paths back from VPS,
  # remove them locally before the next pull so rsync --update cannot preserve
  # resurrected Export/duplicate files forever.
  printf '%s\n' "$deleted_lines" | while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    local_target="$LOCAL_VAULT/$rel"
    if [ -f "$local_target" ]; then
      rm -f "$local_target" && echo "[$label] local deleted: $rel" >> "$maintenance_log" 2>&1 || true
    fi
  done
  echo "$(sh_msgf scripts.obsidian_sync.step_5b_2c '{"count":"'$(echo "$deleted_lines" | wc -l | tr -d ' ')'","server":"'$SERVER'"}')" >&2
  printf '%s\n' "$deleted_lines" | ssh "${SSH_OPTS[@]}" "$SERVER" \
    "SVAULT='$SERVER_VAULT'; LABEL='$label'
     while IFS= read -r rel; do
       target=\"\$SVAULT/\$rel\"
       if [ -f \"\$target\" ]; then
         rm -f \"\$target\" && echo \"[\$LABEL] remote deleted: \$rel\" || true
       fi
     done
     exit 0" >> "$maintenance_log" 2>&1 \
    || echo "$(sh_msg scripts.obsidian_sync.step_5b_2c_fail)" >&2
}

_kb_cleanup_legacy_charts() {
  local tag="${1:-kb-chart-cleanup}"
  if cap_module_enabled KNOWLEDGE && [ -d "${AGENT_ROOT}/knowledge_bot" ]; then
    export VAULT_PATH="$LOCAL_VAULT" PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
    (cd "$AGENT_ROOT" && PYTHONUNBUFFERED=1 ./scripts/oa-python.sh -c "
from knowledge_bot.services.chart_layout import cleanup_legacy_vault_charts
for line in cleanup_legacy_vault_charts():
    print('[${tag}]', line)
" ) >> "${AGENT_ROOT}/knowledge_bot/logs/chart_layout.log" 2>&1 || true
  fi
}

# Если прошлый maintenance удалил Export/дубли, повторяем удаление на VPS до первого pull:
# иначе rsync --update снова вернёт серверные копии в локальный vault.
_cleanup_remote_deleted_from_manifest "prepull-manifest"
# Planning/knowledge: bare python3 often lacks PyYAML → context_sync / iphone_* fail in logs.
_py_imports_yaml() {
  local py="$1" sp="${2:-}"
  if [ -n "$sp" ]; then
    PYTHONPATH="${sp}${PYTHONPATH:+:$PYTHONPATH}" "$py" -c "import yaml" 2>/dev/null
  else
    "$py" -c "import yaml" 2>/dev/null
  fi
}
_pb_sp_early="${OBSIDIAN_AGENT_PYDEPS_PLANNING:-}"
if [[ -z "$_pb_sp_early" ]]; then
  _pb_sp_early="$(ls -d "$AGENT_ROOT/planning_bot/venv/lib/python"*/site-packages 2>/dev/null | head -1)"
fi
PLAN_PYTHON=""
if ! [ -t 0 ]; then
  _la_py="$(common_launchagent_python "$AGENT_ROOT/finance_bot")"
  if [ -n "$_la_py" ] && _py_imports_yaml "$_la_py" "$_pb_sp_early"; then
    PLAN_PYTHON="$_la_py"
  fi
fi
if [ -z "$PLAN_PYTHON" ]; then
  for _candidate in \
    "$AGENT_ROOT/finance_bot/.venv/bin/python" \
    "$AGENT_ROOT/planning_bot/venv/bin/python" \
    "$(common_launchagent_python "$AGENT_ROOT/finance_bot")" \
    python3; do
    if [ -n "$_candidate" ] && command -v "$_candidate" >/dev/null 2>&1 && _py_imports_yaml "$_candidate" "$_pb_sp_early"; then
      PLAN_PYTHON="$_candidate"
      break
    fi
  done
fi
unset _candidate _pb_sp_early _la_py
RSYNC_BIN="${RSYNC_BIN:-rsync}"
FLAGS=(-avz)
# Не создаём и не синхронизируем бэкапы rsync
EXCLUDE_BACKUP=( --exclude='.rsync-backup/' )
# Push Mac→VPS: удалять на сервере файлы, которых нет локально (orphans после удаления в Obsidian).
# Excludes (PUSH_EXCLUDE_300 и т.д.) защищают server-authoritative файлы от --delete.
# Отключить: RSYNC_PUSH_DELETE=0 в .env
RSYNC_PUSH_DELETE="${RSYNC_PUSH_DELETE:-1}"
PUSH_DELETE_FLAGS=()
if [ "$RSYNC_PUSH_DELETE" = "1" ]; then
  PUSH_DELETE_FLAGS=(--delete)
fi

# Исключения при подтягивании 300_Дашборды. Логи только в Логи/; корневой 📊 Логи_Действий_*.md не тянуть и не пушить (устаревшая структура).
# Аудит_*.md — только Mac (obsidian_sync 5b.1/5b.3); на VPS не генерируются, pull затирал свежий локальный отчёт.
EXCLUDE_300=(
  --exclude="${VAULT_DASH_CHARTS}/"
  --exclude='weekly_sprints.json'
  --exclude='Completions_By_Category_Chart.md'
  --exclude="${VAULT_DASH_DATA}/"
  --exclude="${VAULT_FILE_ROUTINES_CALENDAR_SUBDIR}"
  --exclude="${VAULT_FILE_ROUTINES_STATS_MD}"
  --exclude="${VAULT_FILE_ROUTINES_STATS_LEGACY_MD:-}"
  --exclude="/${VAULT_FILE_ACTION_LOG_PREFIX}*.md"
  --exclude="${VAULT_FILE_AUDIT_SYSTEM}"
  --exclude="${VAULT_FILE_AUDIT_VAULT}"
  --exclude="${VAULT_DASH_DATA}/finance.db"
  --exclude="${VAULT_DASH_DATA}/finance.db-*"
  # Mac-authoritative: auto-generated dashboards (local rebuild at end of sync; server maintenance uses stale code)
  --exclude="/${VAULT_FILE_FINANCE_DASHBOARD:-📊 Финансы_Дашборд.md}"
  --exclude="/${VAULT_FILE_HEALTH_DASHBOARD:-🏥 Здоровье.md}"
  --exclude="/${VAULT_FILE_CALENDAR_DASHBOARD:-📅 Встречи_и_фокус_недели.md}"
  --exclude="/${VAULT_FILE_ANALYTICS_DASHBOARD:-🔬 Аналитика.md}"
  --exclude="/📊 Прогресс_*.md"
  # Mac-authoritative: IMAP/Shortcuts пишут здесь; pull с VPS возвращал мусор после локального cleanup
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_ACTIONS_IPHONE}/"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_ACTIONS_MAC}/"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_IPHONE_TODAY}"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_IPHONE_WEEK}"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_CONTEXT_TODAY}"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_CONTEXT_WEEK}"
)
# Не подтягивать устаревшие пути рутин (корневой stats, markdown «Сегодня») — только новая структура.
EXCLUDE_ROUTINES=()
if [[ -n "${VAULT_FILE_ROUTINES_STATS_LEGACY_MD:-}" ]]; then
  EXCLUDE_ROUTINES+=(--exclude="/${VAULT_FILE_ROUTINES_STATS_LEGACY_MD}")
fi
if [[ -n "${VAULT_FILE_ROUTINES_CALENDAR_SUBDIR:-}" && -n "${VAULT_FILE_ROUTINES_TODAY_LEGACY_MD:-}" ]]; then
  EXCLUDE_ROUTINES+=(--exclude="${VAULT_FILE_ROUTINES_CALENDAR_SUBDIR}${VAULT_FILE_ROUTINES_TODAY_LEGACY_MD}")
fi
# 0r. Локально: миграция + удаление legacy до pull (чтобы --update не подтянул мусор с VPS).
if cap_module_enabled PLANNING && [ -d "${AGENT_ROOT}/planning_bot" ]; then
  export VAULT_PATH="$LOCAL_VAULT" PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$AGENT_ROOT" && PYTHONUNBUFFERED=1 ./scripts/oa-python.sh -c "
from planning_bot.services.routines_layout import ensure_routines_layout
for line in ensure_routines_layout(scaffold_stats=False):
    print('[0r]', line)
" ) >> "${AGENT_ROOT}/planning_bot/logs/routines_layout.log" 2>&1 || true
fi
# 1. Сервер → Локальный.
# Перед pull сохраняем локальные правки задач с last_sync_ok (мин. 30м, макс. 7д) —
# force-push в step 2, даже если сервер «новее» (бот/cron обогнал локальный edit).
# Фиксированное окно 30м недостаточно: после серии FAIL maintenance локальная доска
# с новыми задачами не попадала в force-push, --update проигрывал mtime сервера,
# а step 4 --ignore-times затирал задачи (лог task_created при этом оставался).
_LOCAL_TASKS_RECENT="$(mktemp "${TMPDIR:-/tmp}/obsidian_sync_local_recent.XXXXXX")"
_recent_epoch_30m="$(_sync_recent_tasks_since_epoch)"
echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=1 recent_tasks_since_epoch=${_recent_epoch_30m}" >> "$DEBUG_LOG" 2>/dev/null || true
_write_recent_local_task_paths "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" "$_recent_epoch_30m" "$_LOCAL_TASKS_RECENT" 2>/dev/null || true
if cap_module_enabled PLANNING; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_GOALS}/" "$LOCAL_VAULT/${VAULT_FOLDER_GOALS}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${EXCLUDE_ROUTINES[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_ROUTINES}/" "$LOCAL_VAULT/${VAULT_FOLDER_ROUTINES}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_HANDWRITTEN}/" "$LOCAL_VAULT/${VAULT_FOLDER_HANDWRITTEN}/" || SYNC_OK=0
fi
if cap_module_enabled FINANCE || cap_module_enabled PLANNING || cap_module_enabled KNOWLEDGE; then
  _authority_pull_exclude_1=()
  while IFS= read -r _ex; do
    [ -n "$_ex" ] && _authority_pull_exclude_1+=("$_ex")
  done < <(_sync_authority_pull_excludes "$_recent_epoch_30m" 2>/dev/null || true)
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${EXCLUDE_300[@]}" "${_authority_pull_exclude_1[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_DASHBOARDS}/" "$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/" || SYNC_OK=0
  unset _authority_pull_exclude_1 _ex
fi
if cap_module_enabled KNOWLEDGE; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/${KNOWLEDGE_SUBDIR}/" "$LOCAL_VAULT/${KNOWLEDGE_SUBDIR}/" || SYNC_OK=0
fi

# 1r. Рутины: миграция layout локально + удаление legacy (rsync --update не удаляет устаревшие пути).
if cap_module_enabled PLANNING && [ -d "${AGENT_ROOT}/planning_bot" ]; then
  export VAULT_PATH="$LOCAL_VAULT" PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$AGENT_ROOT" && PYTHONUNBUFFERED=1 ./scripts/oa-python.sh -c "
from planning_bot.services.routines_layout import ensure_routines_layout
from planning_bot.services.dashboard_layout import cleanup_legacy_dashboard_files
for line in ensure_routines_layout():
    print('[1r]', line)
for line in cleanup_legacy_dashboard_files():
    print('[1r]', line)
" ) >> "${AGENT_ROOT}/planning_bot/logs/routines_layout.log" 2>&1 || SYNC_OK=0
fi
if cap_module_enabled KNOWLEDGE && [ -d "${AGENT_ROOT}/knowledge_bot" ]; then
  export VAULT_PATH="$LOCAL_VAULT" PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$AGENT_ROOT" && PYTHONUNBUFFERED=1 ./scripts/oa-python.sh -c "
from knowledge_bot.services.chart_layout import cleanup_legacy_vault_charts
for line in cleanup_legacy_vault_charts():
    print('[1r-kb]', line)
" ) >> "${AGENT_ROOT}/knowledge_bot/logs/chart_layout.log" 2>&1 || SYNC_OK=0
fi

# Важно: rsync с --update НЕ удаляет на удалённой стороне файлы, которые уже убраны локально.
# Поэтому после шага 5b.2 (удаление дублей в Export на Mac) выполняется 5b.2b — тот же apply_duplicates на сервере.

# 1a. IPhone/Mac: DD.MM.YYYY → YYYY-MM-DD (сортировка); манифест → 1a-remote до push
_PLANNING_BOT="${AGENT_ROOT}/planning_bot"
if cap_module_enabled PLANNING && cap_step_enabled SYNC_MAC_IPHONE && [ -d "$_PLANNING_BOT" ] && [ -f "$_PLANNING_BOT/tools/rename_action_snapshots.py" ]; then
  touch "$_PLANNING_BOT/logs/action_snapshot_rename.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT" SYNC_STATE_DIR="$SYNC_DIR"
  export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  _rename_py="${PLAN_PYTHON:-${CHART_PYTHON:-python3}}"
  (cd "$_PLANNING_BOT" && PYTHONUNBUFFERED=1 common_run_python_script "$_rename_py" "$_PLANNING_BOT/tools/rename_action_snapshots.py" --target both --apply --vault "$LOCAL_VAULT" --sync-dir "$SYNC_DIR") \
    >> "$_PLANNING_BOT/logs/action_snapshot_rename.log" 2>&1 || true
  unset _rename_py
  _ACTION_RENAME_MANIFEST="$SYNC_DIR/action_snapshot_renames.json"
  if [ ! -f "$_ACTION_RENAME_MANIFEST" ]; then
    _ACTION_RENAME_MANIFEST="$SYNC_DIR/iphone_snapshot_renames.json"
  fi
  if [ -f "$_ACTION_RENAME_MANIFEST" ]; then
    _action_unlink=$(
      python3 - "$_ACTION_RENAME_MANIFEST" 2>/dev/null <<'PY_ACTION_UNLINK'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for p in data.get("unlink_on_server") or []:
    if p and ".." not in p:
        print(p)
PY_ACTION_UNLINK
    )
    if [ -n "$_action_unlink" ]; then
      echo "$(sh_msg scripts.obsidian_sync.step_1a_remote)" >&2
      printf '%s\n' "$_action_unlink" | ssh "${SSH_OPTS[@]}" "$SERVER" \
        "SVAULT='$SERVER_VAULT'
         while IFS= read -r rel; do
           target=\"\$SVAULT/\$rel\"
           if [ -f \"\$target\" ]; then
             rm -f \"\$target\" && echo \"[1a-remote] deleted: \$rel\" || true
           fi
         done" >> "$_PLANNING_BOT/logs/action_snapshot_rename.log" 2>&1 \
        || echo "$(sh_msg scripts.obsidian_sync.step_1a_remote_fail)" >&2
    fi
  fi
fi
unset _PLANNING_BOT _ACTION_RENAME_MANIFEST _action_unlink

# 1b. Mac-контекст локально: materialize from LaunchAgent stdout → TTL cleanup + context_*.json
_PLANNING_BOT="${AGENT_ROOT}/planning_bot"
_PLAN_SP="${OBSIDIAN_AGENT_PYDEPS_PLANNING:-}"
if [[ -z "$_PLAN_SP" ]]; then
  _PLAN_SP="$(ls -d "$_PLANNING_BOT/venv/lib/python"*/site-packages 2>/dev/null | head -1)"
fi
_PLAN_PYTHONPATH="${AGENT_ROOT}${_PLAN_SP:+:$_PLAN_SP}"
if cap_module_enabled PLANNING && cap_step_enabled SYNC_MAC_IPHONE && [ -d "$_PLANNING_BOT" ]; then
  touch "$_PLANNING_BOT/logs/context_sync.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT"
  export PYTHONPATH="${_PLAN_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
  if [ -f "$_PLANNING_BOT/tools/ingest_mac_context_stdout.py" ]; then
    (cd "$_PLANNING_BOT" && PYTHONUNBUFFERED=1 "$PLAN_PYTHON" -u tools/ingest_mac_context_stdout.py) \
      >> "$_PLANNING_BOT/logs/context_sync.log" 2>&1 || true
  fi
  if [ -f "$_PLANNING_BOT/tools/context_sync.py" ]; then
    (cd "$_PLANNING_BOT" && PYTHONUNBUFFERED=1 "$PLAN_PYTHON" -u tools/context_sync.py) \
      >> "$_PLANNING_BOT/logs/context_sync.log" 2>&1 || true
  fi
fi

# 1c. iPhone: удалить невалидные IPhone/*.txt + пересобрать iphone_*.json ДО push (канон Mac → VPS)
if cap_module_enabled PLANNING && cap_step_enabled SYNC_MAC_IPHONE && [ -d "$_PLANNING_BOT" ] && [ -f "$_PLANNING_BOT/tools/iphone_context_sync.py" ]; then
  touch "$_PLANNING_BOT/logs/iphone_context_sync.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT"
  export PYTHONPATH="${_PLAN_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$_PLANNING_BOT" && PYTHONUNBUFFERED=1 "$PLAN_PYTHON" -u tools/iphone_context_sync.py) >> "$_PLANNING_BOT/logs/iphone_context_sync.log" 2>&1 || true
fi
unset _PLANNING_BOT _PLAN_SP _PLAN_PYTHONPATH

# 2. Локальный → Сервер (отправить изменения, не затирать более новые на сервере)
# При push 300_Дашборды не отправляем сервер-авторитетные файлы (бот/cron/maintenance пишут их на сервере).
# Плюс не пушим корневой 📊 Логи_Действий_*.md — канон только 300_Дашборды/Логи/; иначе файл из корня (устаревшая структура) снова уезжает на сервер и «возвращается».
# Не пушить устаревший график (выпилен из build_finance_dashboard; иначе вернётся с мака на сервер)
PUSH_EXCLUDE_300=(
  --exclude='kanban_state.json'
  --exclude='kanban_archive_meta.json'
  --exclude='.kanban_monitor_state.json'
  --exclude="${VAULT_DASH_LOGS}/"
  --exclude='goals_task_mapping.json'
  --exclude='goals_task_mapping.staging.json'
  --exclude="/${VAULT_FILE_ACTION_LOG_PREFIX}*.md"
  --exclude="${VAULT_DASH_CHARTS}/${VAULT_FIN_CHART_DAILY_CATEGORIES_PNG}"
  --exclude="${VAULT_DASH_CHARTS}/${VAULT_LEGACY_MAINTENANCE_CHART_PNG}"
  --exclude="${VAULT_DASH_DATA}/finance.db"
  --exclude="${VAULT_DASH_DATA}/finance.db-*"
)
PUSH_EXCLUDE_ROUTINES=()
if [[ -n "${VAULT_FILE_ROUTINES_STATS_LEGACY_MD:-}" ]]; then
  PUSH_EXCLUDE_ROUTINES+=(--exclude="/${VAULT_FILE_ROUTINES_STATS_LEGACY_MD}")
fi
if [[ -n "${VAULT_FILE_ROUTINES_CALENDAR_SUBDIR:-}" && -n "${VAULT_FILE_ROUTINES_TODAY_LEGACY_MD:-}" ]]; then
  PUSH_EXCLUDE_ROUTINES+=(--exclude="${VAULT_FILE_ROUTINES_CALENDAR_SUBDIR}${VAULT_FILE_ROUTINES_TODAY_LEGACY_MD}")
fi
if cap_module_enabled PLANNING; then
  # Drop cards that already live in the closed-tasks archive so --update / force-push
  # cannot resurrect them after monthly archive. Genuine new local IDs are kept.
  if [[ -f "$AGENT_ROOT/scripts/lib/sync_kanban_protect.py" ]]; then
    python3 "$AGENT_ROOT/scripts/lib/sync_kanban_protect.py" strip-dir \
      --tasks-root "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}" \
      >>"$DEBUG_LOG" 2>&1 || true
  fi
  # Recent local task files (since last_sync_ok / 30m): force-push with --ignore-times.
  # Safety filter: never clobber a server kanban that has task IDs missing locally.
  _sync_filter_force_push_tasks_safe "$_LOCAL_TASKS_RECENT" "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}" 2>>"$DEBUG_LOG" || true
  _recent_task_count="$(wc -l < "$_LOCAL_TASKS_RECENT" 2>/dev/null | tr -d ' ' || echo 0)"
  if [ "${_recent_task_count:-0}" -gt 0 ]; then
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=2 force_push_recent count=${_recent_task_count}" >> "$DEBUG_LOG" 2>/dev/null || true
    "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --ignore-times --files-from="$_LOCAL_TASKS_RECENT" "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
  fi
  rm -f "$_LOCAL_TASKS_RECENT" 2>/dev/null || true
  _sync_force_push_recent_authority_json "$_recent_epoch_30m" 2>/dev/null || true
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_GOALS}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_GOALS}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" "${PUSH_EXCLUDE_ROUTINES[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_ROUTINES}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_ROUTINES}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_HANDWRITTEN}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_HANDWRITTEN}/" || SYNC_OK=0
fi
if cap_module_enabled FINANCE || cap_module_enabled PLANNING || cap_module_enabled KNOWLEDGE; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" "${PUSH_EXCLUDE_300[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_DASHBOARDS}/" || SYNC_OK=0
fi
if cap_module_enabled KNOWLEDGE; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --update "$LOCAL_VAULT/${KNOWLEDGE_SUBDIR}/" "$SERVER:$SERVER_VAULT/${KNOWLEDGE_SUBDIR}/" || SYNC_OK=0
fi

# 2r. VPS: миграция рутин + удаление legacy paths на сервере.
if cap_module_enabled PLANNING && [ -d "${AGENT_ROOT}/planning_bot" ]; then
  echo "[2r] routines layout on server" >&2
  _legacy_stats="${VAULT_FILE_ROUTINES_STATS_LEGACY_MD:-}"
  _legacy_today="${VAULT_FILE_ROUTINES_CALENDAR_SUBDIR:-}${VAULT_FILE_ROUTINES_TODAY_LEGACY_MD:-}"
  if [[ -n "$_legacy_stats" || -n "$_legacy_today" ]]; then
    ssh "${SSH_OPTS[@]}" "$SERVER" \
      "SVAULT='${SERVER_VAULT}' FOLDER='${VAULT_FOLDER_ROUTINES}' LEGACY_STATS='${_legacy_stats}' LEGACY_TODAY='${_legacy_today}'
       for rel in \"\$LEGACY_STATS\" \"\$LEGACY_TODAY\"; do
         if [[ -n \"\$rel\" ]]; then
           target=\"\$SVAULT/\$FOLDER/\$rel\"
           if [[ -f \"\$target\" ]]; then rm -f \"\$target\" && echo \"[2r-remote] deleted \$rel\"; fi
         fi
       done" >> "${AGENT_ROOT}/planning_bot/logs/routines_layout.log" 2>&1 || SYNC_OK=0
  fi
  ssh "${SSH_OPTS[@]}" "$SERVER" \
    "VAULT_PATH='${SERVER_VAULT}' AGENT_LOCALE='${AGENT_LOCALE:-en}' PYTHONPATH='${SERVER_BOTS}' cd '${SERVER_BOTS}' && ./scripts/oa-python.sh -c \"
from planning_bot.services.routines_layout import ensure_routines_layout
from planning_bot.services.dashboard_layout import cleanup_legacy_dashboard_files
for line in ensure_routines_layout():
    print('[2r]', line)
for line in cleanup_legacy_dashboard_files():
    print('[2r]', line)
\"" >> "${AGENT_ROOT}/planning_bot/logs/routines_layout.log" 2>&1 || SYNC_OK=0
fi
if cap_module_enabled KNOWLEDGE && [ -d "${AGENT_ROOT}/knowledge_bot" ]; then
  echo "[2r-kb] legacy vault charts on server" >&2
  ssh "${SSH_OPTS[@]}" "$SERVER" \
    "VAULT_PATH='${SERVER_VAULT}' AGENT_LOCALE='${AGENT_LOCALE:-en}' PYTHONPATH='${SERVER_BOTS}' cd '${SERVER_BOTS}' && ./scripts/oa-python.sh -c \"
from knowledge_bot.services.chart_layout import cleanup_legacy_vault_charts
for line in cleanup_legacy_vault_charts():
    print('[2r-kb]', line)
\"" >> "${AGENT_ROOT}/knowledge_bot/logs/chart_layout.log" 2>&1 || SYNC_OK=0
fi

# 2b. На VPS: тот же cleanup/JSON для IPhone (старый мусор мог остаться только на сервере)
if cap_module_enabled PLANNING && cap_step_enabled SYNC_MAC_IPHONE && [ -d "${AGENT_ROOT}/planning_bot" ] && [ -f "${AGENT_ROOT}/planning_bot/tools/iphone_context_sync.py" ]; then
  echo "$(sh_msg scripts.obsidian_sync.step_2b)" >&2
  ssh "${SSH_OPTS[@]}" "$SERVER" "cd '${SERVER_BOTS}/planning_bot' && VAULT_PATH='${SERVER_VAULT}' PYTHONPATH='${SERVER_BOTS}' ./.venv/bin/python -u tools/iphone_context_sync.py" \
    >> "${AGENT_ROOT}/planning_bot/logs/iphone_context_sync.log" 2>&1 || SYNC_OK=0
fi

# 3. Обслуживание vault на сервере (VAULT_PATH=$SERVER_VAULT). Kanban — только cron на VPS.
if cap_module_enabled PLANNING; then
  echo "$(sh_msg scripts.obsidian_sync.step_3)" >&2
  # Longer ServerAlive: maintenance can be quiet for >45s; retry once on flaky SSH.
  _ssh_maint_opts=(-o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=20 -o ServerAliveCountMax=12)
  _step3_ok=0
  for _try in 1 2; do
    if ssh "${_ssh_maint_opts[@]}" "$SERVER" \
      "cd ${SERVER_BOTS}/planning_bot && ./scripts/run_maintenance_from_sync.sh"; then
      _step3_ok=1
      break
    fi
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=3-server-maintenance retry=${_try}" >> "$DEBUG_LOG" 2>/dev/null || true
    sleep 3
  done
  unset _try _ssh_maint_opts
  if [ "$_step3_ok" != 1 ]; then
    echo "$(sh_msgf scripts.obsidian_sync.step_3_fail '{"log_path":"'${SERVER_BOTS}/planning_bot/logs/maintenance.log'"}')" >&2
    _sync_fail "3-server-maintenance"
  fi
  unset _step3_ok
fi

# 4. Подтянуть обновлённые файлы с сервера после maintenance.
# 100_: ignore-times — канон сортировки с VPS. Но если файл задачи поменяли локально уже ПОСЛЕ старта
# текущего sync-цикла (Obsidian UI во время длительного maintenance), не тянем его обратно с VPS:
# иначе финальный pull стирает только что созданные/перемещённые задачи до следующего цикла.
# Если step 3 (maintenance) уже упал — НЕ делаем ignore-times pull доски: сервер может быть
# в частично обновлённом/старом состоянии относительно локальных task_created; только --update.
# 300_: --update + EXCLUDE_300 (в т.ч. Аудит_*.md) — не затирать Mac-only отчёты.
echo "$(sh_msg scripts.obsidian_sync.step_4)" >&2
if cap_module_enabled PLANNING; then
  _recent_tasks_exclude="$(mktemp "${TMPDIR:-/tmp}/obsidian_sync_recent_tasks.XXXXXX")"
  _protect_tasks_exclude="$(mktemp "${TMPDIR:-/tmp}/obsidian_sync_protect_tasks.XXXXXX")"
  _recent_tasks_count="$(_write_recent_local_task_paths "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" "$SYNC_START_EPOCH" "$_recent_tasks_exclude" 2>/dev/null || echo 0)"
  _protect_count="$(_sync_write_pull_protect_excludes "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}" "$_protect_tasks_exclude" 2>>"$DEBUG_LOG" || echo 0)"
  if [ "${_protect_count:-0}" -gt 0 ]; then
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=4 protect_local_task_ids count=${_protect_count}" >> "$DEBUG_LOG" 2>/dev/null || true
    cat "$_protect_tasks_exclude" >> "$_recent_tasks_exclude" 2>/dev/null || true
    # Local board has IDs the server lost — push it before any pull can clobber.
    "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --ignore-times --files-from="$_protect_tasks_exclude" \
      "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
  fi
  _tasks_pull_mode="ignore-times"
  if [ -n "${SYNC_FAIL_STEP:-}" ] || [ "${SYNC_OK:-1}" != "1" ]; then
    _tasks_pull_mode="update"
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=4 tasks_pull_safe mode=update reason=prior_fail step=${SYNC_FAIL_STEP:-none}" >> "$DEBUG_LOG" 2>/dev/null || true
  fi
  _exclude_count="$(wc -l < "$_recent_tasks_exclude" 2>/dev/null | tr -d ' ' || echo 0)"
  if [ "$_tasks_pull_mode" = "update" ]; then
    if [ "${_exclude_count:-0}" -gt 0 ]; then
      "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update --exclude-from="$_recent_tasks_exclude" \
        "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
    else
      "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update \
        "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
    fi
  elif [ "${_exclude_count:-0}" -gt 0 ]; then
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=4 skip_protected_or_recent_tasks count=${_exclude_count}" >> "$DEBUG_LOG" 2>/dev/null || true
    "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --ignore-times --exclude-from="$_recent_tasks_exclude" \
      "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
  else
    "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --ignore-times \
      "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
  fi
  rm -f "$_recent_tasks_exclude" "$_protect_tasks_exclude" 2>/dev/null || true
  unset _tasks_pull_mode _protect_count _exclude_count
  # Same heal as VPS cron (Python service, locale via domain_messages) — after pull protect.
  if [ -d "${AGENT_ROOT}/planning_bot" ]; then
    (
      export VAULT_PATH="$LOCAL_VAULT" PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
      cd "$AGENT_ROOT" && ./scripts/oa-python.sh -m planning_bot.services.kanban_orphan_heal --days 7 \
        >> "${AGENT_ROOT}/planning_bot/logs/kanban_orphan_heal.log" 2>&1
    ) || true
  fi
fi
if cap_module_enabled FINANCE || cap_module_enabled PLANNING || cap_module_enabled KNOWLEDGE; then
  _authority_pull_exclude_4=()
  while IFS= read -r _ex; do
    [ -n "$_ex" ] && _authority_pull_exclude_4+=("$_ex")
  done < <(_sync_authority_pull_excludes "$SYNC_START_EPOCH" 2>/dev/null || true)
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${EXCLUDE_300[@]}" "${_authority_pull_exclude_4[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_DASHBOARDS}/" "$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/" || SYNC_OK=0
  unset _authority_pull_exclude_4 _ex
fi

TODAY=$(date +%Y-%m-%d)
NOW_ISO=$(date +%Y-%m-%dT%H:%M:%S)
# Частая опечатка: FORCE_CHART=1 → FORCE_CHARTS=1
if [ -n "${FORCE_CHART:-}" ] && [ -z "${FORCE_CHARTS:-}" ]; then
  export FORCE_CHARTS=1
fi

# Python для графиков: LaunchAgent часто не читает planning_bot/venv/pyvenv.cfg (TCC/FDA).
# Сначала homebrew из LaunchAgent; venv — если реально импортирует yaml.
_pb_venv="$AGENT_ROOT/planning_bot/venv"
_pb_sp="${OBSIDIAN_AGENT_PYDEPS_PLANNING:-}"
if [[ -z "$_pb_sp" ]]; then
  _pb_sp="$(ls -d "$_pb_venv/lib/python"*/site-packages 2>/dev/null | head -1)"
fi
_chart_py_ok() {
  local py="$1" sp="${2:-}"
  if [ -n "$sp" ]; then
    PYTHONPATH="${sp}${PYTHONPATH:+:$PYTHONPATH}" "$py" -c "import yaml" 2>/dev/null
  else
    "$py" -c "import yaml" 2>/dev/null
  fi
}
CHART_PYTHON="${PLAN_PYTHON:-}"
if [ -z "$CHART_PYTHON" ]; then
  if ! [ -t 0 ]; then
    _la_chart="$(common_launchagent_python "$AGENT_ROOT/finance_bot")"
    if [ -n "$_la_chart" ] && _chart_py_ok "$_la_chart" "$_pb_sp"; then
      CHART_PYTHON="$_la_chart"
    fi
  fi
  if [ -z "$CHART_PYTHON" ] && [ -x "$_pb_venv/bin/python" ] && _chart_py_ok "$_pb_venv/bin/python" "$_pb_sp"; then
    CHART_PYTHON="$_pb_venv/bin/python"
  elif [ -z "$CHART_PYTHON" ]; then
    _la_fb="$(common_launchagent_python "$AGENT_ROOT/finance_bot")"
    if [ -n "$_la_fb" ] && _chart_py_ok "$_la_fb" "$_pb_sp"; then
      CHART_PYTHON="$_la_fb"
    elif command -v python3 >/dev/null 2>&1 && _chart_py_ok python3 "$_pb_sp"; then
      CHART_PYTHON=python3
    fi
  fi
fi
unset _la_chart _la_fb
if [ -n "$_pb_sp" ]; then
  CHART_PYTHONPATH="${AGENT_ROOT}:${_pb_sp}"
else
  CHART_PYTHONPATH="${AGENT_ROOT}"
fi
unset _pb_venv _pb_sp _chart_py_ok

# 4b. Planning kanban hygiene on every sync cycle:
# keep board IDs and deterministic sorting independent from knowledge-maintenance profile.
PLANNING_BOT="${PLANNING_BOT:-$AGENT_ROOT/planning_bot}"
_kanban_py="${CHART_PYTHON:-${PLAN_PYTHON:-}}"
if [ -d "$PLANNING_BOT" ] && [ -n "$_kanban_py" ] && [ -f "$PLANNING_BOT/tools/vault_maintenance/kanban_hygiene.py" ]; then
  touch "$PLANNING_BOT/logs/kanban_hygiene.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT"
  _kanban_sp="${OBSIDIAN_AGENT_PYDEPS_PLANNING:-}"
  if [ -z "$_kanban_sp" ]; then
    _kanban_sp="$(ls -d "$PLANNING_BOT/venv/lib/python"*/site-packages 2>/dev/null | head -1)"
  fi
  if [ -n "$_kanban_sp" ]; then
    export PYTHONPATH="${AGENT_ROOT}:${_kanban_sp}${PYTHONPATH:+:$PYTHONPATH}"
  else
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
  fi
  if (cd "$PLANNING_BOT" && FROM_SYNC=1 PYTHONUNBUFFERED=1 common_run_python_script "$_kanban_py" "$PLANNING_BOT/tools/vault_maintenance/kanban_hygiene.py") >> "$PLANNING_BOT/logs/kanban_hygiene.log" 2>&1; then
    : # ok
  else
    echo "warning: kanban_hygiene failed (see $PLANNING_BOT/logs/kanban_hygiene.log)" >&2
    _sync_fail "4b-kanban-hygiene"
  fi
fi
unset _kanban_sp
unset _kanban_py

sync_steps_charts_planning

sync_steps_charts_calendar

sync_steps_charts_agent_cost

# 5d. График КБЖУ: перенесён сразу после 5b.4b (iphone_context_sync) — иначе PNG строится по
# вчерашнему iphone_week.json и день с ручным .txt в IPhone/ даёт пустой/битый столбец.
# (см. шаг 5d ниже, после iphone_context_sync)

sync_steps_maintenance_audits

# 5b.4 iPhone-контекст из Gmail IMAP (iphone_mail_sync)
# Требует GMAIL_IMAP_USER и GMAIL_IMAP_APP_PASSWORD в корневом .env (уже загружен в начале скрипта).
# ВАЖНО: после source .env VAULT_PATH может быть /root/... (сервер) — принудительно подставляем LOCAL_VAULT (Mac).
# Throttle: не чаще IPHONE_IMAP_MIN_INTERVAL сек (по умолч. 300), кроме FORCE_IPHONE_SYNC=1. Раньше был «раз в сутки»
# по дате — из-за этого письмо, пришедшее в 23:45, не забирали, если первый прогон был утром.
# Лог: planning_bot/logs/iphone_mail_sync; метка: .sync/iphone_imap_last_ok_epoch
IPHONE_IMAP_THROTTLE_FILE="${SYNC_DIR}/iphone_imap_last_ok_epoch"
_MIN="${IPHONE_IMAP_MIN_INTERVAL:-300}"
touch "$PLANNING_BOT/logs/iphone_mail_sync.log" 2>/dev/null || true
_SHOULD_IMAP=0
if [ -n "${FORCE_IPHONE_SYNC:-}" ]; then
  _SHOULD_IMAP=1
elif [ ! -f "$IPHONE_IMAP_THROTTLE_FILE" ]; then
  _SHOULD_IMAP=1
else
  _LASTI=$(head -1 "$IPHONE_IMAP_THROTTLE_FILE" 2>/dev/null || echo 0)
  _NOWI=$(date +%s)
  if [ -z "$_LASTI" ] || [ "$_LASTI" = "0" ] || [ "$((_NOWI - _LASTI))" -ge "$_MIN" ]; then
    _SHOULD_IMAP=1
  fi
fi
if cap_step_enabled SYNC_GMAIL_HEALTH && [ "$_SHOULD_IMAP" = "1" ] && [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/tools/iphone_mail_sync.py" ]; then
  echo "$(sh_msg scripts.obsidian_sync.step_5b_4)" >&2
  # Локальный vault, не путь с сервера из .env
  export VAULT_PATH="$LOCAL_VAULT"
  if [ -n "${GMAIL_IMAP_USER:-}" ] && [ -n "${GMAIL_IMAP_APP_PASSWORD:-}" ]; then
    export LOCAL_VAULT PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
    # Окно «сегодня+вчера» по дате Date (см. IPHONE_MAIL_SYNC_RECENT_DAYS; по умолч. 2)
    export IPHONE_MAIL_SYNC_TODAY_ONLY="${IPHONE_MAIL_SYNC_TODAY_ONLY:-1}"
    export IPHONE_MAIL_SYNC_RECENT_DAYS="${IPHONE_MAIL_SYNC_RECENT_DAYS:-2}"
    if [ -n "${FORCE_IPHONE_SYNC_ALL_DAYS:-}" ]; then
      export IPHONE_MAIL_SYNC_TODAY_ONLY=0
    fi
    # Защита от «вечного» зависания IMAP: если шаг висит слишком долго, убиваем и продолжаем цикл синка.
    _IMAP_TIMEOUT="${IPHONE_MAIL_SYNC_TIMEOUT_SECS:-480}"
    (
      cd "$PLANNING_BOT" && PYTHONUNBUFFERED=1 common_run_python_script "$PLAN_PYTHON" "$PLANNING_BOT/tools/iphone_mail_sync.py"
    ) >> "$PLANNING_BOT/logs/iphone_mail_sync.log" 2>&1 &
    _imap_pid=$!
    (
      sleep "$_IMAP_TIMEOUT"
      if kill -0 "$_imap_pid" 2>/dev/null; then
        echo "$(date '+%Y-%m-%dT%H:%M:%S') iphone_mail_sync timeout ${_IMAP_TIMEOUT}s; terminate pid=${_imap_pid}" >> "$PLANNING_BOT/logs/iphone_mail_sync.log" 2>&1 || true
        kill -TERM "$_imap_pid" 2>/dev/null || true
        sleep 5
        kill -KILL "$_imap_pid" 2>/dev/null || true
      fi
    ) &
    _imap_watchdog_pid=$!
    wait "$_imap_pid"
    _imap_rc=$?
    kill "$_imap_watchdog_pid" 2>/dev/null || true
    wait "$_imap_watchdog_pid" 2>/dev/null || true
    if [ "$_imap_rc" -eq 0 ]; then
      date +%s > "$IPHONE_IMAP_THROTTLE_FILE" 2>/dev/null || true
    else
      echo "$(date '+%Y-%m-%dT%H:%M:%S') iphone_mail_sync failed/timeout rc=${_imap_rc}" >> "$PLANNING_BOT/logs/iphone_mail_sync.log" 2>/dev/null || true
    fi
  else
    echo "$(sh_msgf scripts.obsidian_sync.step_5b_4_skip '{"env_path":"'$AGENT_ROOT/.env'"}')" >&2
  fi
fi

# 5b.4b Каждый синк: iphone_today.json / iphone_week.json из IPhone/*.txt (без IMAP, быстро)
if cap_step_enabled SYNC_MAC_IPHONE && [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/tools/iphone_context_sync.py" ]; then
  touch "$PLANNING_BOT/logs/iphone_context_sync.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT"
  export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$PLANNING_BOT" && PYTHONUNBUFFERED=1 common_run_python_script "$PLAN_PYTHON" "$PLANNING_BOT/tools/iphone_context_sync.py") >> "$PLANNING_BOT/logs/iphone_context_sync.log" 2>&1 || true
fi

sync_steps_charts_nutrition_health

sync_steps_charts_finance

# 5e. Каждый синк: read-only копия vault в iCloud для iPhone (100/200/300 без Данные/Действия/400 + .obsidian).
# Односторонне Mac→iCloud; тот же цикл, что rsync с сервером (LaunchAgent ~5 мин). SKIP_MOBILE_VAULT=1 — отключить.
MOBILE_EXPORT_SCRIPT="$AGENT_ROOT/scripts/export_mobile_vault.sh"
MOBILE_EXPORT_LOG="$SYNC_DIR/mobile_vault_export.log"
if cap_module_enabled PLANNING && [ -z "${SKIP_MOBILE_VAULT:-}" ] && [ -x "$MOBILE_EXPORT_SCRIPT" ]; then
  touch "$MOBILE_EXPORT_LOG" 2>/dev/null || true
  echo "$(sh_msgf scripts.obsidian_sync.step_5e '{"log":"'$MOBILE_EXPORT_LOG'"}')" >&2
  _mobile_rc=0
  _mobile_tmp="$(mktemp "${TMPDIR:-/tmp}/mobile_export.XXXXXX")"
  SRC="$LOCAL_VAULT" zsh "$MOBILE_EXPORT_SCRIPT" > "$_mobile_tmp" 2>&1 || _mobile_rc=$?
  cat "$_mobile_tmp" >> "$MOBILE_EXPORT_LOG" 2>/dev/null || true
  if [ "$_mobile_rc" -ne 0 ]; then
    _mobile_err="$(grep -E 'export_mobile_vault:|error|Error|not configured' "$_mobile_tmp" 2>/dev/null | tail -1 || true)"
    [ -n "$_mobile_err" ] && echo "  reason: $_mobile_err" >> "$MOBILE_EXPORT_LOG" 2>/dev/null || true
  fi
  common_rotate_log "$MOBILE_EXPORT_LOG" 200 120
  rm -f "$_mobile_tmp"
  if [ "$_mobile_rc" -eq 0 ]; then
    echo "$NOW_ISO" > "$SYNC_DIR/mobile_vault_last_ok.txt" 2>/dev/null || true
    rm -f "$SYNC_DIR/mobile_vault_last_fail.txt" "$SYNC_DIR/mobile_vault_consecutive_fails.txt" 2>/dev/null || true
  else
    echo "$(date '+%Y-%m-%dT%H:%M:%S') export_mobile_vault failed rc=${_mobile_rc}" >> "$MOBILE_EXPORT_LOG" 2>/dev/null || true
    echo "$NOW_ISO" > "$SYNC_DIR/mobile_vault_last_fail.txt" 2>/dev/null || true
    _mf="$(tr -d '\n' <"$SYNC_DIR/mobile_vault_consecutive_fails.txt" 2>/dev/null || echo 0)"
    case "$_mf" in ''|*[!0-9]*) _mf=0 ;; esac
    echo "$((_mf + 1))" > "$SYNC_DIR/mobile_vault_consecutive_fails.txt" 2>/dev/null || true
    unset _mf
    echo "$(sh_msgf scripts.obsidian_sync.step_5e_fail '{"rc":"'${_mobile_rc}'","log":"'$MOBILE_EXPORT_LOG'"}')" >&2
  fi
  unset _mobile_rc
elif [ -n "${SKIP_MOBILE_VAULT:-}" ]; then
  echo "$(sh_msg scripts.obsidian_sync.step_5e_skip)" >&2
fi

# 7. Маркер успешного синка и отчёт о здоровье (чтобы видеть, что сломалось, без поиска по логам)
echo "$(sh_msg scripts.obsidian_sync.step_7)" >&2
if [ "${SYNC_OK:-0}" = "1" ]; then
  if echo "$NOW_ISO" > "$SYNC_DIR/last_sync_ok.txt" 2>/dev/null; then WROTE=1; else WROTE=0; fi
  rm -f "$SYNC_DIR/last_sync_failed.txt" "$SYNC_DIR/last_sync_fail_step.txt" 2>/dev/null || true
  READ_BACK="$(head -1 "$SYNC_DIR/last_sync_ok.txt" 2>/dev/null)"
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ OK last_sync_ok=$SYNC_DIR wrote=$WROTE content=$READ_BACK" >> "$DEBUG_LOG" 2>/dev/null || true
else
  WROTE=0
  _fail_step="${SYNC_FAIL_STEP:-unknown}"
  echo "$NOW_ISO step=${_fail_step} (see $DEBUG_LOG)" > "$SYNC_DIR/last_sync_failed.txt" 2>/dev/null || true
  echo "$_fail_step" > "$SYNC_DIR/last_sync_fail_step.txt" 2>/dev/null || true
  READ_BACK="$(head -1 "$SYNC_DIR/last_sync_ok.txt" 2>/dev/null)"
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ WARN critical sync steps failed; step=${_fail_step}; last_sync_ok not updated (prev=$READ_BACK)" >> "$DEBUG_LOG" 2>/dev/null || true
  unset _fail_step
fi
HEALTH_SCRIPT="${AGENT_ROOT}/scripts/check_sync_health.sh"
if [ -x "$HEALTH_SCRIPT" ]; then
  "$HEALTH_SCRIPT" "$LOCAL_VAULT" "$SYNC_DIR" >> "$SYNC_DIR/health.log" 2>&1 || true
else
  # Inline health check (scripts/ папка отсутствует): пишем ключевые маркеры в health.log.
  _h_sync="$(cat "$SYNC_DIR/last_sync_ok.txt" 2>/dev/null | tr -d '\n' || echo 'N/A')"
  _h_maint="$(cat "$VM_MARKER" 2>/dev/null | tr -d '\n' || echo 'N/A')"
  _h_fin="$(cat "$SYNC_DIR/finance_dashboard_last_ok.txt" 2>/dev/null | cut -c1-10 | tr -d '\n' || echo 'N/A')"
  _h_mobile="$(cat "$SYNC_DIR/mobile_vault_last_ok.txt" 2>/dev/null | cut -c1-16 | tr -d '\n' || echo 'N/A')"
  echo "[$(date '+%Y-%m-%dT%H:%M:%S')] health: sync=${_h_sync} maint=${_h_maint} finance=${_h_fin} mobile=${_h_mobile} — OK" >> "$SYNC_DIR/health.log" 2>&1 || true
  unset _h_sync _h_maint _h_fin _h_mobile
  _trim_log "$SYNC_DIR/health.log" 500 300
fi
echo "$(sh_msg scripts.obsidian_sync.done)" >&2
