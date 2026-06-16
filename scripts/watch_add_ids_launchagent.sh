#!/bin/zsh
# LaunchAgent wrapper: same runtime env as obsidian_sync_launchagent.sh, then watch kanban ids.
set -euo pipefail

RUNTIME_ROOT="${OBSIDIAN_AGENT_RUNTIME_ROOT:-$HOME/Library/Application Support/obsidian-agent/runtime}"
AGENT_ROOT="${AGENT_ROOT:-$RUNTIME_ROOT/agent}"
WATCH_SCRIPT="$AGENT_ROOT/planning_bot/scripts/watch_and_add_ids.py"

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export OBSIDIAN_AGENT_RUNTIME_ROOT="$RUNTIME_ROOT"
export OBSIDIAN_AGENT_PYDEPS_FINANCE="$RUNTIME_ROOT/pydeps/finance"
export OBSIDIAN_AGENT_PYDEPS_PLANNING="$RUNTIME_ROOT/pydeps/planning"
export OBSIDIAN_AGENT_PYDEPS_KNOWLEDGE="$RUNTIME_ROOT/pydeps/knowledge"
export AGENT_ROOT
export PYTHONPATH="$AGENT_ROOT:$OBSIDIAN_AGENT_PYDEPS_FINANCE:$OBSIDIAN_AGENT_PYDEPS_PLANNING:$OBSIDIAN_AGENT_PYDEPS_KNOWLEDGE"

if [[ -f "$AGENT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$AGENT_ROOT/.env"
  set +a
fi

# shellcheck source=scripts/lib/common.sh
source "$AGENT_ROOT/scripts/lib/common.sh"

PY="$(common_launchagent_python "$AGENT_ROOT/planning_bot")"
if [[ -z "$PY" ]]; then
  PY="$(common_launchagent_python "$AGENT_ROOT/finance_bot")"
fi
if [[ -z "$PY" ]]; then
  PY="$(common_resolve_python "$AGENT_ROOT/planning_bot")"
fi

common_export_bot_pythonpath "$AGENT_ROOT/planning_bot" "$AGENT_ROOT"
exec common_run_python_script "$PY" "$WATCH_SCRIPT"
