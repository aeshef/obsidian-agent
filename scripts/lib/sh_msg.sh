# shellcheck shell=bash
# Resolve scripts.* strings via config/messages.{locale}.yaml (AGENT_LOCALE, default en).
# Source from bash or zsh: source "$AGENT_ROOT/scripts/lib/sh_msg.sh"

_sh_msg_repo_root() {
  if [ -n "${AGENT_ROOT:-}" ] && [ -f "${AGENT_ROOT}/.env.example" ]; then
    echo "$AGENT_ROOT"
    return 0
  fi
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
  echo "$here"
}

_sh_msg_python() {
  local root py
  root="$(_sh_msg_repo_root)"
  if [ -x "$root/finance_bot/.venv/bin/python" ]; then
    echo "$root/finance_bot/.venv/bin/python"
    return 0
  fi
  if [ -x "$root/planning_bot/.venv/bin/python" ]; then
    echo "$root/planning_bot/.venv/bin/python"
    return 0
  fi
  command -v python3
}

sh_msg() {
  local root py keypath default
  root="$(_sh_msg_repo_root)"
  py="$(_sh_msg_python)"
  keypath="$1"
  shift
  default="${1:-}"
  AGENT_LOCALE="${AGENT_LOCALE:-en}" PYTHONPATH="$root/finance_bot:$root" \
    "$py" "$root/scripts/resolve_shell_msg.py" msg "$keypath" "$default"
}

sh_msgf() {
  local root py keypath json
  root="$(_sh_msg_repo_root)"
  py="$(_sh_msg_python)"
  keypath="$1"
  json="$2"
  AGENT_LOCALE="${AGENT_LOCALE:-en}" PYTHONPATH="$root/finance_bot:$root" \
    "$py" "$root/scripts/resolve_shell_msg.py" msgf "$keypath" "$json"
}
