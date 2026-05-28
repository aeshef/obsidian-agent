#!/usr/bin/env bash
# CLI-обёртка bootstrap_python: env + PYTHONPATH + venv python.
#
#   eval "$(scripts/bootstrap_python.sh finance_bot --print)"
#   scripts/bootstrap_python.sh finance_bot -- python -c "import bot.main"
#   scripts/bootstrap_python.sh finance_bot --exec python scripts/build_finance_dashboard.py
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/bootstrap_python.sh
source "$ROOT/scripts/lib/bootstrap_python.sh"

COMPONENT="${1:?Usage: bootstrap_python.sh <finance_bot|knowledge_bot|planning_bot> [--print|--exec|--] [cmd...]}"
shift

bootstrap_python "$COMPONENT"

case "${1:-}" in
  --print)
    printf "export ROOT=%q MONOREPO=%q BOT_COMPONENT=%q PYTHON_CMD=%q PYTHONPATH=%q\n" \
      "$ROOT" "$MONOREPO" "$BOT_COMPONENT" "$PYTHON_CMD" "$PYTHONPATH"
    ;;
  --exec)
    shift
    exec "$PYTHON_CMD" "$@"
    ;;
  --)
    shift
    exec "$@"
    ;;
  "")
    echo "ROOT=$ROOT"
    echo "MONOREPO=$MONOREPO"
    echo "PYTHON_CMD=$PYTHON_CMD"
    echo "PYTHONPATH=$PYTHONPATH"
    ;;
  *)
    exec "$PYTHON_CMD" "$@"
    ;;
esac
