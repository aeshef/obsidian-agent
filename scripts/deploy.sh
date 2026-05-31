#!/usr/bin/env bash
# Единый деплой монорепо obsidian-agent (серверная структура: $SERVER_BOTS/<component>).
#
#   ./scripts/deploy.sh --component all
#   ./scripts/deploy.sh --prod                    # patch .env + config/agent + unified_bot + all + unified restart
#   ./scripts/deploy.sh --prod --install-deps
#   ./scripts/deploy.sh --patch-agent-env         # только ключи agent platform на VPS
#   ./scripts/deploy.sh --restart-unified         # только unified_bot (nohup)
#
# Флаги:
#   --component <name>   можно указать несколько раз; all = shared + боты + unified_bot + config/agent
#   --prod               полный prod-выкат (см. выше)
#   --patch-agent-env    дописать TELEGRAM_UNIFIED_BOT_TOKEN, SYNTH_*, MEMORY_*, AGENT_* в server .env
#   --restart-unified    перезапуск unified_bot после деплоя (или отдельно)
#   --no-restart         без перезапуска ботов / unified
#   --install-deps       pip install -r requirements.txt на сервере
#   --dry-run            rsync -n
#
# НИКОГДА не перезаписывает на сервере: .env, *.db, logs/, data/, личные config (см. EXCLUDES).
set -uo pipefail

MONOREPO="${MONOREPO:-$(cd "$(dirname "$0")/.." && pwd)}"
# shellcheck source=scripts/lib/common.sh
source "$MONOREPO/scripts/lib/common.sh"
# shellcheck source=scripts/lib/deploy_agent.sh
source "$MONOREPO/scripts/lib/deploy_agent.sh"
common_load_env "$MONOREPO"

SERVER="${SERVER:?Set SERVER in .env (SSH host for deploy)}"
SERVER_BOTS="$(common_server_bots)"
COMPONENTS=()
NO_RESTART=0
INSTALL_DEPS=0
DRYRUN=0
PROD=0
PATCH_AGENT_ENV=0
RESTART_UNIFIED=0
DEPLOY_VERIFY_WAIT="${DEPLOY_VERIFY_WAIT:-15}"
RESTARTED=()
DEPLOYED_COMPONENTS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --component) COMPONENTS+=("$2"); shift 2;;
    --no-restart) NO_RESTART=1; shift;;
    --install-deps) INSTALL_DEPS=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --prod) PROD=1; PATCH_AGENT_ENV=1; RESTART_UNIFIED=1; shift;;
    --patch-agent-env) PATCH_AGENT_ENV=1; shift;;
    --restart-unified) RESTART_UNIFIED=1; shift;;
    *) echo "Неизвестный флаг: $1"; exit 2;;
  esac
done

EXCLUDES_BASE=(
  --exclude='.git' --exclude='.DS_Store' --exclude='__pycache__/' --exclude='*.pyc'
  --exclude='venv/' --exclude='.venv/' --exclude='.venv' --exclude='venv' --exclude='.cache/'
  --exclude='logs/' --exclude='data/' --exclude='.env'
  --exclude='*.db' --exclude='*.db-shm' --exclude='*.db-wal'
  --exclude='config/author_context.txt'
  --exclude='config/initial_accounts.yaml' --exclude='config/user_context.md'
  --exclude='config/badge.yaml' --exclude='config/badge_import_*.yaml'
  --exclude='CHAT_ID.txt' --exclude='goals_context.md'
)

# finance/planning: личные prompts/*.txt не перезаписываем; .example.txt — деплоим
PROMPT_TXT_EXCLUDE=(
  --include='config/prompts/*.example.txt'
  --exclude='config/prompts/*.txt'
)

# finance_bot: те же правила + явный nlu_prompt.txt если есть локально
FINANCE_PROMPT_RULES=(
  --include='config/prompts/nlu_prompt.txt'
  --include='config/prompts/router_prompt.txt'
  --include='config/prompts/*.example.txt'
  --exclude='config/prompts/*.txt'
)

# knowledge_bot: только query_*.txt из prompts (tags.txt и пр. — отдельно ensure_tags)
KNOWLEDGE_PROMPT_RULES=(
  --include='config/prompts/query_preselect.txt'
  --include='config/prompts/query_select.txt'
  --include='config/prompts/query_answer.txt'
  --exclude='config/prompts/*.txt'
)

