# shellcheck shell=bash
# Mirror vault Agent → LaunchAgent runtime copy (author edits vault; launchd uses ~/Library/.../runtime/agent).
# Source from obsidian_sync.sh after vault_paths_load.

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
    "$vault_agent/" "$runtime_agent/"

  local _cfg
  for _cfg in vault_paths.yaml messages.ru.yaml domain_messages.ru.yaml domain_messages.yaml; do
    if [[ -f "$vault_agent/config/$_cfg" ]]; then
      cp -f "$vault_agent/config/$_cfg" "$runtime_agent/config/$_cfg"
    fi
  done
  for _cfg in platform.yaml capabilities.yaml; do
    if [[ -f "$vault_agent/config/agent/$_cfg" ]]; then
      cp -f "$vault_agent/config/agent/$_cfg" "$runtime_agent/config/agent/$_cfg"
    fi
  done
  if [[ -f "$vault_agent/finance_bot/config/dashboard_templates.yaml" ]]; then
    cp -f "$vault_agent/finance_bot/config/dashboard_templates.yaml" \
      "$runtime_agent/finance_bot/config/dashboard_templates.yaml"
  fi
  unset _cfg

  echo "[runtime-mirror] $vault_agent → $runtime_agent" >&2
}
