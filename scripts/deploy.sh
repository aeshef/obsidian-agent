#!/usr/bin/env bash
# Единый деплой монорепо obsidian-agent (серверная структура: $SERVER_BOTS/<component>).
#
#   ./scripts/deploy.sh --component all
#   ./scripts/deploy.sh --prod                    # patch .env + deploy all + unified restart (legacy bots без рестарта)
#   ./scripts/deploy.sh --prod --install-deps
#   ./scripts/deploy.sh --prod --legacy-bots      # legacy режим: рестартовать finance/knowledge/planning тоже
#   ./scripts/deploy.sh --patch-agent-env         # только ключи agent platform на VPS
#   ./scripts/deploy.sh --restart-unified         # только unified_bot (nohup)
#
# Флаги:
#   --component <name>   можно указать несколько раз; all = shared + боты + unified_bot + config/agent
#   --prod               полный prod-выкат (см. выше)
#   --patch-agent-env    дописать TELEGRAM_UNIFIED_BOT_TOKEN, SYNTH_*, MEMORY_*, AGENT_* в server .env
#   --restart-unified    перезапуск unified_bot после деплоя (или отдельно)
#   --legacy-bots        при --prod перезапускать legacy polling ботов вместе с unified
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
# shellcheck source=scripts/lib/sh_msg.sh
source "$MONOREPO/scripts/lib/sh_msg.sh"
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
LEGACY_BOTS=0
DEPLOY_VERIFY_WAIT="${DEPLOY_VERIFY_WAIT:-15}"
RESTARTED=()
DEPLOYED_COMPONENTS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --component)
      IFS=',' read -r -a _comp_parts <<< "$2"
      for _cp in "${_comp_parts[@]}"; do
        _cp="${_cp#"${_cp%%[![:space:]]*}"}"
        _cp="${_cp%"${_cp##*[![:space:]]}"}"
        [ -n "$_cp" ] && COMPONENTS+=("$_cp")
      done
      unset _comp_parts _cp
      shift 2
      ;;
    --no-restart) NO_RESTART=1; shift;;
    --install-deps) INSTALL_DEPS=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --prod) PROD=1; PATCH_AGENT_ENV=1; RESTART_UNIFIED=1; shift;;
    --patch-agent-env) PATCH_AGENT_ENV=1; shift;;
    --restart-unified) RESTART_UNIFIED=1; shift;;
    --legacy-bots) LEGACY_BOTS=1; shift;;
    *) echo "$(sh_msgf scripts.deploy.unknown_flag "{\"flag\":\"$1\"}")"; exit 2;;
  esac
done

EXCLUDES_BASE=(
  --exclude='.git' --exclude='.DS_Store' --exclude='__pycache__/' --exclude='*.pyc'
  --exclude='venv/' --exclude='.venv/' --exclude='.venv' --exclude='venv' --exclude='.cache/'
  --exclude='docs/' --exclude='README.md'
  --exclude='logs/' --exclude='data/' --exclude='.env'
  --exclude='*.db' --exclude='*.db-shm' --exclude='*.db-wal'
  --exclude='config/author_context.txt'
  --exclude='config/initial_accounts.yaml' --exclude='config/user_context.md'
  --exclude='config/badge.yaml' --exclude='config/badge_import_*.yaml' --exclude='config/badge_append_*.yaml' --exclude='config/recover_session_*.yaml'
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
  --include='config/prompts/*.example.txt'
  --exclude='config/prompts/*.txt'
)

# knowledge_bot: prod query_*.txt с локали; *.example.txt — comment-stubs из git
KNOWLEDGE_PROMPT_RULES=(
  --include='config/prompts/*.example.txt'
  --include='config/prompts/query_preselect.txt'
  --include='config/prompts/query_select.txt'
  --include='config/prompts/query_answer.txt'
  --exclude='config/prompts/*.txt'
)

