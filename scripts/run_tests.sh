#!/usr/bin/env bash
# Локальный прогон тестов (как CI: finance .venv + knowledge .venv).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}:${ROOT}/finance_bot:${ROOT}/knowledge_bot:${ROOT}/planning_bot"
export DEPLOY_MODE="${DEPLOY_MODE:-single}"
export TELEGRAM_UNIFIED_BOT_TOKEN="${TELEGRAM_UNIFIED_BOT_TOKEN:-ci-smoke-test-token}"
export TELEGRAM_FINANCE_BOT_TOKEN="${TELEGRAM_FINANCE_BOT_TOKEN:-ci-smoke-test-token}"
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-ci-smoke-test-token}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-ci-smoke-test-key}"

cp finance_bot/config/nlu_config.yaml.example finance_bot/config/nlu_config.yaml 2>/dev/null || true
cp knowledge_bot/config/media_extensions.yaml.example knowledge_bot/config/media_extensions.yaml 2>/dev/null || true
cp knowledge_bot/config/tag_domains.yaml.example knowledge_bot/config/tag_domains.yaml 2>/dev/null || true
cp planning_bot/config/kanban_schema.yaml.example planning_bot/config/kanban_schema.yaml 2>/dev/null || true
cp finance_bot/config/analytics_categories.yaml.example finance_bot/config/analytics_categories.yaml 2>/dev/null || true

FIN_PY="${ROOT}/finance_bot/.venv/bin/python"
KB_PY="${ROOT}/knowledge_bot/.venv/bin/python"
if [[ ! -x "$FIN_PY" ]]; then
  echo "Run scripts/ensure_bot_venv.sh first" >&2
  exit 1
fi

"$FIN_PY" -m pip install -q pytest pytest-asyncio

ARGS=("$@")
if [[ ${#ARGS[@]} -eq 0 ]]; then
  FIN_TESTS=(
    tests/test_transaction_parse.py tests/test_llm_json.py tests/test_kanban_sort.py
    tests/test_finance_llm.py tests/test_transactions_core.py tests/test_agent_platform.py
    tests/test_calendar_sync.py tests/test_tag_normalize.py tests/test_entity_names.py
    tests/test_note_lookup.py tests/test_kanban_parse_substantive.py tests/test_kanban_columns_config.py
    tests/test_planning_agent_tools_imports.py
    tests/test_agent_progress.py tests/test_date_range.py tests/test_reference_date.py
    tests/test_host_knowledge_keyboard.py tests/test_finance_txn_query.py
    tests/test_brain_query_helpers.py
    tests/test_prompt_examples_are_stubs.py
    tests/test_capabilities.py tests/test_onboarding.py tests/test_prompt_filter.py
    tests/test_prompt_preamble.py tests/test_runtime_config.py tests/test_ui_bindings.py
    tests/test_profile_matrix.py tests/test_msg_capability_gate.py
    tests/test_agent_sanity.py tests/test_ui_patterns.py
  )
  echo "=== finance/planning/shared tests ==="
  "$FIN_PY" -m pytest "${FIN_TESTS[@]}" -q
  if [[ -x "$KB_PY" ]]; then
  "$KB_PY" -m pip install -q pytest 2>/dev/null || true
  echo "=== knowledge tests ==="
  "$KB_PY" -m pytest tests/test_note_complete.py -q
  fi
  exit 0
fi

exec "$FIN_PY" -m pytest "${ARGS[@]}" -q
