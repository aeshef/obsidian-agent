#!/usr/bin/env bash
# Capability-aware primary setup: .env, scoped venvs, gated configs.
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

# Resolve which bot venvs to create (default: finance_bot always for shared deps)
_VENV_ARGS=(finance_bot)
if [ -f "$ROOT/config/agent/capabilities.yaml" ]; then
  _mods="$("$ROOT/scripts/oa-python.sh" -c "
from shared.capabilities.profile import get_capabilities, clear_capabilities_cache, MODULE_PLANNING, MODULE_KNOWLEDGE
clear_capabilities_cache()
p=get_capabilities()
print('planning' if p.module(MODULE_PLANNING) else '')
print('knowledge' if p.module(MODULE_KNOWLEDGE) else '')
" 2>/dev/null || true)"
  echo "$_mods" | grep -q planning && _VENV_ARGS+=(planning_bot)
  echo "$_mods" | grep -q knowledge && _VENV_ARGS+=(knowledge_bot)
else
  # No capabilities yet — minimal host deps only (wizard writes profile next)
  _VENV_ARGS=(finance_bot)
fi

echo ""
sh_msg scripts.setup.section_venv
bash "$ROOT/scripts/ensure_bot_venv.sh" "${_VENV_ARGS[@]}"
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
# Always-safe shared configs
for pair in \
  "config/agent/platform.yaml:config/agent/platform.yaml.example"; do
  target="${pair%%:*}"
  example="${pair##*:}"
  if [ ! -f "$ROOT/$target" ] && [ -f "$ROOT/$example" ]; then
    cp "$ROOT/$example" "$ROOT/$target"
    sh_msgf scripts.setup.created_from_example "{\"target\":\"$target\"}"
  fi
done
# Module-gated
if [ -f "$ROOT/config/agent/capabilities.yaml" ]; then
  _has_fin="$("$OA_PY" -c "from shared.capabilities.profile import get_capabilities,MODULE_FINANCE; import sys; sys.exit(0 if get_capabilities().module(MODULE_FINANCE) else 1)" && echo 1 || echo 0)"
  _has_kb="$("$OA_PY" -c "from shared.capabilities.profile import get_capabilities,MODULE_KNOWLEDGE; import sys; sys.exit(0 if get_capabilities().module(MODULE_KNOWLEDGE) else 1)" && echo 1 || echo 0)"
  _has_pl="$("$OA_PY" -c "from shared.capabilities.profile import get_capabilities,MODULE_PLANNING; import sys; sys.exit(0 if get_capabilities().module(MODULE_PLANNING) else 1)" && echo 1 || echo 0)"
else
  _has_fin=0; _has_kb=0; _has_pl=0
fi
if [ "$_has_fin" = 1 ]; then
  for pair in \
    "finance_bot/config/nlu_config.yaml:finance_bot/config/nlu_config.yaml.example"; do
    target="${pair%%:*}"; example="${pair##*:}"
    if [ ! -f "$ROOT/$target" ] && [ -f "$ROOT/$example" ]; then
      cp "$ROOT/$example" "$ROOT/$target"
      sh_msgf scripts.setup.created_from_example "{\"target\":\"$target\"}"
    fi
  done
fi
if [ "$_has_kb" = 1 ]; then
  for pair in \
    "knowledge_bot/config/media_extensions.yaml:knowledge_bot/config/media_extensions.yaml.example" \
    "knowledge_bot/config/hubs_registry.yaml:knowledge_bot/config/hubs_registry.yaml.example"; do
    target="${pair%%:*}"; example="${pair##*:}"
    if [ ! -f "$ROOT/$target" ] && [ -f "$ROOT/$example" ]; then
      cp "$ROOT/$example" "$ROOT/$target"
      sh_msgf scripts.setup.created_from_example "{\"target\":\"$target\"}"
    fi
  done
fi

echo ""
sh_msg scripts.setup.prompts_header
bash "$ROOT/scripts/ensure_bot_prompts.sh"
if [ -x "$ROOT/scripts/pull_prompts_from_server.sh" ]; then
  bash "$ROOT/scripts/pull_prompts_from_server.sh" 2>/dev/null || true
fi
if [ "$_has_pl" = 1 ]; then
  "$OA_PY" "$ROOT/scripts/seed_planning_prompts.py" || true
fi
if [ "$_has_kb" = 1 ]; then
  bash "$ROOT/scripts/ensure_hubs_registry.sh" || true
  echo ""
  sh_msg scripts.setup.section_tags_prompt
  bash "$ROOT/scripts/ensure_tags_prompt.sh" || true
fi

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
