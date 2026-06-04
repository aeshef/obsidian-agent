#!/bin/zsh
# Одностороннее зеркало vault для Obsidian на iPhone (read-mostly).
# Папки — из config/vault_paths.yaml (как obsidian_sync.sh).
#
# По умолчанию — iCloud Obsidian (только телефон; Mac только пишет файлы через rsync):
#   ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault — Mobile
#
# Локальный тест без iCloud:
#   MOBILE_VAULT="$HOME/Documents/Obsidian Vault — Mobile" ./export_mobile_vault.sh
#
# Автозапуск: obsidian_sync.sh шаг 5e (каждый цикл LaunchAgent, ~5 мин).
# Отключить: SKIP_MOBILE_VAULT=1 ~/bin/obsidian_sync.sh

set -euo pipefail

if [[ -n "${0:A}" && -f "${0:A}" ]]; then
  AGENT_ROOT="$(cd "$(dirname "${0:A}")/.." && pwd)"
  P="$(cd "$(dirname "${0:A}")/../.." && pwd)"
  [[ -d "$P/800_Автоматизация" ]] && SRC="$P"
fi
AGENT_ROOT="${AGENT_ROOT:-$(cd "$(dirname "${0:A}")/.." 2>/dev/null && pwd)}"
if [[ -f "${AGENT_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${AGENT_ROOT}/.env"
  set +a
fi
SRC="${SRC:-${VAULT_PATH:-${LOCAL_VAULT:-$HOME/Documents/Obsidian Vault}}}"
MOBILE="${MOBILE_VAULT:-$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian Vault — Mobile}"

# shellcheck source=scripts/lib/vault_paths_defaults.sh
source "${AGENT_ROOT}/scripts/lib/vault_paths_defaults.sh"
vault_paths_load_from_agent "${AGENT_ROOT}"

_actions_parent="${VAULT_PATH_ACTIONS_MAC:h}"

RSYNC=(rsync -a --delete --exclude='.DS_Store')

_vault_segment_sane() {
  local val="$1"
  [[ -n "$val" && "$val" != /* && "$val" != *".."* && "$val" != *"/"* ]]
}

_rsync_folder() {
  local name="$1"
  if ! _vault_segment_sane "$name"; then
    echo "SKIP unsafe folder segment: ${name}" >&2
    return 0
  fi
  local src_dir="$SRC/$name"
  if [[ ! -d "$src_dir" ]]; then
    echo "SKIP missing folder: $src_dir" >&2
    return 0
  fi
  mkdir -p "$MOBILE/$name"
  "${RSYNC[@]}" "$src_dir/" "$MOBILE/$name/"
}

# Remove EN ghost folders from a bad locale run (RU names are canonical here).
_prune_mobile_stale_en_folders() {
  local -a stale=(100_Tasks 200_Goals 300_Dashboards 400_Routines 600_Handwritten)
  local s
  for s in "${stale[@]}"; do
    [[ -d "$MOBILE/$s" ]] || continue
    echo "prune stale mobile folder: $s" >&2
    rm -rf "$MOBILE/$s"
  done
  [[ -d "$MOBILE/Users" ]] && rm -rf "$MOBILE/Users" && echo "prune nested Users/ under mobile vault" >&2
}

echo "export_mobile_vault: $SRC → $MOBILE"

mkdir -p "$MOBILE"

_rsync_folder "${VAULT_FOLDER_TASKS}"
_rsync_folder "${VAULT_FOLDER_GOALS}"
if [[ -d "$SRC/${VAULT_FOLDER_DASHBOARDS}" ]]; then
  mkdir -p "$MOBILE/${VAULT_FOLDER_DASHBOARDS}"
  "${RSYNC[@]}" \
    --exclude="${VAULT_DASH_DATA}/${_actions_parent}/" \
    --exclude="${VAULT_DASH_DATA}/finance.db" \
    --exclude="${VAULT_DASH_DATA}/finance.db-*" \
    "$SRC/${VAULT_FOLDER_DASHBOARDS}/" "$MOBILE/${VAULT_FOLDER_DASHBOARDS}/"
else
  echo "SKIP missing folder: $SRC/${VAULT_FOLDER_DASHBOARDS}" >&2
fi
_rsync_folder "${VAULT_FOLDER_ROUTINES}"

mkdir -p "$MOBILE/.obsidian/plugins"
for f in app.json appearance.json community-plugins.json core-plugins.json templates.json daily-notes.json; do
  [[ -f "$SRC/.obsidian/$f" ]] && cp "$SRC/.obsidian/$f" "$MOBILE/.obsidian/$f"
done
for p in dataview templater-obsidian obsidian-kanban; do
  [[ -d "$SRC/.obsidian/plugins/$p" ]] && rsync -a "$SRC/.obsidian/plugins/$p/" "$MOBILE/.obsidian/plugins/$p/"
done
[[ -d "$SRC/.obsidian/snippets" ]] && rsync -a "$SRC/.obsidian/snippets/" "$MOBILE/.obsidian/snippets/"

_prune_mobile_stale_en_folders

echo "OK: $(du -sh "$MOBILE" | awk '{print $1}') → $MOBILE"
