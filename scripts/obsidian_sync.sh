#!/bin/zsh
AGENT_ROOT="${0:A:h}/.."
export AGENT_ROOT
if [[ -f "$AGENT_ROOT/.env" ]]; then
  set -a
  source "$AGENT_ROOT/.env"
  set +a
fi

# Лог каждого запуска в /tmp (доступно и из launchd) — смотреть: tail -f /tmp/obsidian_sync_debug.log
DEBUG_LOG="/tmp/obsidian_sync_debug.log"
echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ START" >> "$DEBUG_LOG" 2>/dev/null || true
SYNC_OK=1

# Без set -e: ошибка одной папки не останавливает синк остальных
# Путь к vault: из env или по расположению скрипта (чтобы LaunchAgent работал и для ~/Obsidian Vault после миграции без правки plist)
if [[ -n "${0:A}" && -f "${0:A}" ]]; then
  # Если скрипт запущен из /tmp (устаревшая схема с копией), не трогаем vault и выходим.
  if [[ "${0:A}" == "/tmp/obsidian_sync.sh" ]]; then
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ SKIP: запущен из /tmp/obsidian_sync.sh, выхожу без синка" >> "$DEBUG_LOG" 2>/dev/null || true
    exit 0
  fi
  _SDIR="$(dirname "${0:A}")"
  if [[ "$(basename "$_SDIR")" == "scripts" ]]; then
    P="$(cd "$_SDIR/../../.." 2>/dev/null && pwd)"
    AGENT_ROOT="$(cd "$_SDIR/.." && pwd)"
  else
    P="$(cd "$_SDIR/../.." 2>/dev/null && pwd)"
    AGENT_ROOT="$_SDIR"
  fi
  [[ -n "$P" && -d "$P/800_Автоматизация" ]] && LOCAL_VAULT="$P"
fi
LOCAL_VAULT="${LOCAL_VAULT:-${HOME}/Documents/Obsidian Vault}"
# Fallback если Documents/Obsidian Vault не существует
if [[ ! -d "$LOCAL_VAULT" && -d "${HOME}/Obsidian Vault" ]]; then
  LOCAL_VAULT="${HOME}/Obsidian Vault"
fi
AGENT_ROOT="${AGENT_ROOT:-${AGENT_ROOT}}"
export AGENT_ROOT LOCAL_VAULT

# shellcheck source=scripts/lib/capabilities.sh
# Product manifest: optional sync steps (default = all on if exporter missing)
if [[ -f "$AGENT_ROOT/scripts/lib/capabilities.sh" ]]; then
  # shellcheck disable=SC1091
  source "$AGENT_ROOT/scripts/lib/capabilities.sh"
  cap_load_env
  cap_load_vault_paths 2>/dev/null || true
fi
# Defaults when vault_paths exporter missing (match config/vault_paths.yaml.example)
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
: "${VAULT_FILE_AUDIT_SYSTEM:=Аудит_системы_отчет.md}"
: "${VAULT_FILE_AUDIT_VAULT:=Аудит_хранилища_отчет.md}"
# Fallback: no manifest exporter → run full sync (backward compatible)
if ! typeset -f cap_step_enabled >/dev/null 2>&1; then
  cap_step_enabled() { return 0; }
fi

VAULT_TEST="${AGENT_ROOT}/scripts/obsidian_sync.sh"
if ! test -r "$VAULT_TEST" 2>/dev/null || ! head -c1 "$VAULT_TEST" >/dev/null 2>/dev/null; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ SKIP: нет доступа к vault (запуск без FDA), выхожу" >> "$DEBUG_LOG" 2>/dev/null || true
  exit 0
fi

# Когда LaunchAgent не может писать в vault (Documents), маркеры и логи пишем в домашнюю папку
SYNC_DIR="${SYNC_STATE_DIR:-$LOCAL_VAULT/.sync}"
mkdir -p "$SYNC_DIR" 2>/dev/null || true
# Проверка именно перезаписи (launchd может разрешать append, но не overwrite в Documents)
if ! ( echo 1 > "$SYNC_DIR/.write_test" 2>/dev/null ); then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ FALLBACK: нет доступа к vault/.sync" >> "$DEBUG_LOG" 2>/dev/null || true
  SYNC_DIR="$HOME/.sync/obsidian"
  SYNC_STATE_DIR="$SYNC_DIR"
  mkdir -p "$SYNC_DIR"
fi
rm -f "$SYNC_DIR/.write_test" 2>/dev/null
# LaunchAgent без FDA не может писать в ~/Documents — не крутим rsync впустую
if [[ "$SYNC_DIR" == "$HOME/.sync/obsidian"* ]] && [[ "$LOCAL_VAULT" == *"/Documents/"* ]]; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ SKIP: нет доступа к Documents, синк отключён (нужен cron или FDA)" >> "$DEBUG_LOG" 2>/dev/null || true
  exit 0
fi
# Каждый запуск (cron или вручную) — одна строка в лог; по нему видно, срабатывает ли cron каждые 5 мин (см. plist StartInterval)
echo "$(date '+%Y-%m-%dT%H:%M:%S')" >> "$SYNC_DIR/cron_runs.log" 2>/dev/null || true

# Изоляция от pyenv: venv/bin/python может быть симлинком на $HOME/.pyenv/versions/.../bin/python3,
# а у pyenv-питона нет TCC FDA на ~/Documents → site.py падает на чтении venv/pyvenv.cfg и засоряет system_audit.log.
unset PYENV_VERSION PYENV_VIRTUAL_ENV PYENV_SHELL
if [[ ":$PATH:" == *":${HOME}/.pyenv/"* ]]; then
  PATH="$(printf '%s' "$PATH" | awk -v RS=':' -v ORS=':' 'NF && $0 !~ /\.pyenv\/(shims|versions)/' | sed 's/:$//')"
  export PATH
fi
SERVER="${SERVER:-}"
SERVER_VAULT="${SERVER_VAULT:-/root/obsidian-vault}"
SERVER_BOTS="${SERVER_BOTS:-/root/bots}"
if [ -z "$SERVER" ]; then
  echo "obsidian_sync: задайте SERVER в .env (SSH host)" >&2
  exit 1
