#!/bin/zsh
# Одностороннее зеркало vault для Obsidian на iPhone (read-mostly).
# Папки — из config/vault_paths.yaml (как obsidian_sync.sh).
#
# Default mobile mirror path is configured via MOBILE_VAULT or config/agent/platform.yaml.
#
# Local test:
#   MOBILE_VAULT="/path/to/mobile-vault" ./export_mobile_vault.sh
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
# shellcheck source=scripts/lib/common.sh
source "${AGENT_ROOT}/scripts/lib/common.sh"
SRC="${SRC:-${VAULT_PATH:-${LOCAL_VAULT:-$(common_resolve_vault "$AGENT_ROOT" 2>/dev/null || true)}}}"
if [[ -z "$SRC" ]]; then
  echo "export_mobile_vault: VAULT_PATH is not configured" >&2
  exit 1
fi
MOBILE="${MOBILE_VAULT:-$(common_platform_value "$AGENT_ROOT" vault mobile_path "")}"
if [[ -z "$MOBILE" ]]; then
  echo "export_mobile_vault: MOBILE_VAULT is not configured" >&2
  exit 1
fi

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

echo "export_mobile_vault: $SRC → $MOBILE"

mkdir -p "$MOBILE"

_rsync_folder "${VAULT_FOLDER_TASKS}"
_rsync_folder "${VAULT_FOLDER_GOALS}"
if _vault_segment_sane "${VAULT_FOLDER_DASHBOARDS}" && [[ -d "$SRC/${VAULT_FOLDER_DASHBOARDS}" ]]; then
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

echo "OK: $(du -sh "$MOBILE" | awk '{print $1}') → $MOBILE"
