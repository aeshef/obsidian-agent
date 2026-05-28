#!/bin/bash
# Маппинг задач к целям (для cron). Запуск из корня: ./scripts/run_map_missing_goals.sh
# Cron: 0 * * * * cd /path/to/planning_bot && ./scripts/run_map_missing_goals.sh >> logs/map_goals.log 2>&1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

export PYTHONPATH="$(dirname "$ROOT")${PYTHONPATH:+:$PYTHONPATH}"
python3 -m planning_bot.tools.map_missing_goals "$@"
