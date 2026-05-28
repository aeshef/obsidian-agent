#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"
common_require_server
SERVER_BOTS="${SERVER_BOTS:-/opt/obsidian-bots}"
common_ssh "cd ${SERVER_BOTS}/knowledge_bot && tail -f logs/bot.log"
