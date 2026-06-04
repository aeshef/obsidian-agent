#!/usr/bin/env bash
# Remove EN ghost folders created when AGENT_LOCALE=en overrode vault_paths.yaml.
# Safe: only deletes known EN names if matching RU folder exists (or folder is empty).
set -euo pipefail

VAULT="${1:-${VAULT_PATH:-$HOME/Documents/Obsidian Vault}}"
MOBILE="${2:-$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault — Mobile}"

_pairs=(
  "100_Tasks:100_Задачи"
  "200_Goals:200_Цели"
  "300_Dashboards:300_Дашборды"
  "400_Routines:400_Рутины"
  "600_Handwritten:600_Рукописное"
)

_prune_root() {
  local root="$1"
  local en ru
  [[ -d "$root" ]] || return 0
  for pair in "${_pairs[@]}"; do
    en="${pair%%:*}"
    ru="${pair##*:}"
    [[ -d "$root/$en" ]] || continue
    if [[ -d "$root/$ru" ]] || [[ -z "$(find "$root/$en" -mindepth 1 -print -quit 2>/dev/null)" ]]; then
      echo "rm -rf $root/$en"
      rm -rf "$root/$en"
    fi
  done
  if [[ -d "$root/Users" ]]; then
    echo "rm -rf $root/Users (nested absolute-path rsync artifact)"
    rm -rf "$root/Users"
  fi
}

_prune_root "$VAULT"
_prune_root "$MOBILE"
echo "done"
