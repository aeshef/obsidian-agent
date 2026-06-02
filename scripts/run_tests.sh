#!/usr/bin/env bash
# Локальный прогон тестов (тот же PYTHONPATH, что в CI).
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
cp -n knowledge_bot/config/media_extensions.yaml.example knowledge_bot/config/media_extensions.yaml 2>/dev/null || true
cp -n knowledge_bot/config/tag_domains.yaml.example knowledge_bot/config/tag_domains.yaml 2>/dev/null || true
cp -n planning_bot/config/kanban_schema.yaml.example planning_bot/config/kanban_schema.yaml 2>/dev/null || true

PY="${ROOT}/finance_bot/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Run scripts/ensure_bot_venv.sh first" >&2
  exit 1
fi

"$PY" -m pip install -q pytest pytest-asyncio

ARGS=("$@")
if [[ ${#ARGS[@]} -eq 0 ]]; then
  ARGS=(tests/)
fi

exec "$PY" -m pytest "${ARGS[@]}" -q