# Файлы, чья контрольная сумма сверяется после deploy (относительно $SERVER_BOTS)
DEPLOY_VERIFY_PATHS=(
  shared/capabilities/profile.py
  shared/constants.py
  shared/llm.py
  knowledge_bot/services/extract/__init__.py
  knowledge_bot/core/llm.py
  planning_bot/core/llm.py
  planning_bot/app/keyboards.py
  knowledge_bot/app/agent_tools.py
  knowledge_bot/app/save_note.py
  knowledge_bot/app/handlers/modes.py
  knowledge_bot/services/query/__init__.py
  knowledge_bot/services/query/brain_query.py
  knowledge_bot/services/query/note_lookup.py
  shared/agent/app.py
  shared/agent/router.py
  shared/telegram/kb_media.py
  unified_bot/host/constants.py
  unified_bot/host/knowledge_dispatch.py
  unified_bot/host/wire.py
  knowledge_bot/app/register_handlers.py
  finance_bot/bot/services/transactions/core.py
  finance_bot/bot/services/nlu_parser.py
  finance_bot/bot/handlers/transactions/__init__.py
  finance_bot/bot/handlers/transactions/states.py
  finance_bot/bot/handlers/transactions/nlu.py
)

# config/agent: prompts/*.txt — локальный prod (gitignore); prompts/*.example.txt — шаблон в git.
# Локальные *.yaml — prod; *.example.yaml — шаблон.
AGENT_PROMPT_RULES=(
  --include='prompts/'
  --include='prompts/*.txt'
  --include='prompts/*.example.txt'
  --exclude='prompts/*'
)

AGENT_EXCLUDES=(
  "${EXCLUDES_BASE[@]}"
  "${AGENT_PROMPT_RULES[@]}"
  --exclude='user_profile.md'
)

# Keep long remote pip/venv sessions alive; bare ssh hung on ensure_bot_venv.
DEPLOY_SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=20 -o ServerAliveCountMax=12)

ssh_check() {
  ssh "${DEPLOY_SSH_OPTS[@]}" -o ConnectTimeout=5 "$SERVER" "echo ok" >/dev/null 2>&1 || { echo "$(sh_msgf scripts.deploy.ssh_failed "{\"server\":\"$SERVER\"}")"; exit 1; }
}

deploy_ssh() {
  ssh "${DEPLOY_SSH_OPTS[@]}" "$SERVER" "$@"
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
    deploy_ssh "mkdir -p '$SERVER_BOTS/$name'"
  fi
  echo "🔄 rsync $name → $dst"
  rsync $flags "${AGENT_EXCLUDES[@]}" "$src" "$dst"
}

install_deps() {
  local name="$1"
  case "$name" in
    shared|unified_bot) return 0 ;;
  esac
  [ "$INSTALL_DEPS" = 1 ] || return 0
  echo "📦 ensure .venv + pip install ($name)"
  [ -f "$MONOREPO/constraints.txt" ] && rsync -az "$MONOREPO/constraints.txt" "$SERVER:$SERVER_BOTS/constraints.txt"
  deploy_ssh "bash $SERVER_BOTS/scripts/ensure_bot_venv.sh $name --recreate"
}

ensure_venv_link() {
  local name="$1"
  deploy_ssh "bash $SERVER_BOTS/scripts/ensure_bot_venv.sh $name" 2>/dev/null || true
}

_restart_bot_remote() {
  local name="$1" bot_pattern="$2"
  deploy_ssh "set -e
    cd $SERVER_BOTS/$name
    pkill -f '$bot_pattern' 2>/dev/null || true
    sleep 2
    if [ -f $SERVER_BOTS/scripts/start_watchdog_detached.sh ]; then
      bash $SERVER_BOTS/scripts/start_watchdog_detached.sh $SERVER_BOTS/$name
    else
      echo '  skip: no start_watchdog_detached.sh; use deploy.sh --restart-unified'
    fi
    echo restarted $name"
  RESTARTED+=("$name")
}