fi
# shellcheck source=scripts/lib/vault_knowledge_dir.sh
source "${AGENT_ROOT}/scripts/lib/vault_knowledge_dir.sh"
KNOWLEDGE_SUBDIR="$(vault_knowledge_subdir)"
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

# LaunchAgent не видит SSH-агент; ключ из Keychain нужен явно. Иначе rsync/ssh падают с Permission denied, маркер last_sync_ok всё равно пишется.
export RSYNC_RSH="${RSYNC_RSH:-ssh -o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3}"
SSH_OPTS=(-o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)

# Исключения при подтягивании 300_Дашборды. Логи только в Логи/; корневой 📊 Логи_Действий_*.md не тянуть и не пушить (устаревшая структура).
# Аудит_*.md — только Mac (obsidian_sync 5b.1/5b.3); на VPS не генерируются, pull затирал свежий локальный отчёт.
EXCLUDE_300=(
  --exclude="${VAULT_DASH_CHARTS}/"
  --exclude='weekly_sprints.json'
  --exclude='Completions_By_Category_Chart.md'
  --exclude='data/'
  --exclude='📅 Рутины/'
  --exclude='📊 Рутины_Статистика.md'
  --exclude='/📊 Логи_Действий_*.md'
  --exclude="${VAULT_FILE_AUDIT_SYSTEM}"
  --exclude="${VAULT_FILE_AUDIT_VAULT}"
  --exclude="${VAULT_DASH_DATA}/finance.db"
  --exclude="${VAULT_DASH_DATA}/finance.db-*"
  # Mac-authoritative: IMAP/Shortcuts пишут здесь; pull с VPS возвращал мусор после локального cleanup
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_ACTIONS_IPHONE}/"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_ACTIONS_MAC}/"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_IPHONE_TODAY}"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_IPHONE_WEEK}"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_CONTEXT_TODAY}"
  --exclude="${VAULT_DASH_DATA}/${VAULT_PATH_CONTEXT_WEEK}"
)
# 1. Сервер → Локальный. --update: не перезаписывать локальные, если они новее (сохраняем правки в Obsidian). Если новее сервер (задача через бота / заметки knowledge bot) — подтягиваем.
if cap_module_enabled PLANNING; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_GOALS}/" "$LOCAL_VAULT/${VAULT_FOLDER_GOALS}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_ROUTINES}/" "$LOCAL_VAULT/${VAULT_FOLDER_ROUTINES}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_HANDWRITTEN}/" "$LOCAL_VAULT/${VAULT_FOLDER_HANDWRITTEN}/" || SYNC_OK=0
fi
if cap_module_enabled FINANCE || cap_module_enabled PLANNING || cap_module_enabled KNOWLEDGE; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${EXCLUDE_300[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_DASHBOARDS}/" "$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/" || SYNC_OK=0
fi
if cap_module_enabled KNOWLEDGE; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/${KNOWLEDGE_SUBDIR}/" "$LOCAL_VAULT/${KNOWLEDGE_SUBDIR}/" || SYNC_OK=0
fi
# Важно: rsync с --update НЕ удаляет на удалённой стороне файлы, которые уже убраны локально.
# Поэтому после шага 5b.2 (удаление дублей в Export на Mac) выполняется 5b.2b — тот же apply_duplicates на сервере.

# 1a. IPhone/Mac: DD.MM.YYYY → YYYY-MM-DD (сортировка); манифест → 1a-remote до push
_PLANNING_BOT="${AGENT_ROOT}/planning_bot"
if cap_module_enabled PLANNING && cap_step_enabled SYNC_MAC_IPHONE && [ -d "$_PLANNING_BOT" ] && [ -f "$_PLANNING_BOT/tools/rename_action_snapshots.py" ]; then
  touch "$_PLANNING_BOT/logs/action_snapshot_rename.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT" SYNC_STATE_DIR="$SYNC_DIR"
  export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$_PLANNING_BOT" && PYTHONUNBUFFERED=1 python3 -u tools/rename_action_snapshots.py --target both --apply --vault "$LOCAL_VAULT" --sync-dir "$SYNC_DIR") \
    >> "$_PLANNING_BOT/logs/action_snapshot_rename.log" 2>&1 || true
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
      echo "obsidian_sync: шаг 1a-remote — удаление старых имён IPhone/Mac на VPS…" >&2
      printf '%s\n' "$_action_unlink" | ssh "${SSH_OPTS[@]}" "$SERVER" \
        "SVAULT='$SERVER_VAULT'
         while IFS= read -r rel; do
           target=\"\$SVAULT/\$rel\"
           if [ -f \"\$target\" ]; then
             rm -f \"\$target\" && echo \"[1a-remote] deleted: \$rel\" || true
           fi
         done" >> "$_PLANNING_BOT/logs/action_snapshot_rename.log" 2>&1 \
        || echo "⚠️ obsidian_sync: 1a-remote завершился с ошибкой" >&2
    fi
  fi
fi
unset _PLANNING_BOT _ACTION_RENAME_MANIFEST _action_unlink

# 1b. Mac-контекст локально: TTL cleanup + context_*.json ДО push (не слать на VPS снапшоты старше TTL)
_PLANNING_BOT="${AGENT_ROOT}/planning_bot"
if cap_module_enabled PLANNING && cap_step_enabled SYNC_MAC_IPHONE && [ -d "$_PLANNING_BOT" ] && [ -f "$_PLANNING_BOT/tools/context_sync.py" ]; then
  touch "$_PLANNING_BOT/logs/context_sync.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT"
  export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$_PLANNING_BOT" && PYTHONUNBUFFERED=1 python3 -u tools/context_sync.py) >> "$_PLANNING_BOT/logs/context_sync.log" 2>&1 || true
fi

# 1c. iPhone: удалить невалидные IPhone/*.txt + пересобрать iphone_*.json ДО push (канон Mac → VPS)
if cap_module_enabled PLANNING && cap_step_enabled SYNC_MAC_IPHONE && [ -d "$_PLANNING_BOT" ] && [ -f "$_PLANNING_BOT/tools/iphone_context_sync.py" ]; then
  touch "$_PLANNING_BOT/logs/iphone_context_sync.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT"
  export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$_PLANNING_BOT" && PYTHONUNBUFFERED=1 python3 -u tools/iphone_context_sync.py) >> "$_PLANNING_BOT/logs/iphone_context_sync.log" 2>&1 || true
fi
unset _PLANNING_BOT

# 2. Локальный → Сервер (отправить изменения, не затирать более новые на сервере)
# При push 300_Дашборды не отправляем сервер-авторитетные файлы (бот/cron/maintenance пишут их на сервере).
# Плюс не пушим корневой 📊 Логи_Действий_*.md — канон только 300_Дашборды/Логи/; иначе файл из корня (устаревшая структура) снова уезжает на сервер и «возвращается».
# Не пушить устаревший график (выпилен из build_finance_dashboard; иначе вернётся с мака на сервер)
PUSH_EXCLUDE_300=(
  --exclude='kanban_state.json'
  --exclude='.kanban_monitor_state.json'
  --exclude='Логи/'
  --exclude='goals_task_mapping.json'
  --exclude='/📊 Логи_Действий_*.md'
  --exclude='Графики/Финансы/Доли_по_дням_категории_обычные.png'
  --exclude='Данные/finance.db'
  --exclude='Данные/finance.db-*'
)
if cap_module_enabled PLANNING; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_GOALS}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_GOALS}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_ROUTINES}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_ROUTINES}/" || SYNC_OK=0
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_HANDWRITTEN}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_HANDWRITTEN}/" || SYNC_OK=0
fi
if cap_module_enabled FINANCE || cap_module_enabled PLANNING || cap_module_enabled KNOWLEDGE; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" "${PUSH_EXCLUDE_300[@]}" --update "$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/" "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_DASHBOARDS}/" || SYNC_OK=0
fi
if cap_module_enabled KNOWLEDGE; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_DELETE_FLAGS[@]}" --update "$LOCAL_VAULT/${KNOWLEDGE_SUBDIR}/" "$SERVER:$SERVER_VAULT/${KNOWLEDGE_SUBDIR}/" || SYNC_OK=0
fi