# Файлы, чья контрольная сумма сверяется после deploy (относительно $SERVER_BOTS)
DEPLOY_VERIFY_PATHS=(
  knowledge_bot/app/agent_tools.py
  knowledge_bot/app/save_note.py
  knowledge_bot/app/handlers/modes.py
  knowledge_bot/app/direct_read.py
  knowledge_bot/services/query/brain_query.py
  knowledge_bot/services/query/note_lookup.py
  shared/agent/app.py
  shared/telegram/kb_media.py
  shared/telegram/host/knowledge_dispatch.py
  shared/telegram/host/wire.py
  knowledge_bot/app/register_handlers.py
  finance_bot/bot/services/transactions/core.py
  finance_bot/bot/services/nlu_parser.py
  finance_bot/bot/handlers/transactions/nlu.py
)

AGENT_EXCLUDES=(
  "${EXCLUDES_BASE[@]}"
  "${PROMPT_TXT_EXCLUDE[@]}"
  --exclude='user_profile.md'
)

ssh_check() {
  ssh -o ConnectTimeout=5 "$SERVER" "echo ok" >/dev/null 2>&1 || { echo "❌ SSH $SERVER не отвечает"; exit 1; }
}

rsync_comp() {
  local name="$1"
  local src="$MONOREPO/$name/"
  local dst="$SERVER:$SERVER_BOTS/$name/"
  local flags="-avz --checksum"
  [ "$DRYRUN" = 1 ] && flags="-navz"
  local excludes=("${EXCLUDES_BASE[@]}")
  if [ "$name" = knowledge_bot ]; then
    excludes+=("${KNOWLEDGE_PROMPT_RULES[@]}")
  elif [ "$name" = finance_bot ]; then
    excludes+=("${FINANCE_PROMPT_RULES[@]}")
  else
    excludes+=("${PROMPT_TXT_EXCLUDE[@]}")
  fi
  echo "🔄 rsync $name → $dst"
  rsync $flags "${excludes[@]}" "$src" "$dst"
}

rsync_agent_paths() {
  local name="$1"
  local src="$MONOREPO/$name/"
  local dst="$SERVER:$SERVER_BOTS/$name/"
  local flags="-avz --checksum"
  [ "$DRYRUN" = 1 ] && flags="-navz"
  if [ "$DRYRUN" = 0 ]; then
    ssh "$SERVER" "mkdir -p '$SERVER_BOTS/$name'"
  fi
  echo "🔄 rsync $name → $dst"
  rsync $flags "${AGENT_EXCLUDES[@]}" "$src" "$dst"
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

deploy_agent_platform_paths() {
  rsync_agent_paths "config/agent"
  rsync_agent_paths "unified_bot"
  if [ "$DRYRUN" = 0 ]; then
    echo "📋 ensure config/agent from *.example on server..."
    common_ssh "cd '${SERVER_BOTS}' && bash scripts/setup_agent_config.sh" || true
  fi
}

verify_deploy_checksums() {
  [ "$DRYRUN" = 1 ] && return 0
  local rel lc rc missing=0
  local deployed=("$@")
  if [ "${#deployed[@]}" -eq 0 ]; then
    echo "⏭ verify checksums: нет задеплоенных компонентов"
    return 0
  fi
  echo "🔍 verify deploy checksums (${deployed[*]})..."
  for rel in "${DEPLOY_VERIFY_PATHS[@]}"; do
    local comp="${rel%%/*}"
    local match=0 c
    for c in "${deployed[@]}"; do
      if [ "$c" = "$comp" ]; then
        match=1
        break
      fi
    done
    if [ "$match" -eq 0 ]; then
      echo "  skip (component not deployed): $rel"
      continue
    fi
    local local_f="$MONOREPO/$rel"
    local remote_f="$SERVER_BOTS/$rel"
    if [ ! -f "$local_f" ]; then
      echo "  skip (no local): $rel"
      continue
    fi
    lc="$(shasum -a 256 "$local_f" | awk '{print $1}')"
    rc="$(ssh "$SERVER" "test -f '$remote_f' && shasum -a 256 '$remote_f' | awk '{print \$1}'" 2>/dev/null || true)"
    if [ -z "$rc" ]; then
      echo "  ❌ missing on server: $rel"
      missing=1
      continue
    fi
    if [ "$lc" != "$rc" ]; then
      echo "  ❌ checksum mismatch: $rel"
      echo "     local:  $lc"
      echo "     remote: $rc"
      missing=1
    else
      echo "  ✓ $rel"
    fi
  done
  if [ "$missing" -ne 0 ]; then
    echo "❌ deploy verify FAILED — на сервере старая или отсутствующая версия файлов" >&2
    exit 1
  fi
  echo "✅ deploy checksum verify OK"
}

rsync_server_scripts() {
  local flags="-avz --checksum"
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
  DEPLOYED_COMPONENTS+=("$name")
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

# ── Режимы только patch / только unified ─────────────────────────
if [ "$PATCH_AGENT_ENV" = 1 ] && [ "$PROD" = 0 ] && [ "$RESTART_UNIFIED" = 0 ]; then
  ssh_check
  patch_agent_env_remote "$DRYRUN"
  exit $?
fi

# Только перезапуск, без rsync (если не переданы --component / --prod)
if [ "$RESTART_UNIFIED" = 1 ] && [ "$PROD" = 0 ] && [ "$PATCH_AGENT_ENV" = 0 ] && [ "${#COMPONENTS[@]}" -eq 0 ]; then
  ssh_check
  [ "$DRYRUN" = 1 ] && { echo "dry-run: restart unified_bot"; exit 0; }
  [ "$NO_RESTART" = 1 ] && { echo "⏭ --no-restart: unified не перезапускаем"; exit 0; }
  restart_unified_bot_remote
  exit $?
fi

# ── Основной deploy ───────────────────────────────────────────────
if [ "$PROD" = 1 ]; then
  echo "════════════════ deploy --prod ════════════════"
fi

ssh_check

if [ "$PATCH_AGENT_ENV" = 1 ]; then
  patch_agent_env_remote "$DRYRUN" || exit 1
fi

if [ "$PROD" = 1 ]; then
  deploy_agent_platform_paths
fi

rsync_server_scripts
[ "$DRYRUN" = 0 ] && "$MONOREPO/scripts/cleanup_server_stale.sh" 2>/dev/null || true

if [ "${#COMPONENTS[@]}" -eq 0 ]; then
  COMPONENTS=(all)
fi

_want_verify=0
_deploy_all=0
_agent_deployed=0
for c in "${COMPONENTS[@]}"; do
  case "$c" in
    all) _deploy_all=1 ;;
    shared|finance_bot|knowledge_bot|planning_bot|unified_bot) ;;
    *) echo "Неизвестный компонент: $c"; exit 2 ;;
  esac
