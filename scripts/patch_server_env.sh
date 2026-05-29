#!/usr/bin/env bash
# Дописывает/обновляет ключи agent platform в $SERVER_BOTS/.env на VPS (из локального .env).
#
#   ./scripts/patch_server_env.sh
#   ./scripts/patch_server_env.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"
common_require_server

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

SERVER_BOTS="$(common_server_bots)"
REMOTE_ENV="${SERVER_BOTS}/.env"

TELEGRAM_UNIFIED_BOT_TOKEN="${TELEGRAM_UNIFIED_BOT_TOKEN:-}"
SYNTH_ENABLED="${SYNTH_ENABLED:-1}"
SYNTH_DOMAINS="${SYNTH_DOMAINS:-finance,planning}"
MEMORY_SESSION_PERSIST="${MEMORY_SESSION_PERSIST:-1}"

if [ -z "$TELEGRAM_UNIFIED_BOT_TOKEN" ]; then
  echo "❌ TELEGRAM_UNIFIED_BOT_TOKEN пустой в локальном $ROOT/.env" >&2
  exit 1
fi

if [ "$DRY" = 1 ]; then
  echo "dry-run: patch $SERVER:$REMOTE_ENV"
  printf '%s\n' \
    "TELEGRAM_UNIFIED_BOT_TOKEN=***" \
    "SYNTH_ENABLED=$SYNTH_ENABLED" \
    "SYNTH_DOMAINS=$SYNTH_DOMAINS" \
    "MEMORY_SESSION_PERSIST=$MEMORY_SESSION_PERSIST" \
    "AGENT_MEMORY_DB=$SERVER_BOTS/memory.db" \
    "AGENT_ROOT=$SERVER_BOTS"
  exit 0
fi

echo "📝 patch $SERVER:$REMOTE_ENV"
common_ssh "bash -s" <<REMOTE
set -euo pipefail
REMOTE_ENV="$REMOTE_ENV"
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

upsert TELEGRAM_UNIFIED_BOT_TOKEN "${TELEGRAM_UNIFIED_BOT_TOKEN}"
upsert SYNTH_ENABLED "${SYNTH_ENABLED}"
upsert SYNTH_DOMAINS "${SYNTH_DOMAINS}"
upsert MEMORY_SESSION_PERSIST "${MEMORY_SESSION_PERSIST}"
upsert AGENT_MEMORY_DB "${SERVER_BOTS}/memory.db"
upsert AGENT_ROOT "${SERVER_BOTS}"
echo "✅ server .env patched (agent platform)"
REMOTE

echo "✅ patch_server_env OK"
