#!/bin/bash
# Скрипт для проверки статуса бота на сервере

echo "=== Проверка процесса бота ==="
ps aux | grep -E '[b]ot.main' || echo "❌ Бот не запущен"

echo ""
echo "=== Последние 50 строк логов ==="
tail -50 logs/bot.log 2>/dev/null || echo "❌ Логи не найдены"

echo ""
echo "=== Проверка импортов ==="
cd ~/bots/finance_bot 2>/dev/null || cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || echo "⚠️ venv не активирован"
python3 -c "
import sys
sys.path.insert(0, '.')
try:
    import bot.main
    print('✅ bot импортирован')
except Exception as e:
    print(f'❌ Ошибка импорта bot: {e}')
    import traceback
    traceback.print_exc()
"

echo ""
echo "=== PID файл ==="
cat logs/bot.pid 2>/dev/null || echo "❌ PID файл не найден"

echo ""
echo "=== Watchdog лог ==="
tail -20 logs/watchdog.log 2>/dev/null || echo "⚠️ Watchdog лог не найден"
