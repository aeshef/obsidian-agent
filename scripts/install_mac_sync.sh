#!/bin/zsh
# Install LaunchAgent for obsidian_sync.sh (respects config/agent/capabilities.yaml via export_capabilities_env).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -f "$AGENT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$AGENT_ROOT/.env"
  set +a
fi
exec "$SCRIPT_DIR/install_launchagent.sh"
