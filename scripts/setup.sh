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
  "finance_bot/config/nlu_config.yaml:finance_bot/config/nlu_config.yaml.example" \
  "knowledge_bot/config/media_extensions.yaml:knowledge_bot/config/media_extensions.yaml.example"; do
  target="${pair%%:*}"
  example="${pair##*:}"
  if [ ! -f "$ROOT/$target" ] && [ -f "$ROOT/$example" ]; then
    cp "$ROOT/$example" "$ROOT/$target"
    echo "  created $target from example"
  fi
done

echo ""
echo "=== tags prompt (knowledge) ==="
bash "$ROOT/scripts/ensure_tags_prompt.sh" || true

echo ""
echo "✅ Готово. Дальше:"
echo "  Mac sync:  ./scripts/install_launchagent.sh"
echo "  Deploy:    ./scripts/deploy.sh --component all --install-deps"
echo "  Запуск:    <bot>/scripts/run.sh"