done

if [ "$_deploy_all" = 1 ]; then
  deploy_one shared
  deploy_one finance_bot
  deploy_one knowledge_bot
  deploy_one planning_bot
  deploy_agent_platform_paths
  _want_verify=1
else
  for c in "${COMPONENTS[@]}"; do
    case "$c" in
      shared)        deploy_one shared; _want_verify=1 ;;
      finance_bot)   deploy_one finance_bot; _want_verify=1 ;;
      knowledge_bot) deploy_one knowledge_bot; _want_verify=1 ;;
      planning_bot)  deploy_one planning_bot ;;
      unified_bot)
        if [ "$_agent_deployed" = 0 ]; then
          deploy_agent_platform_paths
          _agent_deployed=1
        fi
        _want_verify=1
        ;;
    esac
  done
  # unified_bot читает shared + knowledge — при частичном deploy подтягиваем platform
  for c in "${COMPONENTS[@]}"; do
    case "$c" in
      shared|knowledge_bot)
        if [ "$_agent_deployed" = 0 ]; then
          deploy_agent_platform_paths
          _agent_deployed=1
        fi
        _want_verify=1
        break
        ;;
    esac
  done
fi

if [ "$_want_verify" = 1 ]; then
  verify_deploy_checksums "${DEPLOYED_COMPONENTS[@]}"
fi

_comp_list="${COMPONENTS[*]}"
echo "✅ deploy завершён (components=${_comp_list:-all}, restart=$([ $NO_RESTART = 1 ] && echo no || echo yes))"
if [ "$DRYRUN" = 0 ] && { [ "$_deploy_all" = 1 ] || printf '%s\n' "${COMPONENTS[@]}" | grep -qx knowledge_bot; }; then
  echo "🏷 ensure tags.txt JSON prompt on server..."
  ssh "$SERVER" "python3 $SERVER_BOTS/scripts/ensure_tags_prompt.py \
    --tags $SERVER_BOTS/knowledge_bot/config/prompts/tags.txt \
    --example $SERVER_BOTS/knowledge_bot/config/prompts/tags.example.txt" 2>/dev/null || true
fi
verify_bots

if [ "$RESTART_UNIFIED" = 1 ] && [ "$NO_RESTART" = 0 ] && [ "$DRYRUN" = 0 ]; then
  restart_unified_bot_remote
fi
