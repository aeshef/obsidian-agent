#!/usr/bin/env bash
# Ensure knowledge_bot config/prompts/tags.txt has JSON instructions for retag (DeepSeek json_object).
#
#   ./scripts/ensure_tags_prompt.sh              # local knowledge_bot/config/prompts/tags.txt
#   ./scripts/ensure_tags_prompt.sh --remote     # on VPS: $SERVER_BOTS/knowledge_bot/...
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

REMOTE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --remote) REMOTE=1; shift ;;
    *) echo "Usage: $0 [--remote]" >&2; exit 2 ;;
  esac
done

TAGS_LOCAL="$ROOT/knowledge_bot/config/prompts/tags.txt"
EXAMPLE="$ROOT/knowledge_bot/config/prompts/tags.example.txt"

if [ "$REMOTE" = 1 ]; then
  common_load_env "$ROOT"
  common_require_server
  BOTS="$(common_server_bots)"
  TAGS_REMOTE="$BOTS/knowledge_bot/config/prompts/tags.txt"
  EXAMPLE_REMOTE="$BOTS/knowledge_bot/config/prompts/tags.example.txt"
  echo "Patching tags.txt on $SERVER ..."
  scp -q "$ROOT/scripts/ensure_tags_prompt.py" "$SERVER:/tmp/ensure_tags_prompt.py"
  ssh "$SERVER" "python3 /tmp/ensure_tags_prompt.py --tags '$TAGS_REMOTE' --example '$EXAMPLE_REMOTE'"
else
  python3 "$ROOT/scripts/ensure_tags_prompt.py" --tags "$TAGS_LOCAL" --example "$EXAMPLE"
fi
