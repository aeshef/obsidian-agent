#!/usr/bin/env bash
# Первичная настройка монорепо (локально): .env, venv, smoke.
# Usage: ./scripts/setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
# shellcheck source=scripts/lib/sh_msg.sh
source "$ROOT/scripts/lib/sh_msg.sh"

sh_msg scripts.setup.title

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  sh_msgf scripts.setup.env_created "{\"path\":\"$ROOT\"}"
else
  sh_msgf scripts.setup.env_exists "{\"path\":\"$ROOT\"}"
fi

common_load_env "$ROOT" 2>/dev/null || true

echo ""
sh_msg scripts.setup.section_venv
bash "$ROOT/scripts/ensure_bot_venv.sh" all
OA_PY="$(common_resolve_python "$ROOT/finance_bot")"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

echo ""
sh_msg scripts.setup.section_check_env
bash "$ROOT/scripts/check_env.sh" all || true

echo ""
sh_msg scripts.setup.section_smoke
export SMOKE_INSTALL=1
bash "$ROOT/scripts/smoke_imports.sh"

echo ""
sh_msg scripts.setup.section_locale
AGENT_LOCALE="${AGENT_LOCALE:-en}"
if ! grep -q '^AGENT_LOCALE=' "$ROOT/.env" 2>/dev/null; then
  echo "AGENT_LOCALE=${AGENT_LOCALE}" >> "$ROOT/.env"
  sh_msgf scripts.setup.locale_set "{\"locale\":\"$AGENT_LOCALE\"}"
fi
"$OA_PY" "$ROOT/scripts/setup/materialize_locale.py" "${AGENT_LOCALE}"

echo ""
sh_msg scripts.setup.section_bot_configs
for pair in \
  "config/messages.ru.yaml:config/messages.ru.yaml.example" \
  "config/agent/platform.yaml:config/agent/platform.yaml.example" \
  "finance_bot/config/nlu_config.yaml:finance_bot/config/nlu_config.yaml.example" \
  "knowledge_bot/config/media_extensions.yaml:knowledge_bot/config/media_extensions.yaml.example" \
  "knowledge_bot/config/hubs_registry.yaml:knowledge_bot/config/hubs_registry.yaml.example"; do
  target="${pair%%:*}"
  example="${pair##*:}"
  if [ ! -f "$ROOT/$target" ] && [ -f "$ROOT/$example" ]; then
    cp "$ROOT/$example" "$ROOT/$target"
    sh_msgf scripts.setup.created_from_example "{\"target\":\"$target\"}"
  fi
done

echo ""
sh_msg scripts.setup.prompts_header
bash "$ROOT/scripts/ensure_bot_prompts.sh"
# pull_prompts_from_server.sh — author-only (gitignored); optional local file
if [ -x "$ROOT/scripts/pull_prompts_from_server.sh" ]; then
  bash "$ROOT/scripts/pull_prompts_from_server.sh" 2>/dev/null || true
fi
if "$OA_PY" -c "from shared.capabilities.profile import get_capabilities, MODULE_PLANNING; import sys; sys.exit(0 if get_capabilities().module(MODULE_PLANNING) else 1)" 2>/dev/null; then
  "$OA_PY" "$ROOT/scripts/seed_planning_prompts.py" || true
fi
bash "$ROOT/scripts/ensure_hubs_registry.sh" || true

echo ""
sh_msg scripts.setup.section_tags_prompt
bash "$ROOT/scripts/ensure_tags_prompt.sh" || true

if [ -n "${VAULT_PATH:-}" ] && [ -d "${VAULT_PATH}" ] && [ -f "$ROOT/config/agent/capabilities.yaml" ]; then
  echo ""
  sh_msg scripts.setup.section_obsidian
  "$OA_PY" "$ROOT/scripts/install_obsidian_setup.py" 2>/dev/null || true
  "$OA_PY" "$ROOT/scripts/scaffold_vault_dashboards.py" 2>/dev/null || true
fi

echo ""
sh_msg scripts.setup.done
sh_msg scripts.setup.next_onboarding
sh_msg scripts.setup.next_obsidian
sh_msg scripts.setup.next_mac_sync
sh_msg scripts.setup.next_deploy
sh_msg scripts.setup.next_run
