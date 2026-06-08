# shellcheck shell=bash
# Функции agent-platform deploy (source из deploy.sh).

patch_agent_env_remote() {
  local dry="${1:-0}"
  local root="${MONOREPO:?}"
  local bots="${SERVER_BOTS:?}"

  # shellcheck source=scripts/lib/common.sh
  source "$root/scripts/lib/common.sh"
  common_load_env "$root"
  common_require_server

  local remote_env="${bots}/.env"
  local token="${TELEGRAM_UNIFIED_BOT_TOKEN:-}"
  local synth="${SYNTH_ENABLED:-1}"
  local synth_domains="${SYNTH_DOMAINS:-finance,planning}"
  local session_persist="${MEMORY_SESSION_PERSIST:-1}"
  local kanban_writes="${KANBAN_AGENT_WRITES:-}"
  local vault_rel_knowledge="${VAULT_REL_KNOWLEDGE:-}"
  local agent_locale="${AGENT_LOCALE:-en}"

  if [ -z "$token" ]; then
    # shellcheck source=scripts/lib/sh_msg.sh
    source "$root/scripts/lib/sh_msg.sh"
    echo "$(sh_msgf scripts.deploy_agent.token_empty "{\"path\":\"$root\"}")" >&2
    return 1
  fi

  if [ "$dry" = 1 ]; then
    echo "dry-run: patch $SERVER:$remote_env"
    printf '%s\n' \
      "TELEGRAM_UNIFIED_BOT_TOKEN=***" \
      "SYNTH_ENABLED=$synth" \
      "SYNTH_DOMAINS=$synth_domains" \
      "MEMORY_SESSION_PERSIST=$session_persist" \
      "AGENT_MEMORY_DB=$bots/memory.db" \
      "AGENT_ROOT=$bots"
    return 0
  fi

  echo "📝 patch $SERVER:$remote_env"
  common_ssh "bash -s" <<REMOTE
set -euo pipefail
REMOTE_ENV="$remote_env"
mkdir -p "\$(dirname "\$REMOTE_ENV")"
touch "\$REMOTE_ENV"
upsert() {
  local k="\$1" v="\$2"
  if grep -qE "^\${k}=" "\$REMOTE_ENV" 2>/dev/null; then
    sed -i "s|^\${k}=.*|\${k}=\${v}|" "\$REMOTE_ENV"
  else
    echo "\${k}=\${v}" >> "\$REMOTE_ENV"
  fi
}
upsert TELEGRAM_UNIFIED_BOT_TOKEN "${token}"
upsert SYNTH_ENABLED "${synth}"
upsert SYNTH_DOMAINS "${synth_domains}"
upsert MEMORY_SESSION_PERSIST "${session_persist}"
upsert AGENT_MEMORY_DB "${bots}/memory.db"
upsert AGENT_ROOT "${bots}"
upsert AGENT_LOCALE "${agent_locale}"
REMOTE
  if [ -n "$vault_rel_knowledge" ]; then
    common_ssh "bash -s" <<REMOTE_KB
set -euo pipefail
REMOTE_ENV="${remote_env}"
upsert() {
  local k="\$1" v="\$2"
  if grep -qE "^\${k}=" "\$REMOTE_ENV" 2>/dev/null; then
    sed -i "s|^\${k}=.*|\${k}=\${v}|" "\$REMOTE_ENV"
  else
    echo "\${k}=\${v}" >> "\$REMOTE_ENV"
  fi
}
upsert VAULT_REL_KNOWLEDGE "${vault_rel_knowledge}"
REMOTE_KB
    echo "✅ VAULT_REL_KNOWLEDGE=${vault_rel_knowledge} on server"
  fi
  if [ -n "$kanban_writes" ]; then
    common_ssh "bash -s" <<REMOTE2
set -euo pipefail
REMOTE_ENV="${remote_env}"
upsert() {
  local k="\$1" v="\$2"
  if grep -qE "^\${k}=" "\$REMOTE_ENV" 2>/dev/null; then
    sed -i "s|^\${k}=.*|\${k}=\${v}|" "\$REMOTE_ENV"
  else
    echo "\${k}=\${v}" >> "\$REMOTE_ENV"
  fi
}
upsert KANBAN_AGENT_WRITES "${kanban_writes}"
REMOTE2
    echo "✅ KANBAN_AGENT_WRITES=${kanban_writes} on server"
  fi
  echo "✅ server .env patched (agent platform)"
}

