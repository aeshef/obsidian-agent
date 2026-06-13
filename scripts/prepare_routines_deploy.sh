#!/usr/bin/env bash
# Prepare 400_Routines vault layout + stats scaffold locally (no deploy, no bot restart).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export AGENT_ROOT="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

if [[ -z "${VAULT_PATH:-}" ]]; then
  echo "Set VAULT_PATH in .env" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/vault_paths_defaults.sh"
vault_paths_load_from_agent "$ROOT" 2>/dev/null || vault_paths_apply_defaults

export AGENT_LOCALE="${AGENT_LOCALE:-ru}"
export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo "== prepare_routines: vault=$VAULT_PATH locale=$AGENT_LOCALE =="

(cd "$AGENT_ROOT" && ./scripts/oa-python.sh scripts/init_vault_layout.py --allow-missing-capabilities) || exit 1

(cd "$AGENT_ROOT" && ./scripts/oa-python.sh -c "
from planning_bot.services.routines_layout import ensure_routines_layout
for line in ensure_routines_layout(scaffold_stats=False):
    print('layout:', line)
") || exit 1

(cd "$AGENT_ROOT" && ./scripts/oa-python.sh scripts/scaffold_vault_routines.py --force) || exit 1

(cd "$AGENT_ROOT" && ./scripts/oa-python.sh planning_bot/services/routines_manager.py) || exit 1

_legacy="${VAULT_PATH}/${VAULT_FOLDER_ROUTINES:-400_Рутины}/${VAULT_FILE_ROUTINES_STATS_LEGACY_MD:-📊 Рутины_Статистика.md}"
if [[ -f "$_legacy" ]]; then
  rm -f "$_legacy"
  echo "removed legacy: $_legacy"
fi

echo ""
echo "Local vault ready. When knowledge ingest finishes:"
echo "  1. ./scripts/deploy.sh --prod"
echo "  2. ~/bin/obsidian_sync.sh   (or LaunchAgent sync cycle)"
echo ""
echo "Stats: ${VAULT_FOLDER_ROUTINES}/Графики/"
echo "Signals YAML: ${VAULT_FOLDER_ROUTINES}/📊 Сигналы/📋 Конфиг_Сигналов.yaml"
echo "Signals stub: ${VAULT_FOLDER_ROUTINES}/📊 Сигналы/📋 Конфиг_Сигналов.md"