restart_comp() {
  local name="$1"
  [ "$NO_RESTART" = 0 ] || { echo "⏭  $name: --no-restart"; return 0; }
  [ "$DRYRUN" = 0 ] || { echo "$(sh_msgf scripts.deploy.dry_run_skip "{\"name\":\"$name\"}")"; return 0; }
  echo "🔁 restart $name"
  case "$name" in
    finance_bot)   _restart_bot_remote finance_bot 'bot.main';;
    knowledge_bot) _restart_bot_remote knowledge_bot 'start_bot.py';;
    planning_bot)  _restart_bot_remote planning_bot 'planning_bot.app.main';;
    shared) echo "  $(sh_msg scripts.deploy.shared_no_restart)";;
  esac
}

deploy_agent_platform_paths() {
  rsync_agent_paths "config/agent"
  rsync_agent_paths "unified_bot"
  if [ "$DRYRUN" = 0 ]; then
    echo "📋 ensure config/agent + prompts on server..."
    common_ssh "cd '${SERVER_BOTS}' && set -a && [ -f .env ] && . ./.env; set +a && bash scripts/ensure_bot_prompts.sh && bash scripts/setup_agent_config.sh && bash scripts/ensure_hubs_registry.sh" || true
    common_ssh "cd '${SERVER_BOTS}' && set -a && [ -f .env ] && . ./.env; set +a && PYTHONPATH='${SERVER_BOTS}' python3 scripts/seed_planning_prompts.py" 2>/dev/null || true
  fi
}

verify_deploy_checksums() {
  [ "$DRYRUN" = 1 ] && return 0
  local rel lc rc missing=0
  local deployed=("$@")
  if [ "${#deployed[@]}" -eq 0 ]; then
    echo "$(sh_msg scripts.deploy.verify_no_components)"
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
    rc="$(deploy_ssh "test -f '$remote_f' && shasum -a 256 '$remote_f' | awk '{print \$1}'" 2>/dev/null || true)"
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
    echo "$(sh_msg scripts.deploy.verify_failed)" >&2
    exit 1
  fi
  echo "✅ deploy checksum verify OK"
}