# 2b. На VPS: тот же cleanup/JSON для IPhone (старый мусор мог остаться только на сервере)
if cap_module_enabled PLANNING && cap_step_enabled SYNC_MAC_IPHONE && [ -d "${AGENT_ROOT}/planning_bot" ] && [ -f "${AGENT_ROOT}/planning_bot/tools/iphone_context_sync.py" ]; then
  echo "obsidian_sync: шаг 2b — iphone_context_sync на сервере…" >&2
  ssh "${SSH_OPTS[@]}" "$SERVER" "cd '${SERVER_BOTS}/planning_bot' && VAULT_PATH='${SERVER_VAULT}' PYTHONPATH='${SERVER_BOTS}' ./.venv/bin/python -u tools/iphone_context_sync.py" \
    >> "${AGENT_ROOT}/planning_bot/logs/iphone_context_sync.log" 2>&1 || SYNC_OK=0
fi

# 3. Обслуживание vault на сервере (VAULT_PATH=$SERVER_VAULT). Kanban — только cron на VPS.
if cap_module_enabled PLANNING; then
  echo "obsidian_sync: шаг 3 — SSH: vault_maintenance на сервере (лог: planning_bot/logs/maintenance.log)…" >&2
  ssh "${SSH_OPTS[@]}" "$SERVER" "cd ${SERVER_BOTS}/planning_bot && ./scripts/run_maintenance_from_sync.sh >> logs/maintenance.log 2>&1" || { echo "⚠️ Maintenance на сервере завершился с ошибкой (см. ssh \$SERVER 'tail -50 ${SERVER_BOTS}/planning_bot/logs/maintenance.log')" >&2; SYNC_OK=0; }
fi

# 4. Подтянуть обновлённые файлы с сервера после maintenance.
# 100_: ignore-times — канон сортировки с VPS. 300_: --update + EXCLUDE_300 (в т.ч. Аудит_*.md) — не затирать Mac-only отчёты.
echo "obsidian_sync: шаг 4 — rsync сервер→локаль после maintenance…" >&2
if cap_module_enabled PLANNING; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --ignore-times "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_TASKS}/" "$LOCAL_VAULT/${VAULT_FOLDER_TASKS}/" || SYNC_OK=0
fi
if cap_module_enabled FINANCE || cap_module_enabled PLANNING || cap_module_enabled KNOWLEDGE; then
  "$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${EXCLUDE_300[@]}" --update "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_DASHBOARDS}/" "$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/" || SYNC_OK=0
fi
# 700 уже подтянут в шаге 1; при необходимости можно добавить сюда с --ignore-times

TODAY=$(date +%Y-%m-%d)
NOW_ISO=$(date +%Y-%m-%dT%H:%M:%S)
# Частая опечатка: FORCE_CHART=1 → FORCE_CHARTS=1
if [ -n "${FORCE_CHART:-}" ] && [ -z "${FORCE_CHARTS:-}" ]; then
  export FORCE_CHARTS=1
fi

# Python для графиков: LaunchAgent часто не читает planning_bot/venv/pyvenv.cfg (TCC/FDA).
# Сначала homebrew из LaunchAgent; venv — если реально импортирует yaml.
_pb_venv="$AGENT_ROOT/planning_bot/venv"
_pb_sp="$(ls -d "$_pb_venv/lib/python"*/site-packages 2>/dev/null | head -1)"
_chart_py_ok() { "$1" -c "import yaml" 2>/dev/null; }
CHART_PYTHON=""
if ! [ -t 0 ] && [ -x "/opt/homebrew/bin/python3" ] && _chart_py_ok "/opt/homebrew/bin/python3"; then
  CHART_PYTHON="/opt/homebrew/bin/python3"
elif [ -x "$_pb_venv/bin/python" ] && _chart_py_ok "$_pb_venv/bin/python"; then
  CHART_PYTHON="$_pb_venv/bin/python"
elif [ -x "/opt/homebrew/bin/python3" ] && _chart_py_ok "/opt/homebrew/bin/python3"; then
  CHART_PYTHON="/opt/homebrew/bin/python3"
elif command -v python3 >/dev/null 2>&1 && _chart_py_ok python3; then
  CHART_PYTHON=python3
