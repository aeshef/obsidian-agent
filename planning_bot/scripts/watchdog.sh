#!/bin/bash
# Скрипт-сторож для автоматического перезапуска бота при падении
# Использование: ./scripts/watchdog.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BOT_SCRIPT="./scripts/run.sh"
CHECK_INTERVAL=60  # Проверка каждые 60 секунд
LOG_FILE="logs/watchdog.log"
MAX_RESTART_ATTEMPTS=5  # Максимум попыток перезапуска в течение часа
RESTART_WINDOW=3600  # Окно времени в секундах (1 час)

# Создаем директорию для логов
mkdir -p logs

# Функция логирования
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Функция проверки, запущен ли бот
is_bot_running() {
    # Проверяем наличие процесса planning_bot.app.bot
    pgrep -f 'python.*planning_bot.app.bot' > /dev/null 2>&1
    return $?
}

# Функция подсчета перезапусков за последний час
count_recent_restarts() {
    local now=$(date +%s)
    local cutoff=$((now - RESTART_WINDOW))
    
    # Считаем записи о перезапусках за последний час
    if [ -f "$LOG_FILE" ]; then
        grep "🔄 Перезапуск бота" "$LOG_FILE" | while read line; do
            local timestamp=$(echo "$line" | grep -oP '\[\K[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}')
            if [ -n "$timestamp" ]; then
                local log_time=$(date -d "$timestamp" +%s 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "$timestamp" +%s 2>/dev/null || echo "0")
                if [ "$log_time" -gt "$cutoff" ]; then
                    echo "1"
                fi
            fi
        done | wc -l | tr -d ' '
    else
        echo "0"
    fi
}

log_message "🛡️ Watchdog запущен (интервал проверки: ${CHECK_INTERVAL}с)"
log_message "📁 Рабочая директория: $(pwd)"
log_message "🔧 BOT_SCRIPT: $BOT_SCRIPT"

while true; do
    if ! is_bot_running; then
        log_message "⚠️ Бот не запущен!"
        
        # Проверяем количество перезапусков за последний час
        recent_restarts=$(count_recent_restarts)
        
        if [ "$recent_restarts" -ge "$MAX_RESTART_ATTEMPTS" ]; then
            log_message "❌ Превышен лимит перезапусков ($recent_restarts за последний час). Останавливаю watchdog."
            log_message "💡 Проверь логи бота и исправь проблему вручную."
            exit 1
        fi
        
        log_message "🔄 Перезапуск бота (попытка $((recent_restarts + 1))/$MAX_RESTART_ATTEMPTS)..."
        
        # Запускаем бота через run.sh
        log_message "📝 Запуск: $BOT_SCRIPT"
        nohup bash $BOT_SCRIPT > logs/bot.log 2>&1 &
        BOT_PID=$!
        log_message "📝 Запущен процесс (nohup PID: $BOT_PID)"
        
        # Ждем немного и проверяем, что процесс запустился
        sleep 5
        
        # Ищем реальный PID процесса planning_bot.app.bot
        REAL_PID=$(pgrep -f 'python.*planning_bot.app.bot' | head -1)
        if [ -n "$REAL_PID" ]; then
            echo "$REAL_PID" > logs/bot.pid
            log_message "✅ Бот успешно запущен (реальный PID: $REAL_PID, nohup PID: $BOT_PID)"
        elif is_bot_running; then
            REAL_PID=$(pgrep -f 'planning_bot.app.bot' | head -1)
            if [ -n "$REAL_PID" ]; then
                echo "$REAL_PID" > logs/bot.pid
                log_message "✅ Бот запущен (PID: $REAL_PID)"
            else
                log_message "⚠️ Бот запущен, но не удалось определить PID"
            fi
        else
            log_message "❌ Не удалось запустить бота. Проверь логи:"
            log_message "   tail -50 logs/bot.log"
            # Показываем последние строки лога с ошибками
            if [ -f "logs/bot.log" ]; then
                tail -20 logs/bot.log | while read line; do
                    log_message "   $line"
                done
            fi
        fi
    else
        # Бот работает нормально - можно сбросить счетчик если прошло достаточно времени
        # (это логируется каждую минуту, но без вывода, чтобы не спамить)
        :
    fi
    
    sleep $CHECK_INTERVAL
done
