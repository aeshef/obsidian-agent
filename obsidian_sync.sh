#!/bin/zsh
# Тонкий wrapper → scripts/obsidian_sync.sh (монорепо).
# ${0:A} разрешает symlink (~/bin/obsidian_sync.sh → этот файл).
REAL="${0:A}"
AGENT_ROOT="$(cd "$(dirname "$REAL")" && pwd)"
export AGENT_ROOT
exec "$AGENT_ROOT/scripts/obsidian_sync.sh"
