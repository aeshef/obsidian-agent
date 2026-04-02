#!/bin/bash
# Скрипт для установки watcher'а добавления ID к задачам

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLANNING_BOT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.example.planning_bot.add_ids"
PLIST_FILE="$SCRIPT_DIR/$PLIST_NAME.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LAUNCH_AGENTS_PLIST="$LAUNCH_AGENTS_DIR/$PLIST_NAME.plist"

echo "🔧 Установка watcher'а для автоматического добавления ID к задачам"
echo ""

# Проверяем наличие watchdog
if ! python3 -c "import watchdog" 2>/dev/null; then
    echo "⚠️  watchdog не установлен. Устанавливаем..."
    pip3 install watchdog
    if [ $? -ne 0 ]; then
        echo "❌ Не удалось установить watchdog. Установите вручную: pip3 install watchdog"
        exit 1
    fi
    echo "✅ watchdog установлен"
fi

# Определяем путь к Python (используем тот же, что и в venv если есть)
if [ -f "$PLANNING_BOT_DIR/venv/bin/python3" ]; then
    PYTHON_PATH="$PLANNING_BOT_DIR/venv/bin/python3"
elif command -v python3 &> /dev/null; then
    # Получаем реальный путь к Python (не shim)
    PYTHON_PATH=$(python3 -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -z "$PYTHON_PATH" ] || [ ! -f "$PYTHON_PATH" ]; then
        # Fallback на which если не получилось
        PYTHON_PATH=$(which python3)
    fi
else
    PYTHON_PATH="/usr/local/bin/python3"
fi

echo "🐍 Используется Python: $PYTHON_PATH"

# Обновляем пути в plist файле
echo "📝 Обновление путей в plist файле..."
# Экранируем слеши для sed
PYTHON_PATH_ESC=$(echo "$PYTHON_PATH" | sed 's|/|\\/|g')
VAULT_PATH_ESC=$(echo "$(dirname "$(dirname "$(dirname "$(dirname "$PLANNING_BOT_DIR")")")")" | sed 's|/|\\/|g')

# Создаем временный файл с обновленными путями
sed "s|/Users/example/\\.pyenv/versions/3\\.12\\.7/bin/python3|$PYTHON_PATH|g" "$PLIST_FILE" | \
sed "s|/Users/example/Documents/Obsidian Vault|$(dirname "$(dirname "$(dirname "$(dirname "$PLANNING_BOT_DIR")")")")|g" > "$PLIST_FILE.tmp"
mv "$PLIST_FILE.tmp" "$PLIST_FILE"

# Проверяем, запущен ли уже watcher
if [ -f "$LAUNCH_AGENTS_PLIST" ]; then
    echo "🛑 Выгружаем существующий watcher..."
    launchctl unload "$LAUNCH_AGENTS_PLIST" 2>/dev/null || launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || true
    sleep 1
fi

# Копируем plist в LaunchAgents
echo "📋 Копирование plist в LaunchAgents..."
mkdir -p "$LAUNCH_AGENTS_DIR"
cp "$PLIST_FILE" "$LAUNCH_AGENTS_PLIST"

# Загружаем launchd job
echo "🚀 Запуск watcher через launchd..."

# Пробуем новый способ (macOS 10.11+)
if launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENTS_PLIST" 2>/dev/null; then
    echo "✅ Watcher загружен через launchctl bootstrap"
elif launchctl load "$LAUNCH_AGENTS_PLIST" 2>/dev/null; then
    echo "✅ Watcher загружен через launchctl load"
else
    echo "❌ Не удалось загрузить watcher. Попробуйте вручную:"
    echo "   launchctl bootstrap gui/$(id -u) $LAUNCH_AGENTS_PLIST"
    echo ""
    echo "Или проверьте ошибки:"
    launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENTS_PLIST" 2>&1 || launchctl load "$LAUNCH_AGENTS_PLIST" 2>&1
    exit 1
fi

echo ""
echo "✅ Watcher успешно установлен и запущен!"
echo ""
echo "📋 Управление:"
echo "   Остановить:  launchctl bootout gui/$(id -u)/$PLIST_NAME"
echo "   Запустить:   launchctl bootstrap gui/$(id -u) $LAUNCH_AGENTS_PLIST"
echo "   Статус:      launchctl list | grep $PLIST_NAME"
echo "   Логи:        tail -f $PLANNING_BOT_DIR/logs/add_ids_watcher.log"
echo ""
