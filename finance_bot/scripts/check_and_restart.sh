#!/usr/bin/env bash
# Интерактивная проверка finance_bot на сервере
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/common.sh"
common_load_env "$ROOT"
common_require_server
SERVER_BOTS="$(common_server_bots)"

echo "=== Процессы ==="
common_ssh "pgrep -af 'bot.main|watchdog' | head -5 || echo 'нет процессов'"

echo "=== Лог (хвост) ==="
common_ssh "cd ${SERVER_BOTS}/finance_bot && tail -30 logs/bot.log 2>/dev/null || echo 'лог пуст'"

read -r -p "Перезапустить? [y/N] " ans
if [[ "$ans" =~ ^[Yy]$ ]]; then
  exec "$ROOT/scripts/deploy.sh" --component finance_bot
fi