ensure_unified_host_deps_remote() {
  local bots="${SERVER_BOTS:?}"
  local pip="${bots}/finance_bot/.venv/bin/pip"
  local py="${bots}/finance_bot/.venv/bin/python"
  local root="${MONOREPO:-$(common_monorepo_root)}"
  # shellcheck source=scripts/lib/sh_msg.sh
  source "$root/scripts/lib/sh_msg.sh"
  local msg_pip msg_req
  msg_pip="$(sh_msg scripts.deploy_agent.pip_missing)"
  msg_req="$(sh_msg scripts.deploy_agent.req_missing)"

  echo "📦 unified host: knowledge deps → finance_bot .venv"
  common_ssh "bash -s" <<REMOTE
set -euo pipefail
BOTS="${bots}"
PIP="${pip}"
PY="${py}"
REQ="\$BOTS/knowledge_bot/requirements.txt"
CON="\$BOTS/constraints.txt"
if [ ! -x "\$PIP" ]; then
  echo "${msg_pip}" >&2
  exit 1
fi
if [ ! -f "\$REQ" ]; then
  echo "${msg_req}" >&2
  exit 1
fi
if [ -f "\$CON" ]; then
  "\$PIP" install -q -r "\$REQ" -c "\$CON"
else
  "\$PIP" install -q -r "\$REQ"
fi
export PYTHONPATH="\$BOTS:\$BOTS/finance_bot:\$BOTS/knowledge_bot:\$BOTS/planning_bot"
"\$PY" -c "from knowledge_bot.app.register_handlers import register_knowledge_callbacks; import jinja2"
echo "✅ unified host deps OK (jinja2 + knowledge ingest)"
REMOTE
}

verify_unified_bot_remote() {
  local bots="${SERVER_BOTS:?}"
  local wait="${DEPLOY_VERIFY_WAIT:-15}"
  echo "⏳ verify unified_bot (wait ${wait}s)..."
  sleep "$wait"
  common_ssh "bash -s" <<REMOTE
set -euo pipefail
if pgrep -f 'python -m unified_bot.main' >/dev/null; then
  echo "  unified_bot: UP"
  exit 0
fi
echo "  unified_bot: DOWN" >&2
tail -20 "${bots}/logs/unified_bot.log" 2>/dev/null || true
exit 1
REMOTE
}

stop_legacy_bots_remote() {
  local bots="${SERVER_BOTS:?}"
  echo "🛑 stop legacy polling bots (unified host only) on $SERVER"
  common_ssh "bash -s" <<REMOTE
set -euo pipefail
bots="${bots}"
for b in finance_bot knowledge_bot planning_bot; do
  wd="\$bots/\$b/logs/watchdog.pid"
  if [ -f "\$wd" ]; then
    kill "\$(cat "\$wd")" 2>/dev/null || true
    rm -f "\$wd"
  fi
done
pkill -f "\$bots/finance_bot/.venv/bin/python -m bot.main" 2>/dev/null || true
pkill -f "\$bots/knowledge_bot/.venv/bin/python start_bot.py" 2>/dev/null || true
pkill -f "\$bots/planning_bot/.venv/bin/python -m planning_bot.app.main" 2>/dev/null || true
sleep 1
REMOTE
}

restart_unified_bot_remote() {
  local stop_legacy="${1:-0}"
  local bots="${SERVER_BOTS:?}"
  local py="${bots}/finance_bot/.venv/bin/python"
  local log="${bots}/logs/unified_bot.log"

  ensure_unified_host_deps_remote
  if [ "$stop_legacy" = 1 ]; then
    stop_legacy_bots_remote
  fi

  echo "🔄 restart unified_bot on $SERVER"
  common_ssh "bash -s" <<REMOTE
set -euo pipefail
cd "${bots}"
pkill -f 'python -m unified_bot.main' 2>/dev/null || true
sleep 1
set -a && source .env && set +a
export DEPLOY_MODE=single
export PYTHONPATH="${bots}:${bots}/finance_bot:${bots}/knowledge_bot:${bots}/planning_bot"
export AGENT_ROOT="${bots}"
mkdir -p logs
nohup "${py}" -m unified_bot.main >> "${log}" 2>&1 &
sleep 3
if pgrep -f 'python -m unified_bot.main' >/dev/null; then
  echo "✅ unified_bot running"
  tail -3 "${log}" 2>/dev/null || true
else
  echo "❌ unified_bot failed to start" >&2
  tail -20 "${log}" 2>/dev/null || true
  exit 1
fi
REMOTE
}
