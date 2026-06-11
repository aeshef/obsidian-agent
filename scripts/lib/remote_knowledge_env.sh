# shellcheck shell=bash
# VPS helpers for knowledge_bot CLI (deployed to SERVER_BOTS/scripts/lib/).
# Loads agent .env + vault_paths; no locale-specific paths in callers.

_remote_lib_dir() {
  cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

remote_server_bots() {
  if [[ -n "${SERVER_BOTS:-}" ]]; then
    printf '%s\n' "$SERVER_BOTS"
    return 0
  fi
  cd "$(_remote_lib_dir)/.." && pwd
}

remote_load_agent_env() {
  local bots root
  bots="$(remote_server_bots)"
  export SERVER_BOTS="$bots"
  root="${AGENT_ROOT:-$bots}"
  export AGENT_ROOT="$root"

  # shellcheck source=scripts/lib/common.sh
  source "$bots/scripts/lib/common.sh"
  common_load_env "$root"

  # shellcheck source=scripts/lib/vault_paths_defaults.sh
  source "$bots/scripts/lib/vault_paths_defaults.sh"
  export PYTHONPATH="${root}${PYTHONPATH:+:$PYTHONPATH}"
  vault_paths_load_from_agent "$root" || vault_paths_apply_defaults
}

remote_resolve_knowledge_bot() {
  local tool="${1:-tools/apply_duplicates_resolution.py}" kb vault_kb=""
  if [[ -n "${VAULT_FOLDER_AUTOMATION:-}" && -n "${VAULT_PATH:-}" ]]; then
    vault_kb="${VAULT_PATH}/${VAULT_FOLDER_AUTOMATION}/Agent/knowledge_bot"
  fi
  for kb in \
    "${REMOTE_KNOWLEDGE_BOT:-}" \
    "${SERVER_BOTS}/knowledge_bot" \
    "$vault_kb"; do
    [[ -z "$kb" ]] && continue
    [[ -f "${kb}/${tool}" ]] || continue
    printf '%s\n' "$kb"
    return 0
  done
  return 1
}

remote_resolve_python_for_kb() {
  local kb="$1" py
  # shellcheck source=scripts/lib/common.sh
  source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
  py="$(common_resolve_python "$kb")"
  if [[ -x "$py" ]]; then
    printf '%s\n' "$py"
    return 0
  fi
  if [[ -n "${PLANNING_BOT_REMOTE_PYTHON:-}" && -x "${PLANNING_BOT_REMOTE_PYTHON}" ]]; then
    printf '%s\n' "${PLANNING_BOT_REMOTE_PYTHON}"
    return 0
  fi
  for py in \
    "${SERVER_BOTS}/planning_bot/.venv/bin/python" \
    "${SERVER_BOTS}/planning_bot/venv/bin/python" \
    "${SERVER_BOTS}/finance_bot/.venv/bin/python"; do
    if [[ -x "$py" ]]; then
      printf '%s\n' "$py"
      return 0
    fi
  done
  command -v python3
}

remote_agent_pythonpath() {
  local bots="${SERVER_BOTS:-$(remote_server_bots)}"
  printf '%s:%s/finance_bot:%s/knowledge_bot:%s/planning_bot' "$bots" "$bots" "$bots" "$bots"
}
