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

  if [ -z "$token" ]; then
    echo "❌ TELEGRAM_UNIFIED_BOT_TOKEN пустой в $root/.env" >&2
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
REMOTE
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

  echo "📦 unified host: knowledge deps → finance_bot .venv"
  common_ssh "bash -s" <<REMOTE
set -euo pipefail
BOTS="${bots}"
PIP="${pip}"
PY="${py}"
REQ="\$BOTS/knowledge_bot/requirements.txt"
CON="\$BOTS/constraints.txt"
if [ ! -x "\$PIP" ]; then
  echo "❌ нет \$PIP — сначала ensure_bot_venv.sh finance_bot" >&2
  exit 1
fi
if [ ! -f "\$REQ" ]; then
  echo "❌ нет \$REQ" >&2
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

restart_unified_bot_remote() {
  local bots="${SERVER_BOTS:?}"
  local py="${bots}/finance_bot/.venv/bin/python"
  local log="${bots}/logs/unified_bot.log"

  ensure_unified_host_deps_remote

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
