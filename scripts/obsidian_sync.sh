#!/bin/zsh
# Лог каждого запуска в /tmp (доступно и из launchd) — смотреть: tail -f /tmp/obsidian_sync_debug.log
DEBUG_LOG="/tmp/obsidian_sync_debug.log"
echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ START" >> "$DEBUG_LOG" 2>/dev/null || true

# Защита от устаревшего агента -v2 (зомби): он вызывает /tmp/obsidian_sync.sh без FDA.
# Если нет доступа к vault (Documents) — сразу выходим, не трогая rsync.
VAULT_TEST="${AGENT_ROOT:-${LOCAL_VAULT:-${HOME}/Documents/Obsidian Vault}/800_Автоматизация/Agent}/obsidian_sync.sh"
if ! test -r "$VAULT_TEST" 2>/dev/null || ! head -c1 "$VAULT_TEST" >/dev/null 2>/dev/null; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ SKIP: нет доступа к vault (запуск без FDA), выхожу" >> "$DEBUG_LOG" 2>/dev/null || true
  exit 0
fi

# Синхронизация Obsidian Vault с сервером: 100_Задачи, 200_Цели, 300_Дашборды, 400_Рутины, 600_Рукописное, 700_База_Данных.
# После обновления локального vault — зеркало в iCloud для Obsidian на iPhone (шаг 5e, export_mobile_vault.sh).
# Общий скрипт для planning_bot и knowledge_bot. LaunchAgent вызывает копию скрипта из /tmp/obsidian_sync.sh каждые 2 мин (scripts/install_launchagent.sh кладёт копию в /tmp).
#
# Восстановление LaunchAgent: ./800_Автоматизация/Agent/scripts/install_launchagent.sh (plist в LaunchAgents, симлинк ~/bin → скрипт в vault для ручного запуска).
#
# Исключения для 300_Дашборды: Графики/, weekly_sprints.json, Completions_By_Category_Chart.md
# не подтягиваются с сервера, чтобы не возвращались после удаления (см. docs/300_Дашборды_исключения_синка.md).
#
# Если заметки не уезжают на сервер / не приходят с сервера — смотреть ошибки: /tmp/obsidian-sync.err (при запуске из LaunchAgent)
#
# Принудительно: FORCE_CHARTS=1 — пересобрать графики канбана (шаг 5). FORCE_FINANCE_DASHBOARD=1 — скачать finance.db и пересобрать фин. дашборд/PNG (шаг 6), даже если сегодня уже запускали (иначе шаг 6 — раз в сутки по маркеру .sync/finance_dashboard_date.txt).

# Без set -e: ошибка одной папки (например 400_Рутины на сервере) не останавливает синк остальных, в т.ч. 700_База_Данных
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
SERVER_VAULT="${SERVER_VAULT:-/opt/obsidian-vault}"
SERVER_BOTS="${SERVER_BOTS:-/opt/obsidian-bots}"
if [ -z "$SERVER" ]; then
  echo "obsidian_sync: задайте SERVER в .env (SSH host)" >&2
  exit 1
fi
RSYNC_BIN="${RSYNC_BIN:-rsync}"
FLAGS=(-avz)
# Не создаём и не синхронизируем бэкапы rsync
EXCLUDE_BACKUP=( --exclude='.rsync-backup/' )

# LaunchAgent не видит SSH-агент; ключ из Keychain нужен явно. Иначе rsync/ssh падают с Permission denied, маркер last_sync_ok всё равно пишется.
export RSYNC_RSH="${RSYNC_RSH:-ssh -o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3}"
SSH_OPTS=(-o UseKeychain=yes -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)

