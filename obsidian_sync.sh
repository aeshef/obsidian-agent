#!/bin/zsh
# Тонкий wrapper → scripts/obsidian_sync.sh (монорепо)
AGENT_ROOT="$(cd "$(dirname "$0")" && pwd)"
export AGENT_ROOT
exec "$AGENT_ROOT/scripts/obsidian_sync.sh"