fi
if [ -n "$_pb_sp" ]; then
  CHART_PYTHONPATH="${AGENT_ROOT}:${_pb_sp}"
else
  CHART_PYTHONPATH="${AGENT_ROOT}"
fi
unset _pb_venv _pb_sp _chart_py_ok

# 5. Графики дашборда по action-логам: раз в день + повтор, если лог месяца новее PNG (конец дня).
# Иначе прогон в 00:03 ставит маркер «сегодня», а события дня в графики не попадают до следующей полуночи.
# FORCE_CHARTS=1 ~/bin/obsidian_sync.sh
MARKER="$SYNC_DIR/daily_charts_date.txt"
LOGS_DIR="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_LOGS}"
ACTION_LOG_PREFIX="📊 Логи_Действий_"
_CHART_DIR="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_CHARTS}"
_CUR_LOG="$LOGS_DIR/${ACTION_LOG_PREFIX}$(date +%Y-%m).md"
_chart_png_mtime_max() {
  local d="$1" max=0 m f
  for f in \
    "$d/Активность_за_день.png" \
    "$d/Завершено_по_категориям_дни.png" \
    "$d/Открыто_по_категориям_дни.png" \
    "$d/Дедлайны_горизонт.png"; do
    [ -f "$f" ] || continue
    m=$(stat -f '%m' "$f" 2>/dev/null || echo 0)
    [ "$m" -gt "$max" ] && max=$m
  done
  echo "$max"
}
HAS_LOGS=
[ -d "$LOGS_DIR" ] && [ "$(find "$LOGS_DIR" -maxdepth 1 -name '*Логи_Действий_*.md' 2>/dev/null | wc -l)" -gt 0 ] && HAS_LOGS=1
_SHOULD_CHARTS=0
if [ -n "${FORCE_CHARTS:-}" ]; then
  _SHOULD_CHARTS=1
elif [ ! -f "$MARKER" ] || [ "$(cat "$MARKER" 2>/dev/null)" != "$TODAY" ]; then
  _SHOULD_CHARTS=1
elif [ -f "$_CUR_LOG" ] && [ "$(_chart_png_mtime_max "$_CHART_DIR")" = "0" ]; then
  _SHOULD_CHARTS=1
elif [ -f "$_CUR_LOG" ]; then
  _log_m=$(stat -f '%m' "$_CUR_LOG" 2>/dev/null || echo 0)
  _png_m=$(_chart_png_mtime_max "$_CHART_DIR")
  [ "$_log_m" -gt "$_png_m" ] && _SHOULD_CHARTS=1
fi
if ! cap_step_enabled SYNC_PLANNING_CHARTS; then
  _SHOULD_CHARTS=0
