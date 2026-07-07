#!/bin/zsh
# Pull recent authoring edits from mobile Obsidian mirror into the main vault.
# Safe direction: mobile -> source only for authoring folders, newer files win.

set -euo pipefail

if [[ -n "${0:A}" && -f "${0:A}" ]]; then
  AGENT_ROOT="$(cd "$(dirname "${0:A}")/.." && pwd)"
  P="$(cd "$(dirname "${0:A}")/../.." && pwd)"
  for _guess in "$P"/*/Agent; do
    if [[ -f "$_guess/scripts/obsidian_sync.sh" ]]; then
      SRC="$P"
      break
    fi
  done
  unset _guess
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
  echo "import_mobile_vault: VAULT_PATH is not configured" >&2
  exit 1
fi
MOBILE="${MOBILE_VAULT:-$(common_platform_value "$AGENT_ROOT" vault mobile_path "" || true)}"
if [[ -z "$MOBILE" ]]; then
  echo "import_mobile_vault: mobile path not configured (set MOBILE_VAULT env or vault.mobile_path in config/agent/platform.yaml)" >&2
  exit 1
fi
if [[ ! -d "$MOBILE" ]]; then
  echo "import_mobile_vault: mobile path missing: $MOBILE" >&2
  exit 0
fi

# shellcheck source=scripts/lib/vault_paths_defaults.sh
source "${AGENT_ROOT}/scripts/lib/vault_paths_defaults.sh"
vault_paths_load_from_agent "${AGENT_ROOT}"

RSYNC=(rsync -a --update --exclude='.DS_Store')

_vault_segment_sane() {
  local val="$1"
  [[ -n "$val" && "$val" != /* && "$val" != *".."* && "$val" != *"/"* ]]
}

_rsync_back_folder() {
  local name="$1"
  if ! _vault_segment_sane "$name"; then
    echo "SKIP unsafe folder segment: ${name}" >&2
    return 0
  fi
  local mobile_dir="$MOBILE/$name"
  if [[ ! -d "$mobile_dir" ]]; then
    echo "SKIP missing mobile folder: $mobile_dir" >&2
    return 0
  fi
  mkdir -p "$SRC/$name"
  "${RSYNC[@]}" "$mobile_dir/" "$SRC/$name/"
}

echo "import_mobile_vault: $MOBILE -> $SRC"

# Only authoring folders are imported back. Dashboards remain source-authoritative.
_rsync_back_folder "${VAULT_FOLDER_TASKS}"
_rsync_back_folder "${VAULT_FOLDER_GOALS}"
_rsync_back_folder "${VAULT_FOLDER_ROUTINES}"

echo "OK: mobile authoring changes imported from $MOBILE"
