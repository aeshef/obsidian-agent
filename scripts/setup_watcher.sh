#!/bin/bash
# Установка launchd-watcher'а для watch_and_add_ids.py (macOS).
# Читает шаблон scripts/com.example.planning_bot.add_ids.plist.example и пишет готовый plist в ~/Library/LaunchAgents/
# (репозиторий не изменяется).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLANNING_BOT_DIR="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$SCRIPT_DIR/com.example.planning_bot.add_ids.plist.example"
LABEL="${LAUNCH_AGENT_LABEL:-com.example.planning_bot.add_ids}"
PLIST_NAME="$LABEL"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LAUNCH_AGENTS_PLIST="$LAUNCH_AGENTS_DIR/${PLIST_NAME}.plist"

echo "🔧 Установка watcher'а для автоматического добавления ID к задачам"
echo "   Label: $LABEL (override: LAUNCH_AGENT_LABEL=com.yourname.planning_bot.add_ids)"
echo ""

if [ ! -f "$TEMPLATE" ]; then
    echo "❌ Не найден шаблон: $TEMPLATE"
    exit 1
fi

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

# Путь к Python: venv приоритетнее
if [ -f "$PLANNING_BOT_DIR/venv/bin/python3" ]; then
    PYTHON_PATH="$PLANNING_BOT_DIR/venv/bin/python3"
elif command -v python3 &> /dev/null; then
    PYTHON_PATH=$(python3 -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -z "$PYTHON_PATH" ] || [ ! -f "$PYTHON_PATH" ]; then
        PYTHON_PATH=$(which python3)
    fi
else
    PYTHON_PATH="/usr/local/bin/python3"
fi

echo "🐍 Используется Python: $PYTHON_PATH"

ROOT_RESOLVED=$(cd "$PLANNING_BOT_DIR" && pwd)
PY_RESOLVED=$(cd "$(dirname "$PYTHON_PATH")" && pwd)/$(basename "$PYTHON_PATH")
BIN_DIR=$(dirname "$PY_RESOLVED")
LAUNCHD_PATH="${BIN_DIR}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

echo "📝 Генерация plist из шаблона..."
GEN=$(mktemp /tmp/planning_add_ids.XXXXXX.plist)
python3 - "$ROOT_RESOLVED" "$PY_RESOLVED" "$LAUNCHD_PATH" "$LABEL" "$TEMPLATE" "$GEN" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
py = Path(sys.argv[2]).resolve()
launchd_path = sys.argv[3]
label = sys.argv[4]
template = Path(sys.argv[5])
out = Path(sys.argv[6])

text = template.read_text(encoding="utf-8")
text = text.replace("__LABEL__", label)
text = text.replace("__PLANNING_BOT_ROOT__", str(root))
text = text.replace("__PYTHON_EXEC__", str(py))
text = text.replace("__LAUNCHD_PATH__", launchd_path)
out.write_text(text, encoding="utf-8")
PY

if [ $? -ne 0 ] || [ ! -s "$GEN" ]; then
    echo "❌ Ошибка генерации plist"
    rm -f "$GEN"
    exit 1
fi

# Миграция: старый личный bundle id из прежних версий репозитория
launchctl bootout "gui/$(id -u)/com.example.planning_bot.add_ids" 2>/dev/null || true
rm -f "$LAUNCH_AGENTS_DIR/com.example.planning_bot.add_ids.plist"

if [ -f "$LAUNCH_AGENTS_PLIST" ]; then
    echo "🛑 Выгружаем существующий watcher..."
    launchctl unload "$LAUNCH_AGENTS_PLIST" 2>/dev/null || launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || true
    sleep 1
fi

echo "📋 Копирование plist в LaunchAgents..."
mkdir -p "$PLANNING_BOT_DIR/logs"
mkdir -p "$LAUNCH_AGENTS_DIR"
cp "$GEN" "$LAUNCH_AGENTS_PLIST"
rm -f "$GEN"

echo "🚀 Запуск watcher через launchd..."

if launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENTS_PLIST" 2>/dev/null; then
    echo "✅ Watcher загружен через launchctl bootstrap"
elif launchctl load "$LAUNCH_AGENTS_PLIST" 2>/dev/null; then
    echo "✅ Watcher загружен через launchctl load"
else
    echo "❌ Не удалось загрузить watcher. Попробуйте вручную:"
    echo "   launchctl bootstrap gui/$(id -u) $LAUNCH_AGENTS_PLIST"
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
