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
# shellcheck source=scripts/lib/common.sh
source "$MONOREPO/scripts/lib/common.sh"
common_load_env "$MONOREPO"

SERVER="${SERVER:?Set SERVER in .env (SSH host for deploy)}"
SERVER_BOTS="$(common_server_bots)"
COMPONENT="all"
NO_RESTART=0
INSTALL_DEPS=0
DRYRUN=0
DEPLOY_VERIFY_WAIT="${DEPLOY_VERIFY_WAIT:-15}"
RESTARTED=()

while [ $# -gt 0 ]; do
  case "$1" in
    --component) COMPONENT="$2"; shift 2;;
    --no-restart) NO_RESTART=1; shift;;
    --install-deps) INSTALL_DEPS=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    *) echo "Неизвестный флаг: $1"; exit 2;;
  esac
done

EXCLUDES=(
  --exclude='.git' --exclude='.DS_Store' --exclude='__pycache__/' --exclude='*.pyc'
  --exclude='venv/' --exclude='.venv/' --exclude='.venv' --exclude='venv' --exclude='.cache/'
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
  local name="$1"
  [ "$INSTALL_DEPS" = 1 ] || return 0
  echo "📦 ensure .venv + pip install ($name)"
  [ -f "$MONOREPO/constraints.txt" ] && rsync -az "$MONOREPO/constraints.txt" "$SERVER:$SERVER_BOTS/constraints.txt"
  ssh "$SERVER" "bash $SERVER_BOTS/scripts/ensure_bot_venv.sh $name --recreate"
}

ensure_venv_link() {
  local name="$1"
  ssh "$SERVER" "bash $SERVER_BOTS/scripts/ensure_bot_venv.sh $name" 2>/dev/null || true
}

_restart_bot_remote() {
  local name="$1" bot_pattern="$2"
  ssh "$SERVER" "set -e
    cd $SERVER_BOTS/$name
    pkill -f '$bot_pattern' 2>/dev/null || true
    sleep 2
    bash $SERVER_BOTS/scripts/start_watchdog_detached.sh $SERVER_BOTS/$name
    echo restarted $name"
  RESTARTED+=("$name")
}

restart_comp() {
  local name="$1"
  [ "$NO_RESTART" = 0 ] || { echo "⏭  $name: --no-restart"; return 0; }
  [ "$DRYRUN" = 0 ] || { echo "⏭  $name: --dry-run (без рестарта)"; return 0; }
  echo "🔁 restart $name"
  case "$name" in
    finance_bot)   _restart_bot_remote finance_bot 'bot.main';;
    knowledge_bot) _restart_bot_remote knowledge_bot 'start_bot.py';;
    planning_bot)  _restart_bot_remote planning_bot 'planning_bot.app.main';;
    shared) echo "  shared не требует рестарта";;
  esac
}

rsync_server_scripts() {
  local flags="-avz"
  [ "$DRYRUN" = 1 ] && flags="-navz"
  echo "🔄 rsync server scripts → $SERVER:$SERVER_BOTS/scripts/"
  rsync $flags \
    --exclude='obsidian_sync.sh' \
    --exclude='export_mobile_vault.sh' \
    --exclude='install_launchagent.sh' \
    --exclude='merge_env_from_server.sh' \
    "$MONOREPO/scripts/" "$SERVER:$SERVER_BOTS/scripts/"
  rsync -az "$MONOREPO/scripts/lib/" "$SERVER:$SERVER_BOTS/scripts/lib/"
  ssh "$SERVER" "chmod +x $SERVER_BOTS/scripts/*.sh $SERVER_BOTS/scripts/lib/*.sh 2>/dev/null || true"
}

deploy_one() {
  local name="$1"
  echo "──────── deploy: $name ────────"
  rsync_comp "$name"
  ensure_venv_link "$name"
  install_deps "$name"
  restart_comp "$name"
}

verify_bots() {
  [ "$NO_RESTART" = 1 ] && return 0
  [ "$DRYRUN" = 1 ] && return 0
  [ "${#RESTARTED[@]}" -eq 0 ] && return 0

  echo "⏳ verify bots (wait ${DEPLOY_VERIFY_WAIT}s)..."
  sleep "$DEPLOY_VERIFY_WAIT"

  local failed=0 out
  local restarted_list="${RESTARTED[*]}"
  out="$(ssh "$SERVER" "set +e
    failed=0
    for b in $restarted_list; do
      wd=\$(cat $SERVER_BOTS/\$b/logs/watchdog.pid 2>/dev/null || echo '-')
      case \$b in
        finance_bot)   pat='bot.main';;
        knowledge_bot) pat='start_bot.py';;
        planning_bot)  pat='planning_bot.app.main';;
      esac
      bot=\$(pgrep -f \"\$pat\" 2>/dev/null | head -1 || true)
      if [ -z \"\$bot\" ]; then status=DOWN; failed=1; else status=\$bot; fi
      echo \"  \$b: watchdog=\$wd bot=\$status\"
    done
    exit \$failed")" || failed=1
  echo "$out"
  if [ "$failed" -ne 0 ]; then
    echo "❌ post-deploy verify FAILED — бот(ы) не поднялись" >&2
    exit 1
  fi
  echo "✅ post-deploy verify OK"
}

ssh_check
rsync_server_scripts
[ "$DRYRUN" = 0 ] && "$MONOREPO/scripts/cleanup_server_stale.sh" 2>/dev/null || true
case "$COMPONENT" in
  shared)        deploy_one shared;;
  finance_bot)   deploy_one finance_bot;;
  knowledge_bot) deploy_one knowledge_bot;;
  planning_bot)  deploy_one planning_bot;;
  all)
    deploy_one shared
    deploy_one finance_bot
    deploy_one knowledge_bot
    deploy_one planning_bot
    ;;
  *) echo "Неизвестный компонент: $COMPONENT"; exit 2;;
esac

echo "✅ deploy завершён (component=$COMPONENT, restart=$([ $NO_RESTART = 1 ] && echo no || echo yes))"
if [ "$DRYRUN" = 0 ] && { [ "$COMPONENT" = knowledge_bot ] || [ "$COMPONENT" = all ]; }; then
  echo "🏷 ensure tags.txt JSON prompt on server..."
  ssh "$SERVER" "python3 $SERVER_BOTS/scripts/ensure_tags_prompt.py \
    --tags $SERVER_BOTS/knowledge_bot/config/prompts/tags.txt \
    --example $SERVER_BOTS/knowledge_bot/config/prompts/tags.example.txt" 2>/dev/null || true
fi
verify_bots
