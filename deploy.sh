#!/bin/bash
# Скрипт для деплоя finance_bot на сервер example-server

[REDACTED]
BOT_DIR="$VAULT_PATH/800_Автоматизация/Agent/finance_bot"
SERVER="example-server"
SERVER_BOT_DIR="~/bots/finance_bot"

cd "$VAULT_PATH"

echo "🚀 Деплой finance_bot на сервер..."
echo ""

# Проверка SSH
echo "🔍 Проверяю SSH подключение..."
if ! ssh -o ConnectTimeout=5 $SERVER "echo 'SSH работает!'" > /dev/null 2>&1; then
    echo "❌ SSH не работает! Проверь подключение к example-server"
    exit 1
fi
echo "✅ SSH подключение работает"
echo ""

# Синхронизация файлов
echo "🔄 Синхронизация файлов на сервер..."
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='.DS_Store' \
  --exclude='.venv/' --exclude='__pycache__/' --exclude='*.pyc' \
  --exclude='logs/*.log' --exclude='logs/console.log' \
  --exclude='finance.db' --exclude='.env' \
  "$BOT_DIR/" $SERVER:$SERVER_BOT_DIR/

echo ""
echo "✅ Файлы синхронизированы"
echo ""

# Настройка на сервере
echo "⚙️ Настройка на сервере..."
ssh $SERVER << EOF
cd ~/bots/finance_bot

# Создаем venv если нет
if [ ! -d ".venv" ]; then
    echo "📦 Создаю виртуальное окружение..."
    python3 -m venv .venv
fi

# Активируем venv и устанавливаем зависимости
echo "📦 Устанавливаю зависимости..."
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Делаем скрипты исполняемыми
chmod +x run.sh watchdog.sh check_bot.sh watch_logs.sh sync_to_server.sh check_and_restart.sh init_accounts.py reset_data.py 2>/dev/null || true
chmod +x scripts/*.sh 2>/dev/null || true

# Создаем директории для логов
mkdir -p logs

echo "✅ Настройка завершена"
EOF

echo ""
echo "🔄 Перезапуск бота на сервере..."
ssh $SERVER << EOF
cd ~/bots/finance_bot

# Останавливаем старый процесс
pkill -9 -f 'bot.main' 2>/dev/null || true
sleep 2

# Запускаем через watchdog
if [ -f watchdog.sh ]; then
    pkill -f 'watchdog.sh' 2>/dev/null || true
    sleep 1
    nohup ./watchdog.sh > logs/watchdog.log 2>&1 &
    echo "✅ Watchdog запущен"
    sleep 3
    tail -20 logs/watchdog.log
else
    # Если нет watchdog, запускаем напрямую
    mkdir -p logs
    nohup ./run.sh > logs/bot.log 2>&1 &
    echo \$! > logs/bot.pid
    echo "✅ Бот запущен, PID:" \$(cat logs/bot.pid)
    sleep 2
    tail -20 logs/bot.log
fi
EOF

echo ""
echo "✅ Деплой завершен!"
echo ""
echo "📋 Проверка статуса:"
ssh $SERVER "cd ~/bots/finance_bot && ./check_bot.sh"
