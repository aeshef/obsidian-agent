#!/usr/bin/env bash
# Install LaunchAgent: macOS Shortcut for Mac context snapshots (every 5 min).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="${LAUNCHAGENT_LABEL:-com.example.mac-context-obsidian}"
SHORTCUT_NAME="${MAC_CONTEXT_SHORTCUT_NAME:-Mac Context (Obsidian)}"
SRC="$SCRIPT_DIR/launchagents/com.example.mac-context-obsidian.plist.example"
DST="$HOME/Library/LaunchAgents/${LABEL}.plist"

if [ ! -f "$SRC" ]; then
  echo "Missing template: $SRC" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
sed \
  -e "s/com\\.example\\.mac-context-obsidian/${LABEL//\//\\/}/g" \
  -e "s/Mac Context (Obsidian)/${SHORTCUT_NAME//\//\\/}/g" \
  "$SRC" >"$DST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DST"
launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null || true
echo "Loaded $LABEL (every 300s → $SHORTCUT_NAME)"
echo "Logs: /tmp/mac-context-obsidian.{out,err}"
