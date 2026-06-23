#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$AGENT_DIR/scripts/lib/common.sh"
VAULT_PATH="${VAULT_PATH:-${LOCAL_VAULT:-$(common_resolve_vault "$AGENT_DIR" 2>/dev/null || true)}}"
if [[ -z "$VAULT_PATH" ]]; then
  echo "install_launchagent: VAULT_PATH is not configured" >&2
  exit 1
fi
PLIST_EXAMPLE="$AGENT_DIR/launchd/com.example.obsidian-sync.plist.example"
LABEL="${LAUNCHAGENT_LABEL:-com.example.obsidian-sync}"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
SYNC_LINK="$HOME/bin/obsidian_sync.sh"
LAUNCH_WRAPPER="$HOME/bin/obsidian_sync_launchagent.sh"
LEGACY_LABELS=(com.example.obsidian-sync com.aeshef.obsidian-sync)
RUNTIME_ROOT="$HOME/Library/Application Support/obsidian-agent/runtime"
RUNTIME_AGENT="$RUNTIME_ROOT/agent"

SYNC_INTERVAL="${OBSIDIAN_SYNC_INTERVAL_SEC:-}"
if [[ -z "$SYNC_INTERVAL" ]]; then
  _CAP_PY="$(common_launchagent_python "$AGENT_DIR/finance_bot" 2>/dev/null || true)"
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

echo "Mirroring Agent for LaunchAgent (outside ~/Documents) → $RUNTIME_AGENT"
mkdir -p "$RUNTIME_ROOT/pydeps/finance" "$RUNTIME_ROOT/pydeps/planning"
rsync -a --delete \
  --exclude '.venv/' --exclude 'venv/' --exclude '__pycache__/' \
  --exclude '.git/' --exclude 'memory.db' --exclude '*.pyc' \
  --exclude 'finance_bot/logs/' --exclude 'planning_bot/logs/' --exclude 'knowledge_bot/logs/' \
  "$AGENT_DIR/" "$RUNTIME_AGENT/"

_FIN_SP="$(ls -d "$AGENT_DIR/finance_bot/.venv/lib/python"*/site-packages 2>/dev/null | head -1)"
_PLAN_SP="$(ls -d "$AGENT_DIR/planning_bot/venv/lib/python"*/site-packages 2>/dev/null | head -1)"
if [[ -n "$_FIN_SP" && -d "$_FIN_SP" ]]; then
  rsync -a "$_FIN_SP/" "$RUNTIME_ROOT/pydeps/finance/"
fi
if [[ -n "$_PLAN_SP" && -d "$AGENT_DIR/planning_bot/venv/lib" ]]; then
  rsync -a "$_PLAN_SP/" "$RUNTIME_ROOT/pydeps/planning/"
fi
_KN_SP="$(find "$AGENT_DIR/knowledge_bot/venv/lib" -maxdepth 2 -name site-packages -type d 2>/dev/null | head -1)"
if [[ -n "$_KN_SP" && -d "$_KN_SP" ]]; then
  mkdir -p "$RUNTIME_ROOT/pydeps/knowledge"
  rsync -a "$_KN_SP/" "$RUNTIME_ROOT/pydeps/knowledge/"
fi
unset _FIN_SP _PLAN_SP _KN_SP

# Author prod configs (gitignored) must live in runtime copy for LaunchAgent sync.
for _cfg in vault_paths.yaml messages.ru.yaml domain_messages.ru.yaml domain_messages.yaml; do
  if [[ -f "$AGENT_DIR/config/$_cfg" ]]; then
    cp -f "$AGENT_DIR/config/$_cfg" "$RUNTIME_AGENT/config/$_cfg"
  fi
