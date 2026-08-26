# shellcheck shell=bash
# Rsync spine for obsidian_sync: pull (1/1r/1a–1c) → push (2/2r/2b) → server maintenance (3) → post-pull (4).
# Sourced by scripts/obsidian_sync.sh — do not run standalone.

sync_steps_rsync_spine() {
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
}