sync_repo_config_remote() {
  local cfg="$MONOREPO/config"
  [ -d "$cfg" ] || return 0
  [ "$DRYRUN" = 1 ] && { echo "dry-run: sync config/*.yaml.example"; return 0; }
  echo "📋 sync repo config examples → $SERVER:$SERVER_BOTS/config/"
  deploy_ssh "mkdir -p '$SERVER_BOTS/config'"
  for f in "$cfg"/*.yaml.example; do
    [ -f "$f" ] || continue
    rsync -az "$f" "$SERVER:$SERVER_BOTS/config/"
  done
  if [ -d "$MONOREPO/vault-templates" ]; then
    rsync -az "$MONOREPO/vault-templates/" "$SERVER:$SERVER_BOTS/vault-templates/"
    echo "  ↑ vault-templates/"
  fi
  # vault_paths.yaml is author-specific (gitignored); server materializes from locale example via ensure_repo_config.sh
  for prod in domain_messages.en.yaml domain_messages.ru.yaml messages.en.yaml messages.ru.yaml domain_messages.yaml vault_paths.yaml; do
    [ -f "$cfg/$prod" ] || continue
    rsync -az "$cfg/$prod" "$SERVER:$SERVER_BOTS/config/"
    echo "  ↑ prod $prod"
  done
  deploy_ssh "AGENT_LOCALE='${AGENT_LOCALE:-en}' bash '$SERVER_BOTS/scripts/ensure_repo_config.sh' '$SERVER_BOTS'" \
    || { echo "⚠️  ensure_repo_config.sh failed (check server config/)" >&2; return 1; }
}

rsync_server_scripts() {
  local flags="-avz --checksum"
  [ "$DRYRUN" = 1 ] && flags="-navz"
  echo "🔄 rsync server scripts → $SERVER:$SERVER_BOTS/scripts/"
  rsync $flags \
    --exclude='obsidian_sync.sh' \
    --exclude='export_mobile_vault.sh' \
    --exclude='install_launchagent.sh' \
    "$MONOREPO/scripts/" "$SERVER:$SERVER_BOTS/scripts/"
  rsync -az "$MONOREPO/scripts/lib/" "$SERVER:$SERVER_BOTS/scripts/lib/"
  deploy_ssh "chmod +x $SERVER_BOTS/scripts/*.sh $SERVER_BOTS/scripts/lib/*.sh 2>/dev/null || true"
}

sync_bot_prompts_optional() {
  local bot="$1"
  local dir="$MONOREPO/$bot/config/prompts"
  [ "$DRYRUN" = 1 ] && return 0
  [ -d "$dir" ] || return 0
  local n=0
  for f in "$dir"/*.txt; do
    [ -f "$f" ] || continue
    case "$f" in *.example.txt) continue ;; esac
    rsync -az "$f" "$SERVER:$SERVER_BOTS/$bot/config/prompts/"
    n=$((n + 1))
  done
  [ "$n" -gt 0 ] && echo "$(sh_msgf scripts.deploy.rsync_prompts "{\"bot\":\"$bot\",\"count\":\"$n\"}")"
}

sync_badge_yaml_optional() {
  local local_badge="$MONOREPO/finance_bot/config/badge.yaml"
  [ "$DRYRUN" = 1 ] && return 0
  [ -f "$local_badge" ] || return 0
  echo "$(sh_msgf scripts.deploy.rsync_badge "{\"server\":\"$SERVER\"}")"
  rsync -az "$local_badge" "$SERVER:$SERVER_BOTS/finance_bot/config/badge.yaml"
}

deploy_one() {
  local name="$1"
  local restart_mode="${2:-auto}"
  echo "──────── deploy: $name ────────"
  rsync_comp "$name"
  [ "$name" = finance_bot ] && { sync_badge_yaml_optional; sync_bot_prompts_optional finance_bot; }
  [ "$name" = knowledge_bot ] && sync_bot_prompts_optional knowledge_bot
  [ "$name" = planning_bot ] && sync_bot_prompts_optional planning_bot
  ensure_venv_link "$name"
  install_deps "$name"
  if [ "$restart_mode" = "skip" ]; then
    echo "⏭  $name: restart skipped by mode"
  else
    restart_comp "$name"
  fi
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
  out="$(deploy_ssh "set +e
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
    echo "$(sh_msg scripts.deploy.post_deploy_failed)" >&2
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
  rsync_server_scripts
  sync_repo_config_remote
  [ "$DRYRUN" = 1 ] && { echo "dry-run: restart unified_bot"; exit 0; }
  [ "$NO_RESTART" = 1 ] && { echo "$(sh_msg scripts.deploy.no_restart_unified)"; exit 0; }
  restart_unified_bot_remote
  verify_unified_bot_remote
  exit $?
fi

# ── Основной deploy ───────────────────────────────────────────────
if [ "$PROD" = 1 ]; then
  echo "════════════════ deploy --prod ════════════════"
fi

ssh_check
if [ "$DRYRUN" = 0 ]; then
  echo "📥 pull prod prompts from server (keep local non-stub)..."
  bash "$MONOREPO/scripts/pull_prompts_from_server.sh" 2>/dev/null || true
  export PYTHONPATH="${MONOREPO}${PYTHONPATH:+:$PYTHONPATH}"
  _DEP_PY="$(common_resolve_python_usable "$MONOREPO/finance_bot")"
  "$_DEP_PY" "$MONOREPO/scripts/seed_planning_prompts.py" 2>/dev/null || true
  bash "$MONOREPO/scripts/ensure_hubs_registry.sh" 2>/dev/null || true
fi

rsync_server_scripts

if [ "$PATCH_AGENT_ENV" = 1 ] || [ "$PROD" = 1 ]; then
  patch_agent_env_remote "$DRYRUN" || exit 1
fi

if [ "$PROD" = 1 ]; then
  deploy_agent_platform_paths
fi

sync_repo_config_remote
[ "$DRYRUN" = 0 ] && [ -f "$MONOREPO/scripts/cleanup_server_stale.sh" ] && "$MONOREPO/scripts/cleanup_server_stale.sh" 2>/dev/null || true

if [ "${#COMPONENTS[@]}" -eq 0 ]; then
  COMPONENTS=(all)
fi

_want_verify=0
_deploy_all=0
_agent_deployed=0
for c in "${COMPONENTS[@]}"; do
  case "$c" in
    all) _deploy_all=1 ;;
    config)
      # config/ уже синхронизирован выше (sync_repo_config_remote); отдельный rsync не нужен
      ;;
    shared|finance_bot|knowledge_bot|planning_bot|unified_bot) ;;
    *) echo "$(sh_msgf scripts.deploy.unknown_component "{\"component\":\"$c\"}")"; exit 2 ;;
  esac
done

# shared/unified тянут knowledge ingest (register_handlers, save_note, …)
if [ "$_deploy_all" = 0 ]; then
  _has_kb=0 _needs_kb=0
  for c in "${COMPONENTS[@]}"; do
    [ "$c" = knowledge_bot ] && _has_kb=1
    case "$c" in shared|unified_bot) _needs_kb=1 ;; esac
  done
  if [ "$_needs_kb" = 1 ] && [ "$_has_kb" = 0 ]; then
    echo "$(sh_msg scripts.deploy.knowledge_deps_note)"
    COMPONENTS+=(knowledge_bot)
  fi
fi

if [ "$_deploy_all" = 1 ]; then
  _legacy_restart_mode="auto"
  if [ "$PROD" = 1 ] && [ "$LEGACY_BOTS" = 0 ]; then
    _legacy_restart_mode="skip"
    echo "ℹ️ --prod: legacy bot restarts disabled (use --legacy-bots to enable)"
  fi
  deploy_one shared
  deploy_one finance_bot "$_legacy_restart_mode"
  deploy_one knowledge_bot "$_legacy_restart_mode"
  deploy_one planning_bot "$_legacy_restart_mode"
  deploy_agent_platform_paths
  _want_verify=1
else
  _legacy_restart_mode="auto"
  if { [ "$PROD" = 1 ] || [ "$RESTART_UNIFIED" = 1 ]; } && [ "$LEGACY_BOTS" = 0 ]; then
    _legacy_restart_mode="skip"
    echo "ℹ️ partial deploy: legacy bot restarts skipped (unified host; use --legacy-bots to enable)"
  fi
  for c in "${COMPONENTS[@]}"; do
    case "$c" in
      shared)        deploy_one shared; _want_verify=1 ;;
      finance_bot)   deploy_one finance_bot "$_legacy_restart_mode"; _want_verify=1 ;;
      knowledge_bot) deploy_one knowledge_bot "$_legacy_restart_mode"; _want_verify=1 ;;
      planning_bot)  deploy_one planning_bot "$_legacy_restart_mode" ;;
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
echo "$(sh_msgf scripts.deploy.deploy_done "{\"components\":\"${_comp_list:-all}\",\"restart\":\"$([ $NO_RESTART = 1 ] && echo no || echo yes)\"}")"
if [ "$DRYRUN" = 0 ]; then
  echo "📋 ensure bot prompts on server (missing .txt from examples)..."
  deploy_ssh "cd '$SERVER_BOTS' && bash scripts/ensure_bot_prompts.sh --warn-stubs" 2>/dev/null || true
fi
if [ "$DRYRUN" = 0 ] && { [ "$_deploy_all" = 1 ] || printf '%s\n' "${COMPONENTS[@]}" | grep -qx knowledge_bot; }; then
  echo "🏷 ensure tags.txt JSON prompt on server..."
  deploy_ssh "python3 $SERVER_BOTS/scripts/ensure_tags_prompt.py \
    --tags $SERVER_BOTS/knowledge_bot/config/prompts/tags.txt \
    --example $SERVER_BOTS/knowledge_bot/config/prompts/tags.example.txt" 2>/dev/null || true
fi
verify_bots

if [ "$RESTART_UNIFIED" = 1 ] && [ "$NO_RESTART" = 0 ] && [ "$DRYRUN" = 0 ]; then
  _stop_legacy=0
  if [ "$_deploy_all" = 1 ] || [ "$LEGACY_BOTS" = 1 ]; then
    _stop_legacy=1
  fi
  restart_unified_bot_remote "$_stop_legacy"
  verify_unified_bot_remote
fi
