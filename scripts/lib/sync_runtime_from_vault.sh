# shellcheck shell=bash
# Mirror vault Agent → LaunchAgent runtime copy (author edits vault; launchd uses ~/Library/.../runtime/agent).
# Source from obsidian_sync.sh after vault_paths_load.

# Copy personal config only when source is readable and non-empty.
# LaunchAgent without Full Disk Access can "see" Documents paths but read 0 bytes;
# never clobber a good runtime file with an empty TCC stub.
_sync_runtime_copy_cfg() {
  local src="$1" dest="$2"
  local sz
  [[ -f "$src" ]] || return 0
  sz=$(wc -c <"$src" 2>/dev/null | tr -d '[:space:]')
  [[ -n "$sz" && "$sz" -gt 0 ]] || {
    echo "[runtime-mirror] skip empty/unreadable: $src" >&2
    return 0
  }
  mkdir -p "$(dirname "$dest")"
  if ! cp -f "$src" "$dest"; then
    echo "[runtime-mirror] cp failed: $src → $dest" >&2
    return 1
  fi
  local dsz
  dsz=$(wc -c <"$dest" 2>/dev/null | tr -d '[:space:]')
  if [[ -z "$dsz" || "$dsz" -lt 1 ]]; then
    echo "[runtime-mirror] WARN empty after cp (TCC?): $dest" >&2
    return 1
  fi
  return 0
}

sync_runtime_from_vault() {
  local vault_agent="${LOCAL_VAULT:?}/${VAULT_FOLDER_AUTOMATION:?}/${VAULT_PATH_AGENT_SUBDIR:?}"
  local runtime_root="${OBSIDIAN_AGENT_RUNTIME_ROOT:-$HOME/Library/Application Support/obsidian-agent/runtime}"
  local runtime_agent="${runtime_root}/agent"

  [[ -d "$vault_agent" ]] || return 0
  # Only when sync runs from runtime (LaunchAgent wrapper), not when AGENT_ROOT is the vault copy itself.
  [[ "$AGENT_ROOT" == "$runtime_agent" ]] || return 0
  [[ "$vault_agent" != "$runtime_agent" ]] || return 0

  mkdir -p "$runtime_root/pydeps/finance" "$runtime_root/pydeps/planning" "$runtime_root/pydeps/knowledge"
  rsync -a \
    --exclude '.venv/' --exclude 'venv/' --exclude '__pycache__/' \
    --exclude '.git/' --exclude 'memory.db' --exclude '*.pyc' \
    --exclude 'finance_bot/logs/' --exclude 'planning_bot/logs/' --exclude 'knowledge_bot/logs/' \
    --exclude 'config/domain_messages.yaml' \
    --exclude 'config/domain_messages.ru.yaml' \
    --exclude 'config/domain_messages.en.yaml' \
    --exclude 'config/messages.ru.yaml' \
    --exclude 'config/messages.en.yaml' \
    --exclude 'config/vault_paths.yaml' \
    --exclude 'config/agent/capabilities.yaml' \
    "$vault_agent/" "$runtime_agent/"

  local _cfg
  for _cfg in vault_paths.yaml messages.ru.yaml domain_messages.ru.yaml domain_messages.yaml; do
    _sync_runtime_copy_cfg "$vault_agent/config/$_cfg" "$runtime_agent/config/$_cfg" || true
  done
  for _cfg in platform.yaml capabilities.yaml; do
    _sync_runtime_copy_cfg "$vault_agent/config/agent/$_cfg" "$runtime_agent/config/agent/$_cfg" || true
  done
  if [[ -f "$vault_agent/finance_bot/config/dashboard_templates.yaml" ]]; then
    _sync_runtime_copy_cfg \
      "$vault_agent/finance_bot/config/dashboard_templates.yaml" \
      "$runtime_agent/finance_bot/config/dashboard_templates.yaml" || true
  fi
  unset _cfg

  echo "[runtime-mirror] $vault_agent → $runtime_agent" >&2
}
