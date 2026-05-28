#!/usr/bin/env bash
# Единый деплой монорепо obsidian-agent (серверная структура: $SERVER_BOTS/<component>).
#
#   ./deploy.sh --component shared --no-restart        # только shared/, без рестартов (безопасно)
#   ./deploy.sh --component finance_bot --install-deps # finance + pip install + рестарт
#   ./deploy.sh --component all                        # все компоненты
#
# Флаги:
#   --component <name>   shared | finance_bot | knowledge_bot | planning_bot | all  (default all)
#   --no-restart         только rsync, без перезапуска бота
#   --install-deps       pip install -r requirements.txt на сервере в venv компонента
#   --dry-run            rsync -n (показать что будет синкнуто, ничего не менять)
#
# НИКОГДА не перезаписывает на сервере: .env, *.db, logs/, data/, личные config (см. EXCLUDES).
set -uo pipefail

MONOREPO="${MONOREPO:-$(cd "$(dirname "$0")/.." && pwd)}"
if [ -f "$MONOREPO/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$MONOREPO/.env"
  set +a
fi

SERVER="${SERVER:?Set SERVER in .env (SSH host for deploy)}"
SERVER_BOTS="${SERVER_BOTS:-/opt/obsidian-bots}"
COMPONENT="all"
NO_RESTART=0
INSTALL_DEPS=0
DRYRUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --component) COMPONENT="$2"; shift 2;;
    --no-restart) NO_RESTART=1; shift;;
    --install-deps) INSTALL_DEPS=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    *) echo "Неизвестный флаг: $1"; exit 2;;
  esac
done

# Личные/серверные данные — никогда не трогаем через rsync
EXCLUDES=(
  --exclude='.git' --exclude='.DS_Store' --exclude='__pycache__/' --exclude='*.pyc'
  --exclude='venv/' --exclude='.venv/' --exclude='.cache/'
  --exclude='logs/' --exclude='data/' --exclude='.env'
  --exclude='*.db' --exclude='*.db-shm' --exclude='*.db-wal'
  --exclude='config/prompts/*.txt' --exclude='config/author_context.txt'
  --exclude='config/initial_accounts.yaml' --exclude='config/user_context.md'
  --exclude='config/badge.yaml' --exclude='config/badge_import_*.yaml'
  --exclude='CHAT_ID.txt' --exclude='goals_context.md'
)

ssh_check() {
  ssh -o ConnectTimeout=5 "$SERVER" "echo ok" >/dev/null 2>&1 || { echo "❌ SSH $SERVER не отвечает"; exit 1; }
}

rsync_comp() {
  local name="$1"
  local src="$MONOREPO/$name/"
  local dst="$SERVER:$SERVER_BOTS/$name/"
  local flags="-avz"
  [ "$DRYRUN" = 1 ] && flags="-navz"
  echo "🔄 rsync $name → $dst"
  rsync $flags "${EXCLUDES[@]}" "$src" "$dst"
}

install_deps() {
  local name="$1" vdir="$2"
  [ "$INSTALL_DEPS" = 1 ] || return 0
  echo "📦 pip install ($name) под общим constraints.txt"
  # доставляем единый потолок версий в корень bots
  [ -f "$MONOREPO/constraints.txt" ] && rsync -az "$MONOREPO/constraints.txt" "$SERVER:$SERVER_BOTS/constraints.txt"
  ssh "$SERVER" "cd $SERVER_BOTS/$name && { [ -d $vdir ] || python3 -m venv $vdir; }; $vdir/bin/pip install -q --upgrade pip; CONS=''; [ -f ../constraints.txt ] && CONS='-c ../constraints.txt'; $vdir/bin/pip install -q -r requirements.txt \$CONS"
}

restart_comp() {
  local name="$1"
  [ "$NO_RESTART" = 0 ] || { echo "⏭  $name: --no-restart"; return 0; }
  [ "$DRYRUN" = 0 ] || { echo "⏭  $name: --dry-run (без рестарта)"; return 0; }
  echo "🔁 restart $name"
  case "$name" in
    finance_bot)
      ssh "$SERVER" "cd $SERVER_BOTS/finance_bot && pkill -9 -f 'bot.main' 2>/dev/null; pkill -f 'scripts/watchdog.sh' 2>/dev/null; sleep 2; nohup ./scripts/watchdog.sh > logs/watchdog.log 2>&1 & sleep 3; echo restarted";;
    knowledge_bot)
      ssh "$SERVER" "cd $SERVER_BOTS/knowledge_bot && pkill -f 'start_bot.py' 2>/dev/null; pkill -f 'scripts/watchdog.sh' 2>/dev/null; sleep 2; nohup ./scripts/watchdog.sh > logs/watchdog.log 2>&1 & sleep 3; echo restarted";;
    planning_bot)
      ssh "$SERVER" "cd $SERVER_BOTS/planning_bot && pkill -f 'planning_bot.app.bot' 2>/dev/null; pkill -f 'scripts/watchdog.sh' 2>/dev/null; sleep 2; nohup ./scripts/watchdog.sh > logs/watchdog.log 2>&1 & sleep 3; echo restarted";;
    shared) echo "  shared не требует рестарта";;
  esac
}

deploy_one() {
  local name="$1" vdir="$2"
  echo "──────── deploy: $name ────────"
  rsync_comp "$name"
  install_deps "$name" "$vdir"
  restart_comp "$name"
}

ssh_check
rsync_server_scripts
case "$COMPONENT" in
  shared)        deploy_one shared "";;
  finance_bot)   deploy_one finance_bot .venv;;
  knowledge_bot) deploy_one knowledge_bot venv;;
  planning_bot)  deploy_one planning_bot venv;;
  all)
    deploy_one shared ""
    deploy_one finance_bot .venv
    deploy_one knowledge_bot venv
    deploy_one planning_bot venv;;
  *) echo "Неизвестный компонент: $COMPONENT"; exit 2;;
esac

echo "✅ deploy завершён (component=$COMPONENT, restart=$([ $NO_RESTART = 1 ] && echo no || echo yes))"
echo "📋 живы ли боты:"
ssh "$SERVER" "pgrep -af 'start_bot|planning_bot|bot.main' | grep -v pgrep" || echo "(нет процессов!)"
