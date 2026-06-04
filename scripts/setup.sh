#!/usr/bin/env bash
# Первичная настройка монорепо (локально): .env, venv, smoke.
# Usage: ./scripts/setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

echo "=== obsidian-agent setup ==="

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Создан $ROOT/.env — заполните токены и VAULT_PATH."
else
  echo "Используется существующий $ROOT/.env"
fi

common_load_env "$ROOT" 2>/dev/null || true

echo ""
echo "=== venv (per-bot, constraints.txt) ==="
bash "$ROOT/scripts/ensure_bot_venv.sh" all

echo ""
echo "=== check_env ==="
bash "$ROOT/scripts/check_env.sh" all || true

echo ""
echo "=== smoke ==="
export SMOKE_INSTALL=1
bash "$ROOT/scripts/smoke_imports.sh"

echo ""
echo "=== bot configs from *.example ==="
for pair in \
  "config/messages.ru.yaml:config/messages.ru.yaml.example" \
  "config/vault_paths.yaml:config/vault_paths.yaml.example" \
  "config/domain_messages.yaml:config/domain_messages.yaml.example" \
  "config/messages.en.yaml:config/messages.en.yaml.example" \
  "config/agent/platform.yaml:config/agent/platform.yaml.example" \
  "finance_bot/config/nlu_config.yaml:finance_bot/config/nlu_config.yaml.example" \
  "knowledge_bot/config/media_extensions.yaml:knowledge_bot/config/media_extensions.yaml.example" \
  "knowledge_bot/config/hubs_registry.yaml:knowledge_bot/config/hubs_registry.yaml.example"; do
  target="${pair%%:*}"
  example="${pair##*:}"
  if [ ! -f "$ROOT/$target" ] && [ -f "$ROOT/$example" ]; then
    cp "$ROOT/$example" "$ROOT/$target"
    echo "  created $target from example"
  fi
done

echo ""
echo "=== bot prompts (*.example.txt → *.txt, не перезаписываем) ==="
bash "$ROOT/scripts/ensure_bot_prompts.sh"
# pull_prompts_from_server.sh — author-only (see docs/_maintainer); optional local file
[ -x "$ROOT/scripts/pull_prompts_from_server.sh" ] && bash "$ROOT/scripts/pull_prompts_from_server.sh" 2>/dev/null || true
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
python3 "$ROOT/scripts/seed_planning_prompts.py" || true
bash "$ROOT/scripts/ensure_hubs_registry.sh" || true

echo ""
echo "=== tags prompt (knowledge) ==="
bash "$ROOT/scripts/ensure_tags_prompt.sh" || true

echo ""
echo "✅ Готово. Дальше:"
echo "  Модули:    docs/ONBOARDING.md  (или skill obsidian-agent-onboarding)"
echo "  Mac sync:  ./scripts/install_launchagent.sh"
echo "  Deploy:    ./scripts/deploy.sh --component all --install-deps"
echo "  Запуск:    python -m unified_bot.main  (см. docs/SETUP.md)"
