#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VAULT_PATH="${VAULT_PATH:-${LOCAL_VAULT:-$(cd "$AGENT_DIR/../.." 2>/dev/null && pwd || echo "$HOME/Documents/Obsidian Vault")}}"
PLIST_EXAMPLE="$AGENT_DIR/launchd/com.example.obsidian-sync.plist.example"
LABEL="${LAUNCHAGENT_LABEL:-com.aeshef.obsidian-sync}"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
SYNC_LINK="$HOME/bin/obsidian_sync.sh"
LAUNCH_WRAPPER="$HOME/bin/obsidian_sync_launchagent.sh"
LEGACY_LABELS=(com.example.obsidian-sync com.aeshef.obsidian-sync)

SYNC_INTERVAL="${OBSIDIAN_SYNC_INTERVAL_SEC:-}"
if [[ -z "$SYNC_INTERVAL" ]]; then
  _CAP_PY=""
  for _c in "$AGENT_DIR/planning_bot/.venv/bin/python" "$AGENT_DIR/finance_bot/.venv/bin/python" python3; do
    [[ -x "$_c" ]] && _CAP_PY="$_c" && break
  done
  if [[ -n "$_CAP_PY" ]]; then
    SYNC_INTERVAL="$("$_CAP_PY" -c "
import sys
sys.path.insert(0, '$AGENT_DIR')
try:
    from shared.agent.platform_config import platform_int
    print(platform_int('obsidian_sync', 'launchagent_interval_sec', default=300))
except Exception:
    print(300)
" 2>/dev/null || echo 300)"
  fi
fi
SYNC_INTERVAL="${SYNC_INTERVAL:-300}"

if [ ! -f "$PLIST_EXAMPLE" ]; then
  echo "Missing plist template: $PLIST_EXAMPLE" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/bin"
chmod +x "$AGENT_DIR/scripts/obsidian_sync.sh"

ln -sf "$AGENT_DIR/scripts/obsidian_sync.sh" "$SYNC_LINK"
cat > "$LAUNCH_WRAPPER" <<EOF
#!/bin/zsh
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export AGENT_ROOT="$AGENT_DIR"
export LOCAL_VAULT="$VAULT_PATH"
export VAULT_PATH="$VAULT_PATH"
DEBUG_LOG="/tmp/obsidian_sync_launchagent_wrapper.log"
echo "\$(date '+%Y-%m-%dT%H:%M:%S') pid=\$\$ wrapper START" >> "\$DEBUG_LOG" 2>/dev/null || true
_CAP_PY=""
for _c in "$AGENT_DIR/planning_bot/.venv/bin/python" "$AGENT_DIR/finance_bot/.venv/bin/python" python3; do
  if [[ -x "\$_c" ]]; then _CAP_PY="\$_c"; break; fi
done
if [[ -n "\$_CAP_PY" && -f "$AGENT_DIR/scripts/export_capabilities_env.py" ]]; then
  eval "\$("\$_CAP_PY" "$AGENT_DIR/scripts/export_capabilities_env.py" 2>/dev/null)" || true
fi
exec "$SYNC_LINK"
EOF
chmod +x "$LAUNCH_WRAPPER"

sed -e "s|__HOME__|$HOME|g" \
    -e "s|__VAULT_PATH__|$VAULT_PATH|g" \
    -e "s|com.example.obsidian-sync|$LABEL|g" \
    -e "s|<integer>300</integer>|<integer>$SYNC_INTERVAL</integer>|" \
    "$PLIST_EXAMPLE" > "$PLIST_DST"

for _old in "${LEGACY_LABELS[@]}"; do
  [[ "$_old" == "$LABEL" ]] && continue
  launchctl bootout "gui/$(id -u)/$_old" 2>/dev/null || true
done
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed: $PLIST_DST"
echo "Vault:     $VAULT_PATH"
echo "Interval:  ${SYNC_INTERVAL}s"
echo "Symlink:   $SYNC_LINK"
echo "Wrapper:   $LAUNCH_WRAPPER"
echo "Label:     $LABEL"