done
if [[ ! -f "$RUNTIME_AGENT/config/vault_paths.yaml" && -f "$AGENT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$AGENT_DIR/.env"
  set +a
  _mat_py="$(common_launchagent_python "$AGENT_DIR/finance_bot" 2>/dev/null || true)"
  if [[ -n "$_mat_py" && -f "$AGENT_DIR/scripts/setup/materialize_locale.py" ]]; then
  AGENT_LOCALE="${AGENT_LOCALE:-ru}" "$_mat_py" "$AGENT_DIR/scripts/setup/materialize_locale.py" \
    "${AGENT_LOCALE:-ru}" --refresh-vault-paths 2>/dev/null || true
  if [[ -f "$AGENT_DIR/config/vault_paths.yaml" ]]; then
    cp -f "$AGENT_DIR/config/vault_paths.yaml" "$RUNTIME_AGENT/config/vault_paths.yaml"
  fi
  fi
fi
unset _cfg _mat_py _c

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/bin"
chmod +x "$AGENT_DIR/scripts/obsidian_sync.sh" "$RUNTIME_AGENT/scripts/obsidian_sync.sh"

ln -sf "$AGENT_DIR/scripts/obsidian_sync.sh" "$SYNC_LINK"
cat > "$LAUNCH_WRAPPER" <<EOF
#!/bin/zsh
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export OBSIDIAN_AGENT_RUNTIME_ROOT="$RUNTIME_ROOT"
export OBSIDIAN_AGENT_PYDEPS_FINANCE="$RUNTIME_ROOT/pydeps/finance"
export OBSIDIAN_AGENT_PYDEPS_PLANNING="$RUNTIME_ROOT/pydeps/planning"
export OBSIDIAN_AGENT_PYDEPS_KNOWLEDGE="$RUNTIME_ROOT/pydeps/knowledge"
export AGENT_ROOT="$RUNTIME_AGENT"
export LOCAL_VAULT="$VAULT_PATH"
export VAULT_PATH="$VAULT_PATH"
export PYTHONPATH="$RUNTIME_AGENT:$RUNTIME_ROOT/pydeps/finance:$RUNTIME_ROOT/pydeps/planning:$RUNTIME_ROOT/pydeps/knowledge"
if [[ -f "$RUNTIME_AGENT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$RUNTIME_AGENT/.env"
  set +a
fi
DEBUG_LOG="/tmp/obsidian_sync_launchagent_wrapper.log"
echo "\$(date '+%Y-%m-%dT%H:%M:%S') pid=\$\$ wrapper START runtime=$RUNTIME_AGENT" >> "\$DEBUG_LOG" 2>/dev/null || true
_CAP_PY=""
if [[ -f "$RUNTIME_AGENT/scripts/lib/common.sh" ]]; then
  source "$RUNTIME_AGENT/scripts/lib/common.sh"
  _CAP_PY="\$(common_launchagent_python "$RUNTIME_AGENT/finance_bot" 2>/dev/null || true)"
fi
if [[ -z "\$_CAP_PY" ]] && command -v python3 >/dev/null 2>&1; then
  _CAP_PY="python3"
fi
_export_py() {
  local script="\$1"
  [[ -n "\$_CAP_PY" && -f "\$script" ]] || return 0
  cat "\$script" | "\$_CAP_PY" -u - 2>/dev/null
}
if [[ -f "$RUNTIME_AGENT/scripts/export_capabilities_env.py" ]]; then
  eval "\$(_export_py "$RUNTIME_AGENT/scripts/export_capabilities_env.py")" || true
fi
if [[ -f "$RUNTIME_AGENT/scripts/export_vault_paths_env.py" ]]; then
  eval "\$(_export_py "$RUNTIME_AGENT/scripts/export_vault_paths_env.py")" || true
fi
unset _export_py _c
exec "$RUNTIME_AGENT/scripts/obsidian_sync.sh"
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
  rm -f "$HOME/Library/LaunchAgents/${_old}.plist"
done
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed: $PLIST_DST"
echo "Vault:     $VAULT_PATH"
echo "Runtime:   $RUNTIME_AGENT"
echo "Interval:  ${SYNC_INTERVAL}s"
echo "Symlink:   $SYNC_LINK (manual → vault copy)"
echo "Wrapper:   $LAUNCH_WRAPPER"
echo "Label:     $LABEL"