# Исключения при подтягивании 300_Дашборды. Логи только в Логи/; корневой 📊 Логи_Действий_*.md не тянуть и не пушить (устаревшая структура).
EXCLUDE_300=(
  --exclude='Графики/'
  --exclude='weekly_sprints.json'
  --exclude='Completions_By_Category_Chart.md'
  --exclude='data/'
  --exclude='📅 Рутины/'
  --exclude='📊 Рутины_Статистика.md'
  --exclude='/📊 Логи_Действий_*.md'
)
# 1. Сервер → Локальный. --update: не перезаписывать локальные, если они новее (сохраняем правки в Obsidian). Если новее сервер (задача через бота / заметки knowledge bot) — подтягиваем.
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/100_Задачи/" "$LOCAL_VAULT/100_Задачи/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/200_Цели/" "$LOCAL_VAULT/200_Цели/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${EXCLUDE_300[@]}" --update "$SERVER:$SERVER_VAULT/300_Дашборды/" "$LOCAL_VAULT/300_Дашборды/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/400_Рутины/" "$LOCAL_VAULT/400_Рутины/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/600_Рукописное/" "$LOCAL_VAULT/600_Рукописное/"
# 700_База_Данных — заметки от knowledge bot (без них граф и локальный vault не видят новые заметки)
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$SERVER:$SERVER_VAULT/700_База_Данных/" "$LOCAL_VAULT/700_База_Данных/"
# Важно: rsync с --update НЕ удаляет на удалённой стороне файлы, которые уже убраны локально.
# Поэтому после шага 5b.2 (удаление дублей в Export на Mac) выполняется 5b.2b — тот же apply_duplicates на сервере.

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
)
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$LOCAL_VAULT/100_Задачи/" "$SERVER:$SERVER_VAULT/100_Задачи/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$LOCAL_VAULT/200_Цели/" "$SERVER:$SERVER_VAULT/200_Цели/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${PUSH_EXCLUDE_300[@]}" --update "$LOCAL_VAULT/300_Дашборды/" "$SERVER:$SERVER_VAULT/300_Дашборды/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$LOCAL_VAULT/400_Рутины/" "$SERVER:$SERVER_VAULT/400_Рутины/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$LOCAL_VAULT/600_Рукописное/" "$SERVER:$SERVER_VAULT/600_Рукописное/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --update "$LOCAL_VAULT/700_База_Данных/" "$SERVER:$SERVER_VAULT/700_База_Данных/"

# 3. Обслуживание vault на сервере (VAULT_PATH=/root/obsidian-vault — тот же путь, откуда забирает rsync)
# Плюс: сразу после обслуживания запускаем kanban_monitor, чтобы новые задачи/перемещения из Obsidian попали в action-логи в этом же цикле синка.
echo "obsidian_sync: шаг 3 — SSH: vault_maintenance + kanban на сервере (без вывода; лог на сервере: planning_bot/logs/maintenance.log)…" >&2
ssh "${SSH_OPTS[@]}" "$SERVER" "cd ${SERVER_BOTS}/planning_bot && ( ./scripts/run_maintenance_from_sync.sh 2>/dev/null || ( set -a && [ -f ../.env ] && . ../.env; [ -f .env ] && . .env; set +a && source venv/bin/activate && export PYTHONPATH='${SERVER_BOTS}'\${PYTHONPATH:+':'}\"\$PYTHONPATH\" && export VAULT_PATH='$SERVER_VAULT' && FROM_SYNC=1 python -m planning_bot.tools.vault_maintenance ) ) >> logs/maintenance.log 2>&1 && ( set -a && [ -f ../.env ] && . ../.env; set +a && source venv/bin/activate && export PYTHONPATH='${SERVER_BOTS}'\${PYTHONPATH:+':'}\"\$PYTHONPATH\" && export VAULT_PATH='$SERVER_VAULT' && python -m planning_bot.services.kanban_monitor ) >> logs/maintenance.log 2>&1" || { echo "⚠️ Maintenance на сервере завершился с ошибкой (см. ssh \$SERVER 'tail -50 ${SERVER_BOTS}/planning_bot/logs/maintenance.log')" >&2; }

# 4. Подтянуть обновлённые файлы с сервера после maintenance (--ignore-times: всегда перезаписать локаль отсортированной доской)
echo "obsidian_sync: шаг 4 — rsync сервер→локаль после maintenance…" >&2
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" --ignore-times "$SERVER:$SERVER_VAULT/100_Задачи/" "$LOCAL_VAULT/100_Задачи/"
"$RSYNC_BIN" "${FLAGS[@]}" "${EXCLUDE_BACKUP[@]}" "${EXCLUDE_300[@]}" "$SERVER:$SERVER_VAULT/300_Дашборды/" "$LOCAL_VAULT/300_Дашборды/"
# 700 уже подтянут в шаге 1; при необходимости можно добавить сюда с --ignore-times

