#!/bin/bash
# Общая инициализация для cron-скриптов planning_bot (source из cron_*.sh).
# Не запускать напрямую.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

if [ -f "$ROOT/../.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/../.env"
    set +a
fi
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

export PYTHONPATH="$ROOT:$(dirname "$ROOT")${PYTHONPATH:+:$PYTHONPATH}"

if [ -d "$ROOT/venv/bin" ]; then
    PY="$ROOT/venv/bin/python3"
elif [ -d "$ROOT/.venv/bin" ]; then
    PY="$ROOT/.venv/bin/python3"
else
    PY="python3"
fi

# Серверный fallback только если VAULT_PATH не задан (на Mac обычно задан в .env)
if [ -z "${VAULT_PATH:-}" ] && [ -n "${SERVER_VAULT:-}" ] && [ -d "${SERVER_VAULT}" ]; then
    export VAULT_PATH="$SERVER_VAULT"
fi
