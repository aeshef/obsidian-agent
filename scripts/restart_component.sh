#!/usr/bin/env bash
# Перезапуск одного бота на сервере (rsync + watchdog restart).
# Usage: ./scripts/restart_component.sh finance_bot|knowledge_bot|planning_bot
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMP="${1:?Usage: restart_component.sh <finance_bot|knowledge_bot|planning_bot>}"
exec "$ROOT/scripts/deploy.sh" --component "$COMP"