fi
if [ "$_SHOULD_CHARTS" = "1" ]; then
  PLANNING_BOT="$AGENT_ROOT/planning_bot"
  if [ -n "$HAS_LOGS" ] && [ -n "$CHART_PYTHON" ] && [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_daily_task_activity_chart.py" ]; then
    echo "obsidian_sync: шаг 5 — графики дашборда ($CHART_PYTHON ×4, лог: $PLANNING_BOT/logs/charts.log)…" >&2
    export LOCAL_VAULT
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
    if cd "$PLANNING_BOT" && "$CHART_PYTHON" scripts/build_daily_task_activity_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1 \
       && "$CHART_PYTHON" scripts/build_daily_completions_by_category_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1 \
       && "$CHART_PYTHON" scripts/build_open_pipeline_by_category_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1 \
       && "$CHART_PYTHON" scripts/build_deadline_horizon_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1; then
      echo "$TODAY" > "$MARKER"
    else
      echo "⚠️ obsidian_sync: шаг 5 — сборка графиков не удалась (см. planning_bot/logs/charts.log)" >&2
      SYNC_OK=0
    fi
  fi
fi
unset _SHOULD_CHARTS _CHART_DIR _CUR_LOG _log_m _png_m _chart_png_mtime_max ACTION_LOG_PREFIX

# 5c. PNG встреч (calendar_sync) — раз в день + если JSON календаря новее PNG.
CAL_MARKER="$SYNC_DIR/calendar_charts_date.txt"
_CAL_JSON="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_DATA}/Календарь.json"
_CAL_PNG="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_CHARTS}/Встречи_нагрузка_недели.png"
PLANNING_BOT="${PLANNING_BOT:-$AGENT_ROOT/planning_bot}"
_SHOULD_CAL=0
if [ -n "${FORCE_CHARTS:-}" ]; then
  _SHOULD_CAL=1
elif [ ! -f "$CAL_MARKER" ] || [ "$(cat "$CAL_MARKER" 2>/dev/null)" != "$TODAY" ]; then
  _SHOULD_CAL=1
elif [ -f "$_CAL_JSON" ] && [ -f "$_CAL_PNG" ]; then
  _cal_j=$(stat -f '%m' "$_CAL_JSON" 2>/dev/null || echo 0)
  _cal_p=$(stat -f '%m' "$_CAL_PNG" 2>/dev/null || echo 0)
  [ "$_cal_j" -gt "$_cal_p" ] && _SHOULD_CAL=1
fi
if ! cap_step_enabled SYNC_CALENDAR; then
  _SHOULD_CAL=0
fi
if [ "$_SHOULD_CAL" = "1" ]; then
  if [ -n "$CHART_PYTHON" ] && [ -d "$PLANNING_BOT" ]; then
    echo "obsidian_sync: шаг 5c — calendar_sync ($CHART_PYTHON, лог: logs/charts.log)…" >&2
    export LOCAL_VAULT
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
    if cd "$PLANNING_BOT" && "$CHART_PYTHON" -m planning_bot.tools.calendar_sync >> logs/charts.log 2>&1; then
      echo "$TODAY" > "$CAL_MARKER"
    else
      echo "⚠️ obsidian_sync: шаг 5c — calendar_sync failed (см. charts.log)" >&2
      SYNC_OK=0
    fi
  fi
fi
unset _SHOULD_CAL _CAL_JSON _CAL_PNG _cal_j _cal_p

# 5d. График КБЖУ: перенесён сразу после 5b.4b (iphone_context_sync) — иначе PNG строится по
# вчерашнему iphone_week.json и день с ручным .txt в IPhone/ даёт пустой/битый столбец.
# (см. шаг 5d ниже, после iphone_context_sync)

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
_kn_sp="$(ls -d "$_kn_venv/lib/python"*/site-packages 2>/dev/null | head -1)"
if [ -n "$_kn_sp" ]; then
  export PYTHONPATH="${KNOWLEDGE_BOT}:${AGENT_ROOT}:${_kn_sp}${PYTHONPATH:+:$PYTHONPATH}"
else
  export PYTHONPATH="${KNOWLEDGE_BOT}:${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
fi
if [ -x "/opt/homebrew/bin/python3" ]; then
  KN_PYTHON="/opt/homebrew/bin/python3"
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
  "$PLANNING_BOT/logs/vault_write_maintenance.log" \
  "$PLANNING_BOT/logs/iphone_mail_sync.log" \
  "$PLANNING_BOT/logs/iphone_context_sync.log" \
  "$PLANNING_BOT/logs/context_sync.log" \
  2>/dev/null || true
# Ротация логов: обрезаем если выросли слишком большими (бывает при циклических сбоях).
_trim_log() {
  local f="$1" max="${2:-1500}" keep="${3:-800}"
  [ -f "$f" ] || return 0
  local n; n=$(wc -l < "$f" 2>/dev/null || echo 0)
  if [ "$n" -gt "$max" ]; then
    local tmp; tmp=$(mktemp)
    tail -n "$keep" "$f" > "$tmp" && mv "$tmp" "$f" || rm -f "$tmp"
  fi
}
# maintenance JSON в логе может быть длинным (stdout_tail шагов) — запас по строкам больше, чем у прочих логов
_trim_log "$PLANNING_BOT/logs/vault_write_maintenance.log" 5000 3500
_trim_log "$PLANNING_BOT/logs/system_audit.log"
_trim_log "$PLANNING_BOT/logs/charts.log" 500 300
# iphone-логи многословные (JSON писем + ASR/Vision), но скачут — отдельные пороги
_trim_log "$PLANNING_BOT/logs/iphone_mail_sync.log" 5000 3000
_trim_log "$PLANNING_BOT/logs/iphone_context_sync.log" 5000 3000

# 5b.1 Аудит planning/sync (лёгкий, секунды)
if cap_module_enabled PLANNING && { [ -n "${FORCE_SYSTEM_AUDIT:-}" ] || [ ! -f "$SYS_AUDIT_MARKER" ] || [ "$(cat "$SYS_AUDIT_MARKER" 2>/dev/null)" != "$TODAY" ]; }; then
  if [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_system_audit_report.py" ]; then
    echo "obsidian_sync: шаг 5b.1 — лёгкий системный аудит (tail -f logs/system_audit.log)…" >&2
    export LOCAL_VAULT
    export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
    if cd "$PLANNING_BOT" && python3 scripts/build_system_audit_report.py --vault "$LOCAL_VAULT" >> logs/system_audit.log 2>&1; then
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
    trap 'rmdir "$VM_LOCK" 2>/dev/null || true' EXIT INT TERM
    if [ -d "$KNOWLEDGE_BOT" ] && [ -f "$KNOWLEDGE_BOT/tools/vault_daily_maintenance.py" ]; then
      echo "obsidian_sync: шаг 5b.2 — vault_daily_maintenance (wikilinks+retag+reprocess по YAML; 5–60+ мин)…" >&2
      echo "  лог: $PLANNING_BOT/logs/vault_write_maintenance.log" >&2
      echo "  смотреть: tail -f \"$PLANNING_BOT/logs/vault_write_maintenance.log\"" >&2
      export VAULT_PATH="$LOCAL_VAULT"
      export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
      if (cd "$KNOWLEDGE_BOT" && PYTHONUNBUFFERED=1 "$KN_PYTHON" -u tools/vault_daily_maintenance.py --sync-dir "$SYNC_DIR" --json) >> "$PLANNING_BOT/logs/vault_write_maintenance.log" 2>&1; then
        : # runner.py уже записал VM_MARKER в начале успешного прогона
        # 5b.2b Удаление дублей на VPS — канон тот же, что локально: analyze_vault_duplicates + apply_duplicates_resolution.
        # Иначе следующий шаг 1 (pull 700_) вернёт файлы, которые остались только на сервере (rsync без --delete).
        if [ "${SKIP_SERVER_DUPLICATE_APPLY:-0}" != "1" ]; then
          echo "obsidian_sync: шаг 5b.2b — apply_duplicates на сервере ($SERVER $SERVER_VAULT)…" >&2
          # shellcheck disable=SC2090
          ssh "${SSH_OPTS[@]}" "$SERVER" env VAULT_PATH="$SERVER_VAULT" SERVER_BOTS="$SERVER_BOTS" REMOTE_KNOWLEDGE_BOT="${REMOTE_KNOWLEDGE_BOT:-}" PLANNING_BOT_REMOTE_PYTHON="${PLANNING_BOT_REMOTE_PYTHON:-}" bash -s \
            >>"$PLANNING_BOT/logs/vault_write_maintenance.log" 2>&1 <<'REMOTE_DUP' || { echo "⚠️ obsidian_sync: 5b.2b завершился с ошибкой — см. vault_write_maintenance.log" >&2; SYNC_OK=0; }
set -euo pipefail
export VAULT_PATH
export SERVER_BOTS="${SERVER_BOTS:-/root/bots}"
KB=""
for d in "${REMOTE_KNOWLEDGE_BOT:-}" "${VAULT_PATH}/800_Автоматизация/Agent/knowledge_bot" "${SERVER_BOTS}/knowledge_bot"; do
  [ -z "${d}" ] && continue
  [ -f "${d}/tools/apply_duplicates_resolution.py" ] || continue
  KB="${d}"
  break
done
if [ -z "${KB}" ]; then
  echo "⚠️ 5b.2b: нет knowledge_bot с tools/apply_duplicates_resolution.py — задай REMOTE_KNOWLEDGE_BOT или разверни knowledge_bot на сервере" >&2
  exit 1
fi
cd "${KB}"
# На VPS у knowledge_bot часто нет своего venv; системный python3 может быть без PyYAML.
# Fallback: venv planning_bot (тот же хост, те же зависимости для YAML/агента).
_PLANNING_PY="${PLANNING_BOT_REMOTE_PYTHON:-${SERVER_BOTS}/planning_bot/venv/bin/python}"
if [ -x .venv/bin/python ]; then PY=".venv/bin/python"
elif [ -x venv/bin/python ]; then PY="venv/bin/python"
elif [ -x "${_PLANNING_PY}" ]; then PY="${_PLANNING_PY}"
else PY="python3"
fi
export VAULT_PATH
echo "[5b.2b] KB=${KB} VAULT_PATH=${VAULT_PATH} PY=${PY}"
# apply_duplicates_resolution.py сам кладёт Agent в sys.path (parent ×3 от tools/)
exec "${PY}" tools/apply_duplicates_resolution.py --apply
REMOTE_DUP

          # 5b.2c: удаление на VPS файлов, чьи оригиналы были удалены локально при reprocess
          # (заметка переехала в другую папку/тип — файл с generic-именем остался только на сервере
          #  и возвращался при следующем rsync --update pull 700_).
          # runner.py пишет манифест .sync/last_maintenance_deleted_paths.json после каждого прогона.
          # Не хардкодим пути и паттерны: всё берётся из манифеста, созданного reprocess_notes.
          _CLEANUP_MANIFEST="$SYNC_DIR/last_maintenance_deleted_paths.json"
          if [ -f "$_CLEANUP_MANIFEST" ] && [ -n "$KN_PYTHON" ]; then
            _deleted_lines=$(
              "$KN_PYTHON" - "$_CLEANUP_MANIFEST" "$LOCAL_VAULT" 2>/dev/null <<'PY_CLEANUP'
import json, sys, pathlib
manifest_path, vault_str = sys.argv[1], sys.argv[2]
vault = pathlib.Path(vault_str).resolve()
data = json.load(open(manifest_path, encoding="utf-8"))
for p in (data.get("deleted") or []):
    if not p or ".." in p:
        continue
    try:
        # Убеждаемся, что путь относительный и не выходит за пределы vault
        resolved = (vault / p).resolve()
        resolved.relative_to(vault)
        print(p)
    except (ValueError, Exception):
        pass
PY_CLEANUP
            )
            if [ -n "$_deleted_lines" ]; then
              echo "obsidian_sync: шаг 5b.2c — remote cleanup: $(echo "$_deleted_lines" | wc -l | tr -d ' ') файлов на $SERVER…" >&2
              printf '%s\n' "$_deleted_lines" | ssh "${SSH_OPTS[@]}" "$SERVER" \
                "SVAULT='$SERVER_VAULT'
                 while IFS= read -r rel; do
                   target=\"\$SVAULT/\$rel\"
                   if [ -f \"\$target\" ]; then
                     rm -f \"\$target\" && echo \"[5b.2c] remote deleted: \$rel\" || true
                   fi
                 done" >> "$PLANNING_BOT/logs/vault_write_maintenance.log" 2>&1 \
                || echo "⚠️ obsidian_sync: 5b.2c завершился с ошибкой — см. vault_write_maintenance.log" >&2
            else
              echo "obsidian_sync: шаг 5b.2c — нет файлов для remote cleanup" >&2
            fi
          fi
        else
          echo "obsidian_sync: шаг 5b.2b — пропуск (SKIP_SERVER_DUPLICATE_APPLY=1)" >&2
        fi
      else
        # Упал — проверяем причину:
        if "$KN_PYTHON" -c "open('$KNOWLEDGE_BOT/config/vault_maintenance.yaml').close()" >/dev/null 2>&1; then
          # Python работает, но скрипт упал по другой причине — пишем маркер чтобы не повторять весь день
          [ "$(cat "$VM_MARKER" 2>/dev/null)" != "$TODAY" ] && echo "$TODAY" > "$VM_MARKER" 2>/dev/null || true
        else
          # Python не имеет доступа к файлам хранилища (macOS TCC из LaunchAgent)
          # Пишем skip-маркер: LaunchAgent не будет повторять, но Terminal/Cursor — запустит
          echo "$TODAY" > "$VM_SKIP_MARKER" 2>/dev/null || true
          echo "obsidian_sync: 5b.2 — Python без доступа к файлам vault (macOS TCC). Запустите obsidian_sync.sh из Terminal для обслуживания." >&2
        fi
      fi
    fi
    rmdir "$VM_LOCK" 2>/dev/null || true
    trap - EXIT INT TERM
  else
    echo "obsidian_sync: шаг 5b.2 — пропуск, другой экземпляр уже работает (lock: $VM_LOCK)" >&2
  fi
fi
unset _vm_skip_today

# 5b.3 Аудит 700_База_Данных (analyze_vault_tags + дубли + секция maintenance в логе → Аудит_хранилища_отчет.md) — тяжёлый, 1–3+ мин
KN_SKIP_MARKER="$SYNC_DIR/daily_knowledge_vault_audit_skip_date.txt"
_kn_skip_today=0
[ "$(cat "$KN_SKIP_MARKER" 2>/dev/null)" = "$TODAY" ] && ! [ -t 0 ] && _kn_skip_today=1
if cap_step_enabled SYNC_VAULT_AUDIT_HEAVY && { [ -n "${FORCE_SYSTEM_AUDIT:-}" ] \
     || { [ ! -f "$KN_AUDIT_MARKER" ] || [ "$(cat "$KN_AUDIT_MARKER" 2>/dev/null)" != "$TODAY" ]; } \
   } && [ "$_kn_skip_today" = "0" ]; then
  if [ -d "$KNOWLEDGE_BOT" ] && [ -f "$KNOWLEDGE_BOT/tools/analyze_vault_report.py" ]; then
    echo "obsidian_sync: шаг 5b.3 — тяжёлый аудит 700_ (часто 1–5+ мин; tail -f logs/system_audit.log)…" >&2
    export VAULT_PATH="$LOCAL_VAULT"
    export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
    if (cd "$KNOWLEDGE_BOT" && "$KN_PYTHON" tools/analyze_vault_report.py --vault "$LOCAL_VAULT" --out "$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_FILE_AUDIT_VAULT}") >> "$PLANNING_BOT/logs/system_audit.log" 2>&1; then
      echo "$TODAY" > "$KN_AUDIT_MARKER"
    else
      if "$KN_PYTHON" -c "open('$KNOWLEDGE_BOT/config/vault_maintenance.yaml').close()" >/dev/null 2>&1; then
        echo "$TODAY" > "$KN_AUDIT_MARKER"  # упал по другой причине — не повторять
      else
        echo "$TODAY" > "$KN_SKIP_MARKER" 2>/dev/null || true  # TCC-блок — ждём Terminal
        echo "obsidian_sync: 5b.3 — Python без доступа (macOS TCC). Аудит запустится при ручном вызове из Terminal." >&2
      fi
    fi
  fi
fi
unset _kn_skip_today

# 5b.post Mac → VPS: аудит-отчёты (после 5b; шаг 2 был до генерации). Pull их не берём (EXCLUDE_300).
_audit_sys="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/Аудит_системы_отчет.md"
_audit_kb="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_FILE_AUDIT_VAULT}"
for _audit_push in "$_audit_sys" "$_audit_kb"; do
  if [ -f "$_audit_push" ]; then
    "$RSYNC_BIN" "${FLAGS[@]}" --update "$_audit_push" \
      "$SERVER:$SERVER_VAULT/${VAULT_FOLDER_DASHBOARDS}/$(basename "$_audit_push")" 2>/dev/null || true
  fi
done
if [ -f "$_audit_sys" ] || [ -f "$_audit_kb" ]; then
  echo "obsidian_sync: шаг 5b.post — аудит-отчёты на сервер (если есть локально)" >&2
fi
unset _audit_sys _audit_kb _audit_push

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
  echo "obsidian_sync: шаг 5b.4 — iPhone mail sync (Gmail IMAP → IPhone/*.txt)…" >&2
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
      cd "$PLANNING_BOT" && PYTHONUNBUFFERED=1 python3 -u tools/iphone_mail_sync.py
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
    echo "obsidian_sync: шаг 5b.4 — пропуск, GMAIL_IMAP_USER/GMAIL_IMAP_APP_PASSWORD не заданы (добавь в $AGENT_ROOT/.env; см. scripts/check_env.sh mac-sync)" >&2
  fi
fi

# 5b.4b Каждый синк: iphone_today.json / iphone_week.json из IPhone/*.txt (без IMAP, быстро)
if cap_step_enabled SYNC_MAC_IPHONE && [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/tools/iphone_context_sync.py" ]; then
  touch "$PLANNING_BOT/logs/iphone_context_sync.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT"
  export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$PLANNING_BOT" && PYTHONUNBUFFERED=1 python3 -u tools/iphone_context_sync.py) >> "$PLANNING_BOT/logs/iphone_context_sync.log" 2>&1 || true
fi

# 5d. График КБЖУ — после 5b.4 + 5b.4b. Раз в сутки по маркеру, НО также если появился новый IPhone/*.txt
# позже последнего PNG (иначе ночной прогон в 00:04 блокирует день до вечернего снапшота).
NUTR_MARKER="$SYNC_DIR/daily_iphone_nutrition_date.txt"
_IPHONE_CTX_DIR="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_DATA}/Действия/IPhone"
_NUTR_PNG="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_CHARTS}/Питание_КБЖУ_по_дням.png"
_SHOULD_NUTR=0
if [ -n "${FORCE_CHARTS:-}" ]; then
  _SHOULD_NUTR=1
elif [ ! -f "$NUTR_MARKER" ] || [ "$(cat "$NUTR_MARKER" 2>/dev/null)" != "$TODAY" ]; then
  _SHOULD_NUTR=1
elif [ -d "$_IPHONE_CTX_DIR" ] && [ -f "$_NUTR_PNG" ]; then
  _latest_iph=$(
    find "$_IPHONE_CTX_DIR" -maxdepth 1 -type f -name '*.txt' ! -iname '*copy*' -print0 2>/dev/null \
      | xargs -0 stat -f '%m' 2>/dev/null | sort -rn | head -1
  )
  _png_m=$(stat -f '%m' "$_NUTR_PNG" 2>/dev/null || echo 0)
  if [ -n "$_latest_iph" ] && [ "$_latest_iph" -gt "$_png_m" ]; then
    _SHOULD_NUTR=1
  fi
fi
if ! cap_step_enabled SYNC_NUTRITION; then
  _SHOULD_NUTR=0
fi
if [ "$_SHOULD_NUTR" = "1" ]; then
  if [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_iphone_nutrition_chart.py" ]; then
    echo "obsidian_sync: шаг 5d — Питание КБЖУ (PNG, после iphone_context_sync; лог: $PLANNING_BOT/logs/charts.log)…" >&2
    export VAULT_PATH="$LOCAL_VAULT"
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
    _nutr_py="${CHART_PYTHON:-python3}"
    if cd "$PLANNING_BOT" && "$_nutr_py" scripts/build_iphone_nutrition_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1; then
      echo "$TODAY" > "$NUTR_MARKER"
    fi
  fi
fi
unset _SHOULD_NUTR _IPHONE_CTX_DIR _NUTR_PNG _latest_iph _png_m

# 6. Финансы: каждый синк — pull канонической БД с сервера; PNG/markdown — раз в день или FORCE
FINANCE_MARKER="$SYNC_DIR/finance_dashboard_date.txt"
FINANCE_BOT="$AGENT_ROOT/finance_bot"
FIN_DB="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_DATA}/finance.db"
FIN_CHART_REF="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_CHARTS}/Финансы/Траты_по_дням_категории.png"
FIN_DB_NEWER=
if [ -f "$FIN_DB" ] && [ -f "$FIN_CHART_REF" ] && [ "$FIN_DB" -nt "$FIN_CHART_REF" ]; then
  FIN_DB_NEWER=1
fi
if cap_step_enabled SYNC_FINANCE_DASHBOARD && [ -d "$FINANCE_BOT" ] && [ -f "$FINANCE_BOT/scripts/sync_finance_db.sh" ]; then
  if [ -n "$SYNC_STATE_DIR" ]; then FIN_LOG="$SYNC_DIR/finance_dashboard_daily.log"; else FIN_LOG="$FINANCE_BOT/logs/finance_dashboard_daily.log"; fi
  mkdir -p "$(dirname "$FIN_LOG")" 2>/dev/null || true
  _FIN_BUILD=0
  if [ -n "${FORCE_FINANCE_DASHBOARD:-}" ] || [ -n "$FIN_DB_NEWER" ] || [ ! -f "$FINANCE_MARKER" ] || [ "$(cat "$FINANCE_MARKER" 2>/dev/null)" != "$TODAY" ]; then
    _FIN_BUILD=1
  fi
  echo "obsidian_sync: шаг 6 — finance.db pull (build=${_FIN_BUILD}; лог: $FIN_LOG)…" >&2
  export VAULT_PATH="$LOCAL_VAULT"
  if [ "$_FIN_BUILD" = "1" ]; then
    if (cd "$FINANCE_BOT" && ./scripts/run_finance_dashboard_daily.sh >> "$FIN_LOG" 2>&1); then
      echo "$TODAY" > "$FINANCE_MARKER"
      echo "$NOW_ISO" > "$SYNC_DIR/finance_dashboard_last_ok.txt"
    else
      echo "⚠️ finance dashboard build failed (see $FIN_LOG)" >&2
      SYNC_OK=0
    fi
  else
    if ! (
      FINANCE_REFRESH_BROKER_BEFORE_PULL=0
      FINANCE_BUILD_DASHBOARD_AFTER_PULL=0
      cd "$FINANCE_BOT" && ./scripts/sync_finance_db.sh >> "$FIN_LOG" 2>&1
    ); then
      echo "⚠️ finance.db pull failed (see $FIN_LOG)" >&2
      SYNC_OK=0
    elif [ -f "$FIN_DB" ] && [ -f "$FIN_CHART_REF" ] && {
      [ -n "${FORCE_FINANCE_DASHBOARD:-}" ] || [ "$FIN_DB" -nt "$FIN_CHART_REF" ]
    }; then
      # FIN_DB_NEWER выше — до pull; после scp БД часто новее PNG, а build=0 — графики не обновлялись весь день
      echo "obsidian_sync: finance.db новее PNG после pull — пересборка графиков…" >&2
      if (cd "$FINANCE_BOT" && ./scripts/run_finance_dashboard.sh >> "$FIN_LOG" 2>&1); then
        echo "$NOW_ISO" > "$SYNC_DIR/finance_dashboard_last_ok.txt"
      else
        echo "⚠️ finance dashboard rebuild after pull failed (see $FIN_LOG)" >&2
        SYNC_OK=0
      fi
    fi
  fi
fi
unset _FIN_BUILD FIN_DB_NEWER

# 5e. Каждый синк: read-only копия vault в iCloud для iPhone (100/200/300 без Данные/Действия/400 + .obsidian).
# Односторонне Mac→iCloud; тот же цикл, что rsync с сервером (LaunchAgent ~5 мин). SKIP_MOBILE_VAULT=1 — отключить.
MOBILE_EXPORT_SCRIPT="$AGENT_ROOT/scripts/export_mobile_vault.sh"
MOBILE_EXPORT_LOG="$SYNC_DIR/mobile_vault_export.log"
if cap_module_enabled PLANNING && [ -z "${SKIP_MOBILE_VAULT:-}" ] && [ -x "$MOBILE_EXPORT_SCRIPT" ]; then
  touch "$MOBILE_EXPORT_LOG" 2>/dev/null || true
  _trim_log "$MOBILE_EXPORT_LOG" 200 120
  echo "obsidian_sync: шаг 5e — export_mobile_vault (iCloud, лог: $MOBILE_EXPORT_LOG)…" >&2
  _mobile_rc=0
  SRC="$LOCAL_VAULT" zsh "$MOBILE_EXPORT_SCRIPT" >> "$MOBILE_EXPORT_LOG" 2>&1 || _mobile_rc=$?
  if [ "$_mobile_rc" -eq 0 ]; then
    echo "$NOW_ISO" > "$SYNC_DIR/mobile_vault_last_ok.txt" 2>/dev/null || true
  else
    echo "$(date '+%Y-%m-%dT%H:%M:%S') export_mobile_vault failed rc=${_mobile_rc}" >> "$MOBILE_EXPORT_LOG" 2>/dev/null || true
    echo "⚠️ export_mobile_vault завершился с ошибкой rc=${_mobile_rc} (см. $MOBILE_EXPORT_LOG)" >&2
  fi
  unset _mobile_rc
elif [ -n "${SKIP_MOBILE_VAULT:-}" ]; then
  echo "obsidian_sync: шаг 5e — пропуск (SKIP_MOBILE_VAULT=1)" >&2
fi

# 7. Маркер успешного синка и отчёт о здоровье (чтобы видеть, что сломалось, без поиска по логам)
echo "obsidian_sync: шаг 7 — last_sync_ok + health…" >&2
if [ "${SYNC_OK:-0}" = "1" ]; then
  if echo "$NOW_ISO" > "$SYNC_DIR/last_sync_ok.txt" 2>/dev/null; then WROTE=1; else WROTE=0; fi
  rm -f "$SYNC_DIR/last_sync_failed.txt" 2>/dev/null || true
  READ_BACK="$(head -1 "$SYNC_DIR/last_sync_ok.txt" 2>/dev/null)"
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ OK last_sync_ok=$SYNC_DIR wrote=$WROTE content=$READ_BACK" >> "$DEBUG_LOG" 2>/dev/null || true
else
  WROTE=0
  echo "$NOW_ISO critical steps failed (see $DEBUG_LOG)" > "$SYNC_DIR/last_sync_failed.txt" 2>/dev/null || true
  READ_BACK="$(head -1 "$SYNC_DIR/last_sync_ok.txt" 2>/dev/null)"
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ WARN critical sync steps failed; last_sync_ok not updated (prev=$READ_BACK)" >> "$DEBUG_LOG" 2>/dev/null || true
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
echo "obsidian_sync: готово." >&2
