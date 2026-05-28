#!/bin/bash
# Единый watchdog для ботов монорепо obsidian-agent.
#
# Вызывается из bot-specific wrapper (planning/finance/knowledge scripts/watchdog.sh),
# который задаёт переменные окружения:
#
#   WATCHDOG_BOT_ROOT      — корень бота (обязательно)
#   WATCHDOG_MODE          — poll | supervisor  (default: poll)
#   WATCHDOG_PGREP_PATTERN — regex для pgrep (poll mode)
#   WATCHDOG_PGREP_FALLBACK — fallback pattern без python.* prefix
#   WATCHDOG_RUN_SCRIPT    — путь к run.sh (default: ./scripts/run.sh)
#   WATCHDOG_LOG           — лог (default: logs/watchdog.log)
#   WATCHDOG_CHECK_INTERVAL — сек между проверками poll (default: 60)
#   WATCHDOG_MAX_RESTARTS  — лимит рестартов/час poll (default: 5)
#   WATCHDOG_LOCK_FILE     — flock lock supervisor mode
#   WATCHDOG_SUPERVISOR_CMD — команда проверки «бот жив» для supervisor (optional)
#   WATCHDOG_INITIAL_BACKOFF / WATCHDOG_MAX_BACKOFF — supervisor backoff

set -uo pipefail

BOT_ROOT="${WATCHDOG_BOT_ROOT:?WATCHDOG_BOT_ROOT required}"
MODE="${WATCHDOG_MODE:-poll}"
RUN_SCRIPT="${WATCHDOG_RUN_SCRIPT:-./scripts/run.sh}"
LOG_FILE="${WATCHDOG_LOG:-logs/watchdog.log}"
CHECK_INTERVAL="${WATCHDOG_CHECK_INTERVAL:-60}"
MAX_RESTART_ATTEMPTS="${WATCHDOG_MAX_RESTARTS:-5}"
RESTART_WINDOW=3600
PGREP_PATTERN="${WATCHDOG_PGREP_PATTERN:-}"
PGREP_FALLBACK="${WATCHDOG_PGREP_FALLBACK:-}"
LOCK_FILE="${WATCHDOG_LOCK_FILE:-}"
INITIAL_BACKOFF="${WATCHDOG_INITIAL_BACKOFF:-2}"
MAX_BACKOFF="${WATCHDOG_MAX_BACKOFF:-60}"

cd "$BOT_ROOT"
mkdir -p logs

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_message_simple() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | watchdog | $1" | tee -a "$LOG_FILE"
}

count_recent_restarts() {
    local cutoff=$(( $(date +%s) - RESTART_WINDOW ))
    if [ ! -f "$LOG_FILE" ]; then
        echo "0"
        return
    fi
    grep -E '🔄 Перезапуск бота|relaunching' "$LOG_FILE" 2>/dev/null | while read -r line; do
        local timestamp
        timestamp=$(echo "$line" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}' | head -1)
        [ -n "$timestamp" ] || continue
        local log_time
        log_time=$(date -d "$timestamp" +%s 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "$timestamp" +%s 2>/dev/null || echo "0")
        [ "$log_time" -gt "$cutoff" ] && echo "1"
    done | wc -l | tr -d ' '
}

is_bot_running_poll() {
    [ -n "$PGREP_PATTERN" ] && pgrep -f "$PGREP_PATTERN" >/dev/null 2>&1 && return 0
    [ -n "$PGREP_FALLBACK" ] && pgrep -f "$PGREP_FALLBACK" >/dev/null 2>&1 && return 0
    return 1
}

restart_bot_poll() {
    local recent_restarts
    recent_restarts=$(count_recent_restarts)
    if [ "$recent_restarts" -ge "$MAX_RESTART_ATTEMPTS" ]; then
        log_message "❌ Превышен лимит перезапусков ($recent_restarts за час). Останавливаю watchdog."
        exit 1
    fi
    log_message "🔄 Перезапуск бота (попытка $((recent_restarts + 1))/$MAX_RESTART_ATTEMPTS)..."
    log_message "📝 Запуск: $RUN_SCRIPT"
    nohup bash "$RUN_SCRIPT" >> logs/bot.log 2>&1 &
    local bot_pid=$!
    log_message "📝 Запущен nohup PID: $bot_pid"
    sleep 5
    if is_bot_running_poll; then
        local real_pid
        real_pid=$(pgrep -f "${PGREP_PATTERN:-$PGREP_FALLBACK}" | head -1)
        [ -n "$real_pid" ] && echo "$real_pid" > logs/bot.pid
        log_message "✅ Бот запущен (PID: ${real_pid:-unknown})"
    else
        log_message "❌ Не удалось запустить бота — tail logs/bot.log"
        [ -f logs/bot.log ] && tail -10 logs/bot.log | while read -r line; do log_message "   $line"; done
    fi
}

# ── supervisor mode (knowledge-style: foreground + backoff) ──
kb_running_supervisor() {
    if [ -n "${WATCHDOG_SUPERVISOR_CMD:-}" ]; then
        bash -c "$WATCHDOG_SUPERVISOR_CMD"
        return $?
    fi
    for pid in $(pgrep -f "start_bot.py" 2>/dev/null || true); do
        [ -r "/proc/${pid}/exe" ] || continue
        readlink -f "/proc/${pid}/exe" 2>/dev/null | grep -qE '(python|python3)$' || continue
        tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null | grep -qF "start_bot.py" || continue
        return 0
    done
    return 1
}

run_supervisor_mode() {
    if [ -n "$LOCK_FILE" ]; then
        exec 9>"$LOCK_FILE"
        if command -v flock >/dev/null 2>&1; then
            flock -n 9 || exit 0
        fi
    fi
    log_message_simple "started (supervisor mode)"
    local backoff=$INITIAL_BACKOFF
    while true; do
        if kb_running_supervisor; then
            sleep 10
            continue
        fi
        log_message_simple "launching $RUN_SCRIPT"
        set +e
        bash "$RUN_SCRIPT" >> logs/bot.log 2>&1
        local code=$?
        set -e
        log_message_simple "bot exited code=${code}; sleeping ${backoff}s"
        sleep "$backoff"
        backoff=$((backoff * 2))
        [ "$backoff" -gt "$MAX_BACKOFF" ] && backoff=$MAX_BACKOFF
    done
}

run_poll_mode() {
    log_message "🛡️ Watchdog poll mode (interval ${CHECK_INTERVAL}s, pattern: ${PGREP_PATTERN:-$PGREP_FALLBACK})"
    log_message "📁 $(pwd)"
    while true; do
        if ! is_bot_running_poll; then
            log_message "⚠️ Бот не запущен!"
            restart_bot_poll
        fi
        sleep "$CHECK_INTERVAL"
    done
}

case "$MODE" in
    supervisor) run_supervisor_mode ;;
    poll|*) run_poll_mode ;;
esac
