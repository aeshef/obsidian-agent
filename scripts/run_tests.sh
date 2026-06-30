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
export AGENT_LOCALE="${AGENT_LOCALE:-en}"

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
# shared/analytics (Spearman, FDR) — scipy is in planning_bot/requirements, not finance_bot
"$FIN_PY" -m pip install -q "scipy>=1.11.0"

ARGS=("$@")
if [[ ${#ARGS[@]} -eq 0 ]]; then
  echo "=== finance/planning/shared tests (full suite) ==="
  "$FIN_PY" -m pytest tests/ -q \
    --ignore=tests/test_note_complete.py \
    --ignore=tests/test_note_lookup.py \
    --ignore=tests/test_ocr_profile.py
  if [[ -x "$KB_PY" ]]; then
    "$KB_PY" -m pip install -q pytest 2>/dev/null || true
    echo "=== knowledge tests ==="
    "$KB_PY" -m pytest tests/test_note_complete.py tests/test_note_lookup.py tests/test_ocr_profile.py -q
  fi
  exit 0
fi

exec "$FIN_PY" -m pytest "${ARGS[@]}" -q
