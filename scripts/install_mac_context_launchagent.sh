#!/usr/bin/env bash
# Install LaunchAgent: shortcuts run "Контекст Mac (Obsidian)" every 5 min.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.aeshef.mac-context-obsidian"
SRC="$SCRIPT_DIR/launchagents/${LABEL}.plist"
DST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [ ! -f "$SRC" ]; then
  echo "Missing template: $SRC" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cp "$SRC" "$DST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DST"
launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null || true
echo "Loaded $LABEL (every 300s → Контекст Mac (Obsidian))"
echo "Logs: /tmp/mac-context-obsidian.{out,err}"
