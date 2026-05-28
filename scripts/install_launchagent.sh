#!/bin/zsh
set -euo pipefail

[REDACTED]
AGENT_DIR="$VAULT_PATH/800_Автоматизация/Agent"
PLIST_SRC="$AGENT_DIR/com.example.obsidian-sync.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.example.obsidian-sync.plist"
SYNC_LINK="$HOME/bin/obsidian_sync.sh"
LAUNCH_WRAPPER="$HOME/bin/obsidian_sync_launchagent.sh"
LABEL="com.example.obsidian-sync"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/bin"
chmod +x "$AGENT_DIR/scripts/obsidian_sync.sh"

ln -sf "$AGENT_DIR/scripts/obsidian_sync.sh" "$SYNC_LINK"
cat > "$LAUNCH_WRAPPER" <<'EOF'
#!/bin/zsh
DEBUG_LOG="/tmp/obsidian_sync_launchagent_wrapper.log"
echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ wrapper START" >> "$DEBUG_LOG" 2>/dev/null || true
exec "/Users/example/Documents/Obsidian Vault/800_Автоматизация/Agent/obsidian_sync.sh"
EOF
chmod +x "$LAUNCH_WRAPPER"
cp "$PLIST_SRC" "$PLIST_DST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed: $PLIST_DST"
echo "Symlink:   $SYNC_LINK"
echo "Wrapper:   $LAUNCH_WRAPPER"
echo "Label:     $LABEL"
echo "Logs:      /tmp/obsidian-sync.out /tmp/obsidian-sync.err /tmp/obsidian_sync_debug.log /tmp/obsidian_sync_launchagent_wrapper.log"