TODAY=$(date +%Y-%m-%d)
NOW_ISO=$(date +%Y-%m-%dT%H:%M:%S)

# 5. Раз в день пересобрать графики главного дашборда (Активность за день, Завершено по категориям, открытый пайплайн)
# Графики строятся локально по action-логам (300_Дашборды/Логи); в синк с сервера Графики/ не тянутся.
# При ручном запуске можно принудительно пересобрать: FORCE_CHARTS=1 ~/bin/obsidian_sync.sh
MARKER="$SYNC_DIR/daily_charts_date.txt"
LOGS_DIR="$LOCAL_VAULT/300_Дашборды/Логи"
HAS_LOGS=
[ -d "$LOGS_DIR" ] && [ "$(find "$LOGS_DIR" -maxdepth 1 -name '*Логи_Действий_*.md' 2>/dev/null | wc -l)" -gt 0 ] && HAS_LOGS=1
if [ -n "${FORCE_CHARTS:-}" ] || [ ! -f "$MARKER" ] || [ "$(cat "$MARKER" 2>/dev/null)" != "$TODAY" ]; then
  PLANNING_BOT="$AGENT_ROOT/planning_bot"
  if [ -n "$HAS_LOGS" ] && [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_daily_task_activity_chart.py" ]; then
    echo "obsidian_sync: шаг 5 — графики дашборда (python×3, лог: $PLANNING_BOT/logs/charts.log; из planning_bot: tail -f logs/charts.log)…" >&2
    export LOCAL_VAULT
    if cd "$PLANNING_BOT" && python3 scripts/build_daily_task_activity_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1 \
       && python3 scripts/build_daily_completions_by_category_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1 \
       && python3 scripts/build_open_pipeline_by_category_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1 \
       && python3 scripts/build_deadline_horizon_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1; then
      echo "$TODAY" > "$MARKER"
    fi
  fi
fi

# 5c. Пересобрать PNG графиков встреч локально — server не имеет matplotlib, Графики/ не тянутся с сервера.
# Запускается при каждом синке (быстро: только если Календарь.json свежее PNG или раз в день).
CAL_MARKER="$SYNC_DIR/calendar_charts_date.txt"
PLANNING_BOT="${PLANNING_BOT:-$AGENT_ROOT/planning_bot}"
if [ -n "${FORCE_CHARTS:-}" ] || [ ! -f "$CAL_MARKER" ] || [ "$(cat "$CAL_MARKER" 2>/dev/null)" != "$TODAY" ]; then
  if [ -d "$PLANNING_BOT" ]; then
    echo "obsidian_sync: шаг 5c — calendar_sync (PNG встреч, тот же лог: logs/charts.log)…" >&2
    export LOCAL_VAULT
    export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
    if cd "$PLANNING_BOT" && python3 -m planning_bot.tools.calendar_sync >> logs/charts.log 2>&1; then
      echo "$TODAY" > "$CAL_MARKER"
    fi
  fi
fi

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
if [ -n "${FORCE_SYSTEM_AUDIT:-}" ] || [ ! -f "$SYS_AUDIT_MARKER" ] || [ "$(cat "$SYS_AUDIT_MARKER" 2>/dev/null)" != "$TODAY" ]; then
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
if [ -n "${FORCE_VAULT_MAINTENANCE:-}" ] \
   || { { [ ! -f "$VM_MARKER" ] || [ "$(cat "$VM_MARKER" 2>/dev/null)" != "$TODAY" ]; } \
        && [ "$_vm_skip_today" = "0" ]; }; then
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
            >>"$PLANNING_BOT/logs/vault_write_maintenance.log" 2>&1 <<'REMOTE_DUP' || echo "⚠️ obsidian_sync: 5b.2b завершился с ошибкой — см. vault_write_maintenance.log" >&2
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
  echo "⚠️ 5b.2b: нет knowledge_bot с tools/apply_duplicates_resolution.py — задай REMOTE_KNOWLEDGE_BOT или разверни ${VAULT_PATH}/800_Автоматизация/Agent/knowledge_bot на сервере"
  exit 0
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
if { [ -n "${FORCE_SYSTEM_AUDIT:-}" ] \
     || { [ ! -f "$KN_AUDIT_MARKER" ] || [ "$(cat "$KN_AUDIT_MARKER" 2>/dev/null)" != "$TODAY" ]; } \
   } && [ "$_kn_skip_today" = "0" ]; then
  if [ -d "$KNOWLEDGE_BOT" ] && [ -f "$KNOWLEDGE_BOT/tools/analyze_vault_report.py" ]; then
    echo "obsidian_sync: шаг 5b.3 — тяжёлый аудит 700_ (часто 1–5+ мин; tail -f logs/system_audit.log)…" >&2
    export VAULT_PATH="$LOCAL_VAULT"
    export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
    if (cd "$KNOWLEDGE_BOT" && "$KN_PYTHON" tools/analyze_vault_report.py --vault "$LOCAL_VAULT" --out "$LOCAL_VAULT/300_Дашборды/Аудит_хранилища_отчет.md") >> "$PLANNING_BOT/logs/system_audit.log" 2>&1; then
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

# 5b.4 iPhone-контекст из Gmail IMAP (iphone_mail_sync)
# Требует GMAIL_IMAP_USER и GMAIL_IMAP_APP_PASSWORD в .env planning_bot.
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
if [ "$_SHOULD_IMAP" = "1" ] && [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/tools/iphone_mail_sync.py" ]; then
  echo "obsidian_sync: шаг 5b.4 — iPhone mail sync (Gmail IMAP → IPhone/*.txt)…" >&2
  _PB_ENV="$PLANNING_BOT/.env"
  if [ -f "$_PB_ENV" ]; then
    set -a; source "$_PB_ENV" 2>/dev/null || true; set +a
  fi
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
    echo "obsidian_sync: шаг 5b.4 — пропуск, GMAIL_IMAP_USER не задан (добавь в planning_bot/.env)" >&2
  fi
fi

# 5b.4b Каждый синк: iphone_today.json / iphone_week.json из IPhone/*.txt (без IMAP, быстро)
if [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/tools/iphone_context_sync.py" ]; then
  touch "$PLANNING_BOT/logs/iphone_context_sync.log" 2>/dev/null || true
  export VAULT_PATH="$LOCAL_VAULT"
  export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$PLANNING_BOT" && PYTHONUNBUFFERED=1 python3 -u tools/iphone_context_sync.py) >> "$PLANNING_BOT/logs/iphone_context_sync.log" 2>&1 || true
fi

# 5d. График КБЖУ — после 5b.4 + 5b.4b. Раз в сутки по маркеру, НО также если появился новый IPhone/*.txt
# позже последнего PNG (иначе ночной прогон в 00:04 блокирует день до вечернего снапшота).
NUTR_MARKER="$SYNC_DIR/daily_iphone_nutrition_date.txt"
_IPHONE_CTX_DIR="$LOCAL_VAULT/300_Дашборды/Данные/Действия/IPhone"
_NUTR_PNG="$LOCAL_VAULT/300_Дашборды/Графики/Питание_КБЖУ_по_дням.png"
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
if [ "$_SHOULD_NUTR" = "1" ]; then
  if [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_iphone_nutrition_chart.py" ]; then
    echo "obsidian_sync: шаг 5d — Питание КБЖУ (PNG, после iphone_context_sync; лог: $PLANNING_BOT/logs/charts.log)…" >&2
    export VAULT_PATH="$LOCAL_VAULT"
    export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
    if cd "$PLANNING_BOT" && env -u PYTHONPATH python3 scripts/build_iphone_nutrition_chart.py --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1; then
      echo "$TODAY" > "$NUTR_MARKER"
    fi
  fi
fi
unset _SHOULD_NUTR _IPHONE_CTX_DIR _NUTR_PNG _latest_iph _png_m

# 6. Раз в день: синк БД финансов + сборка финансового дашборда (один LaunchAgent — всё в одном)
# Повторно в тот же день: только с FORCE_FINANCE_DASHBOARD=1 (иначе графики/БД не обновятся до завтра)
FINANCE_MARKER="$SYNC_DIR/finance_dashboard_date.txt"
FINANCE_BOT="$AGENT_ROOT/finance_bot"
if [ -n "${FORCE_FINANCE_DASHBOARD:-}" ] || [ ! -f "$FINANCE_MARKER" ] || [ "$(cat "$FINANCE_MARKER" 2>/dev/null)" != "$TODAY" ]; then
  if [ -d "$FINANCE_BOT" ] && [ -f "$FINANCE_BOT/scripts/run_finance_dashboard_daily.sh" ]; then
    if [ -n "$SYNC_STATE_DIR" ]; then FIN_LOG="$SYNC_DIR/finance_dashboard_daily.log"; else FIN_LOG="$FINANCE_BOT/logs/finance_dashboard_daily.log"; fi
    echo "obsidian_sync: шаг 6 — finance.db + фин. дашборд (лог: $FIN_LOG)…" >&2
    export VAULT_PATH="$LOCAL_VAULT"
    # Не наследовать PYTHONPATH от шагов knowledge_bot — ломает numpy/matplotlib у finance build.
    if (cd "$FINANCE_BOT" && env -u PYTHONPATH ./scripts/run_finance_dashboard_daily.sh >> "$FIN_LOG" 2>&1); then
      echo "$TODAY" > "$FINANCE_MARKER"
      echo "$NOW_ISO" > "$SYNC_DIR/finance_dashboard_last_ok.txt"
    fi
  fi
fi

# 5e. Каждый синк: read-only копия vault в iCloud для iPhone (100/200/300 без Данные/Действия/400 + .obsidian).
# Односторонне Mac→iCloud; тот же цикл, что rsync с сервером (LaunchAgent ~5 мин). SKIP_MOBILE_VAULT=1 — отключить.
MOBILE_EXPORT_SCRIPT="$AGENT_ROOT/scripts/export_mobile_vault.sh"
MOBILE_EXPORT_LOG="$SYNC_DIR/mobile_vault_export.log"
if [ -z "${SKIP_MOBILE_VAULT:-}" ] && [ -x "$MOBILE_EXPORT_SCRIPT" ]; then
  touch "$MOBILE_EXPORT_LOG" 2>/dev/null || true
  _trim_log "$MOBILE_EXPORT_LOG" 200 120
  echo "obsidian_sync: шаг 5e — export_mobile_vault (iCloud, лог: $MOBILE_EXPORT_LOG)…" >&2
  if SRC="$LOCAL_VAULT" zsh "$MOBILE_EXPORT_SCRIPT" >> "$MOBILE_EXPORT_LOG" 2>&1; then
    echo "$NOW_ISO" > "$SYNC_DIR/mobile_vault_last_ok.txt" 2>/dev/null || true
  else
    echo "$(date '+%Y-%m-%dT%H:%M:%S') export_mobile_vault failed rc=$?" >> "$MOBILE_EXPORT_LOG" 2>/dev/null || true
    echo "⚠️ export_mobile_vault завершился с ошибкой (см. $MOBILE_EXPORT_LOG)" >&2
  fi
elif [ -n "${SKIP_MOBILE_VAULT:-}" ]; then
  echo "obsidian_sync: шаг 5e — пропуск (SKIP_MOBILE_VAULT=1)" >&2
fi

# 7. Маркер успешного синка и отчёт о здоровье (чтобы видеть, что сломалось, без поиска по логам)
echo "obsidian_sync: шаг 7 — last_sync_ok + health…" >&2
if echo "$NOW_ISO" > "$SYNC_DIR/last_sync_ok.txt" 2>/dev/null; then WROTE=1; else WROTE=0; fi
READ_BACK="$(head -1 "$SYNC_DIR/last_sync_ok.txt" 2>/dev/null)"
echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ OK last_sync_ok=$SYNC_DIR wrote=$WROTE content=$READ_BACK" >> "$DEBUG_LOG" 2>/dev/null || true
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
