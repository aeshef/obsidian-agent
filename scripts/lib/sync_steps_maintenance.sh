# shellcheck shell=bash
# Vault audit / write-maintenance steps for obsidian_sync (5b.1–5b.3 + setup).
# Sourced by scripts/obsidian_sync.sh — do not run standalone.

sync_steps_maintenance_audits() {
# 5b. Раз в сутки: read-only аудиты (отдельные маркеры, чтобы тяжёлый проход по 700 не крутился каждые 2 мин при сбое planning).
# Ничего в данных не меняет — только перезаписывает отчёты в 300_Дашборды/. FORCE_SYSTEM_AUDIT=1 — принудительно оба типа сегодня.
PLANNING_BOT="$AGENT_ROOT/planning_bot"
SYS_AUDIT_MARKER="$SYNC_DIR/daily_system_audit_date.txt"
KN_AUDIT_MARKER="$SYNC_DIR/daily_knowledge_vault_audit_date.txt"
KNOWLEDGE_BOT="$AGENT_ROOT/knowledge_bot"
# KN_PYTHON для аудита vault: pyenv python заблокирован macOS TCC от Documents когда запускается из LaunchAgent.
# /opt/homebrew/bin/python3 или PATH-level python3 НЕ попадают под это ограничение и имеют доступ к Documents.
# PYTHONPATH: venv site-packages (yaml и др.) + knowledge_bot как пакет + Agent root.
_kn_venv="$KNOWLEDGE_BOT/venv"
_kn_sp="${OBSIDIAN_AGENT_PYDEPS_PLANNING:-}"
if [[ -z "$_kn_sp" ]]; then
  _kn_sp="$(find "$_kn_venv/lib" -maxdepth 2 -name site-packages -type d 2>/dev/null | head -1)"
fi
if [ -n "$_kn_sp" ]; then
  export PYTHONPATH="${KNOWLEDGE_BOT}:${AGENT_ROOT}:${_kn_sp}${PYTHONPATH:+:$PYTHONPATH}"
elif [ -n "${OBSIDIAN_AGENT_PYDEPS_KNOWLEDGE:-}" ]; then
  export PYTHONPATH="${KNOWLEDGE_BOT}:${AGENT_ROOT}:${OBSIDIAN_AGENT_PYDEPS_KNOWLEDGE}${PYTHONPATH:+:$PYTHONPATH}"
else
  export PYTHONPATH="${KNOWLEDGE_BOT}:${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
fi
if [ -n "$(common_launchagent_python "$AGENT_ROOT/finance_bot" 2>/dev/null)" ]; then
  KN_PYTHON="$(common_launchagent_python "$AGENT_ROOT/finance_bot")"
elif command -v python3 >/dev/null 2>&1; then
  KN_PYTHON=python3
else
  KN_PYTHON=""
fi
unset _kn_venv _kn_sp
mkdir -p "$PLANNING_BOT/logs" 2>/dev/null || true
# Плейсхолдеры: иначе tail -f падает, пока 5b.1/5b.2/5b.3 ни разу не писали (маркер «уже сегодня» → шаги пропущены).
touch \
  "$PLANNING_BOT/logs/system_audit.log" \
  "$PLANNING_BOT/logs/charts.log" \
  "$PLANNING_BOT/logs/kanban_hygiene.log" \
  "$PLANNING_BOT/logs/vault_write_maintenance.log" \
  "$PLANNING_BOT/logs/iphone_mail_sync.log" \
  "$PLANNING_BOT/logs/iphone_context_sync.log" \
  "$PLANNING_BOT/logs/context_sync.log" \
  2>/dev/null || true
# Log rotation policy: keep recurring LaunchAgent/cron logs bounded without a separate daemon.
common_scrub_ssh_noise "/tmp/obsidian-sync.err" || true
common_scrub_ssh_noise "$DEBUG_LOG" || true
common_rotate_log "$DEBUG_LOG" 2000 1000
common_rotate_log "/tmp/obsidian-sync.out" 8000 3000
common_rotate_log "/tmp/obsidian-sync.err" 4000 1500
common_rotate_log "/tmp/finance-dashboard-sync.log" 3000 1200
common_rotate_log "/tmp/calendar-obsidian.out" 12000 3000
common_rotate_log "/tmp/calendar-obsidian.err" 2000 800
common_rotate_log "/tmp/context-obsidian.out" 5000 1500
common_rotate_log "/tmp/context-obsidian.err" 2000 800
common_rotate_log "/tmp/mac-context-obsidian.out" 8000 2000
common_rotate_log "/tmp/mac-context-obsidian.err" 2000 800
common_rotate_log "$SYNC_DIR/cron_runs.log" 3000 1200
common_rotate_log "$SYNC_DIR/health.log" 3000 1200
common_rotate_log "$SYNC_DIR/finance_dashboard_daily.log" 12000 5000
common_rotate_log "$SYNC_DIR/mobile_vault_export.log" 3000 1000
common_rotate_log "$PLANNING_BOT/logs/vault_write_maintenance.log" 8000 4000
common_rotate_log "$PLANNING_BOT/logs/system_audit.log" 3000 1200
common_rotate_log "$PLANNING_BOT/logs/charts.log" 1000 500
common_rotate_log "$PLANNING_BOT/logs/kanban_hygiene.log" 6000 2000
common_rotate_log "$PLANNING_BOT/logs/add_ids_watcher.log" 12000 3000
common_rotate_log "$PLANNING_BOT/logs/iphone_mail_sync.log" 8000 4000
common_rotate_log "$PLANNING_BOT/logs/iphone_context_sync.log" 8000 3000
common_rotate_log "$AGENT_ROOT/finance_bot/logs/finance_dashboard_daily.log" 12000 5000
common_rotate_log "$AGENT_ROOT/finance_bot/logs/bot.log" 12000 4000
common_rotate_log "$AGENT_ROOT/knowledge_bot/logs/bot.log" 12000 4000
_VAULT_AGENT_ROOT="$LOCAL_VAULT/${VAULT_FOLDER_AUTOMATION}/${VAULT_PATH_AGENT_SUBDIR}"
common_rotate_log "$_VAULT_AGENT_ROOT/planning_bot/logs/add_ids_watcher.log" 12000 3000
common_rotate_log "$_VAULT_AGENT_ROOT/planning_bot/logs/vault_write_maintenance.log" 8000 4000
common_rotate_log "$_VAULT_AGENT_ROOT/planning_bot/logs/charts.log" 1000 500
common_rotate_log "$_VAULT_AGENT_ROOT/finance_bot/logs/finance_dashboard_daily.log" 12000 5000
unset _VAULT_AGENT_ROOT
_SYNCTHING_LOG="${SYNCTHING_LOG:-$(common_platform_value "$AGENT_ROOT" log_rotation syncthing_log "")}"
common_rotate_log "$_SYNCTHING_LOG" 12000 3000
unset _SYNCTHING_LOG

# 5b.1 Аудит planning/sync (лёгкий, секунды)
if cap_module_enabled PLANNING && { [ -n "${FORCE_SYSTEM_AUDIT:-}" ] || [ ! -f "$SYS_AUDIT_MARKER" ] || [ "$(cat "$SYS_AUDIT_MARKER" 2>/dev/null)" != "$TODAY" ]; }; then
  if [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_system_audit_report.py" ]; then
    echo "$(sh_msg scripts.obsidian_sync.step_5b_1)" >&2
    export LOCAL_VAULT
    export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
    _sys_audit_py="${CHART_PYTHON:-${PLAN_PYTHON:-python3}}"
    if cd "$PLANNING_BOT" && common_run_python_script "$_sys_audit_py" scripts/build_system_audit_report.py --vault "$LOCAL_VAULT" >> logs/system_audit.log 2>&1; then
      echo "$TODAY" > "$SYS_AUDIT_MARKER"
    fi
  fi
fi

# 5b.2 Раз в сутки: запись в 700_ (хабы, wikilinks, опц. reprocess) — config/vault_maintenance.yaml, маркер .sync
# До reorder был «5b.3». Идёт ПЕРЕД 5b.3 (аудит): чтобы в Аудит_хранилища попал JSON только что
# завершённого vault_daily_maintenance (а не вчерашнего).
# Защита от коллизий: mkdir атомарна на POSIX — если папка уже есть, другой экземпляр (2-мин цикл) не стартует.
VM_MARKER="$SYNC_DIR/daily_vault_write_maintenance_date.txt"
VM_SKIP_MARKER="$SYNC_DIR/daily_vault_write_maintenance_skip_date.txt"
VM_LOCK="$SYNC_DIR/vault_maintenance.lock"
if [ -d "$VM_LOCK" ]; then
  _vm_lock_age="$(
    (cd "$AGENT_ROOT" && ./scripts/oa-python.sh -c "
from pathlib import Path
from shared.sync.lock import lock_age_seconds
print(lock_age_seconds(Path(r'''${VM_LOCK}''')))
") 2>/dev/null || echo 0
  )"
  if [ "${_vm_lock_age:-0}" -gt "${VAULT_MAINTENANCE_LOCK_STALE_SEC:-21600}" ]; then
    rmdir "$VM_LOCK" 2>/dev/null || true
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ removed stale maintenance lock age=${_vm_lock_age}s" >> "$DEBUG_LOG" 2>/dev/null || true
  fi
  unset _vm_lock_age
fi
# Проверяем нужно ли запускать:
#  — уже выполнено сегодня (VM_MARKER=today) → пропуск
#  — уже помечено как «Python недоступен» (VM_SKIP_MARKER=today) И запуск НЕ интерактивный (LaunchAgent) → пропуск
#    но если [ -t 0 ] (Terminal/Cursor) → игнорируем skip и пробуем (у Terminal есть FDA)
#  — FORCE_VAULT_MAINTENANCE=1 → всегда запускать
_vm_skip_today=0
[ "$(cat "$VM_SKIP_MARKER" 2>/dev/null)" = "$TODAY" ] && ! [ -t 0 ] && _vm_skip_today=1
if cap_step_enabled SYNC_KB_MAINTENANCE && { [ -n "${FORCE_VAULT_MAINTENANCE:-}" ] \
   || { { [ ! -f "$VM_MARKER" ] || [ "$(cat "$VM_MARKER" 2>/dev/null)" != "$TODAY" ]; } \
        && [ "$_vm_skip_today" = "0" ]; }; }; then
  if mkdir "$VM_LOCK" 2>/dev/null; then
    # Чистим lock при выходе (в т.ч. при Ctrl-C), чтобы следующий день не застрял
    trap '_obsidian_sync_cleanup' EXIT INT TERM
    if [ -d "$KNOWLEDGE_BOT" ] && [ -f "$KNOWLEDGE_BOT/tools/vault_daily_maintenance.py" ]; then
      echo "$(sh_msg scripts.obsidian_sync.step_5b_2)" >&2
      echo "$(sh_msgf scripts.obsidian_sync.step_5b_2_log '{"log":"'$PLANNING_BOT/logs/vault_write_maintenance.log'"}')" >&2
      echo "$(sh_msgf scripts.obsidian_sync.step_5b_2_tail '{"log":"'$PLANNING_BOT/logs/vault_write_maintenance.log'"}')" >&2
      export VAULT_PATH="$LOCAL_VAULT"
      export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
      if (cd "$KNOWLEDGE_BOT" && PYTHONUNBUFFERED=1 common_run_python_script "$KN_PYTHON" "$KNOWLEDGE_BOT/tools/vault_daily_maintenance.py" --sync-dir "$SYNC_DIR" --json) >> "$PLANNING_BOT/logs/vault_write_maintenance.log" 2>&1; then
        : # runner.py уже записал VM_MARKER в начале успешного прогона
        # 5b.2b Удаление дублей на VPS — канон тот же, что локально: analyze_vault_duplicates + apply_duplicates_resolution.
        # Иначе следующий шаг 1 (pull 700_) вернёт файлы, которые остались только на сервере (rsync без --delete).
        if [ "${SKIP_SERVER_DUPLICATE_APPLY:-0}" != "1" ]; then
          echo "$(sh_msgf scripts.obsidian_sync.step_5b_2b '{"server":"'$SERVER'","vault":"'$SERVER_VAULT'"}')" >&2
          ssh "${SSH_OPTS[@]}" "$SERVER" \
            VAULT_PATH="$SERVER_VAULT" \
            SERVER_BOTS="$SERVER_BOTS" \
            REMOTE_KNOWLEDGE_BOT="${REMOTE_KNOWLEDGE_BOT:-}" \
            PLANNING_BOT_REMOTE_PYTHON="${PLANNING_BOT_REMOTE_PYTHON:-}" \
            bash -s \
            >>"$PLANNING_BOT/logs/vault_write_maintenance.log" 2>&1 <<'REMOTE_DUP' || { echo "$(sh_msg scripts.obsidian_sync.step_5b_2b_fail)" >&2; _sync_fail "5b.2b-remote-duplicates"; }
set -euo pipefail
export VAULT_PATH SERVER_BOTS REMOTE_KNOWLEDGE_BOT PLANNING_BOT_REMOTE_PYTHON
# shellcheck source=scripts/lib/remote_knowledge_env.sh
source "${SERVER_BOTS:?}/scripts/lib/remote_knowledge_env.sh"
remote_load_agent_env
KB="$(remote_resolve_knowledge_bot)" || {
  echo "knowledge_bot tools missing (REMOTE_KNOWLEDGE_BOT or deploy)" >&2
  exit 1
}
cd "${KB}"
PY="$(remote_resolve_python_for_kb "${KB}")"
export PYTHONPATH="$(remote_agent_pythonpath)"
echo "[5b.2b] KB=${KB} VAULT_PATH=${VAULT_PATH} PY=${PY} VAULT_REL_KNOWLEDGE=${VAULT_REL_KNOWLEDGE:-}"
exec "${PY}" tools/apply_duplicates_resolution.py --apply
REMOTE_DUP

          # 5b.2c: удаление на VPS файлов, чьи оригиналы были удалены локально при reprocess
          # (заметка переехала в другую папку/тип — файл с generic-именем остался только на сервере
          #  и возвращался при следующем rsync --update pull 700_).
          # vault_daily_maintenance (runner.py) пишет .sync/last_maintenance_deleted_paths.json
          # Не хардкодим пути и паттерны: всё берётся из манифеста, созданного reprocess_notes.
          _CLEANUP_MANIFEST="$SYNC_DIR/last_maintenance_deleted_paths.json"
          if [ -f "$_CLEANUP_MANIFEST" ] && [ -n "$KN_PYTHON" ]; then
            _deleted_lines=$(
              "$KN_PYTHON" "${AGENT_ROOT}/knowledge_bot/tools/print_deleted_manifest.py" \
                "$_CLEANUP_MANIFEST" "$LOCAL_VAULT" 2>/dev/null
            )
            if [ -n "$_deleted_lines" ]; then
              echo "$(sh_msgf scripts.obsidian_sync.step_5b_2c '{"count":"'$(echo "$_deleted_lines" | wc -l | tr -d ' ')'","server":"'$SERVER'"}')" >&2
              printf '%s\n' "$_deleted_lines" | ssh "${SSH_OPTS[@]}" "$SERVER" \
                "SVAULT='$SERVER_VAULT';
                 while IFS= read -r rel; do
                   target=\"\$SVAULT/\$rel\"
                   if [ -f \"\$target\" ]; then
                     rm -f \"\$target\" && echo \"[5b.2c] remote deleted: \$rel\" || true
                   fi
                 done
                 exit 0" >> "$PLANNING_BOT/logs/vault_write_maintenance.log" 2>&1 \
                || echo "$(sh_msg scripts.obsidian_sync.step_5b_2c_fail)" >&2
            else
              echo "$(sh_msg scripts.obsidian_sync.step_5b_2c_empty)" >&2
            fi
          fi
        else
          echo "$(sh_msg scripts.obsidian_sync.step_5b_2b_skip)" >&2
        fi
      else
        # Упал — проверяем причину:
        if [ -r "$KNOWLEDGE_BOT/config/vault_maintenance.yaml" ]; then
          # Python работает, но скрипт упал по другой причине — пишем маркер чтобы не повторять весь день
          [ "$(cat "$VM_MARKER" 2>/dev/null)" != "$TODAY" ] && echo "$TODAY" > "$VM_MARKER" 2>/dev/null || true
        else
          # Python не имеет доступа к файлам хранилища (macOS TCC из LaunchAgent)
          # Пишем skip-маркер: LaunchAgent не будет повторять, но Terminal/Cursor — запустит
          echo "$TODAY" > "$VM_SKIP_MARKER" 2>/dev/null || true
          echo "$(sh_msg scripts.obsidian_sync.step_5b_2_tcc)" >&2
        fi
      fi
    fi
    rmdir "$VM_LOCK" 2>/dev/null || true
  else
    echo "$(sh_msgf scripts.obsidian_sync.step_5b_2_lock '{"lock":"'$VM_LOCK'"}')" >&2
  fi
fi
unset _vm_skip_today

# 5b.3 Vault audit (vault_audit_report.py → VAULT_FILE_AUDIT_VAULT) — heavy, 1–3+ min
KN_SKIP_MARKER="$SYNC_DIR/daily_knowledge_vault_audit_skip_date.txt"
_kn_skip_today=0
[ "$(cat "$KN_SKIP_MARKER" 2>/dev/null)" = "$TODAY" ] && ! [ -t 0 ] && _kn_skip_today=1
if cap_step_enabled SYNC_VAULT_AUDIT_HEAVY && { [ -n "${FORCE_SYSTEM_AUDIT:-}" ] \
     || { [ ! -f "$KN_AUDIT_MARKER" ] || [ "$(cat "$KN_AUDIT_MARKER" 2>/dev/null)" != "$TODAY" ]; } \
   } && [ "$_kn_skip_today" = "0" ]; then
  if [ -d "$KNOWLEDGE_BOT" ] && [ -f "$KNOWLEDGE_BOT/tools/vault_audit_report.py" ]; then
    echo "$(sh_msg scripts.obsidian_sync.step_5b_3)" >&2
    export VAULT_PATH="$LOCAL_VAULT"
    export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
    if (cd "$KNOWLEDGE_BOT" && common_run_python_script "$KN_PYTHON" "$KNOWLEDGE_BOT/tools/vault_audit_report.py" --vault "$LOCAL_VAULT" --out "$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_FILE_AUDIT_VAULT}") >> "$PLANNING_BOT/logs/system_audit.log" 2>&1; then
      echo "$TODAY" > "$KN_AUDIT_MARKER"
    else
      if [ -r "$KNOWLEDGE_BOT/config/vault_maintenance.yaml" ]; then
        echo "$TODAY" > "$KN_AUDIT_MARKER"  # упал по другой причине — не повторять
      else
        echo "$TODAY" > "$KN_SKIP_MARKER" 2>/dev/null || true  # TCC-блок — ждём Terminal
        echo "$(sh_msg scripts.obsidian_sync.step_5b_3_tcc)" >&2
      fi
    fi
  fi
fi
unset _kn_skip_today

# После maintenance/audit: render_maintenance_charts пишет в localized path и удаляет legacy,
# но старый flat PNG мог остаться на диске или вернуться с VPS до push-exclude — финальная зачистка.
_kb_cleanup_legacy_charts "5b-kb"

# 5b.post Mac → VPS: аудит-отчёты (после 5b; шаг 2 был до генерации). Pull их не берём (EXCLUDE_300).
_audit_sys="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_FILE_AUDIT_SYSTEM}"
_audit_kb="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_FILE_AUDIT_VAULT}"
for _audit_push in "$_audit_sys" "$_audit_kb"; do
  if [ -f "$_audit_push" ]; then
    "$RSYNC_BIN" "${FLAGS[@]}" --update "$_audit_push" \
      "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_DASHBOARDS}/$(basename "$_audit_push")" 2>/dev/null || true
  fi
done
if [ -f "$_audit_sys" ] || [ -f "$_audit_kb" ]; then
  echo "$(sh_msg scripts.obsidian_sync.step_5b_post)" >&2
fi
unset _audit_sys _audit_kb _audit_push
}
