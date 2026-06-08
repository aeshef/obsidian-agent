#!/usr/bin/env bash
# Единый venv-контракт: предпочитаем .venv, legacy venv → symlink .venv → venv.
#
#   scripts/ensure_bot_venv.sh finance_bot
#   scripts/ensure_bot_venv.sh finance_bot knowledge_bot
#   scripts/ensure_bot_venv.sh all --recreate   # пересоздать .venv + pip install
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

RECREATE=0
COMPONENTS=()

usage() {
  echo "Usage: ensure_bot_venv.sh <component|all> [component ...] [--recreate]" >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --recreate) RECREATE=1; shift ;;
    finance_bot|knowledge_bot|planning_bot|all) COMPONENTS+=("$1"); shift ;;
    -h|--help) usage ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage ;;
  esac
done

[ "${#COMPONENTS[@]}" -gt 0 ] || usage

_ensure_one() {
  local comp="$1"
  local bot_root="$ROOT/$comp"
  [ -d "$bot_root" ] || { echo "❌ нет каталога $bot_root" >&2; return 1; }

  if [ "$RECREATE" = 1 ]; then
    local py
    py="$(common_python_for_venv)"
    echo "📦 recreate .venv ($comp) via $py"
    rm -rf "$bot_root/.venv"
    "$py" -m venv "$bot_root/.venv"
    "$bot_root/.venv/bin/pip" install -q --upgrade pip
    if [ -f "$ROOT/constraints.txt" ]; then
      "$bot_root/.venv/bin/pip" install -q -r "$bot_root/requirements.txt" -c "$ROOT/constraints.txt"
    else
      "$bot_root/.venv/bin/pip" install -q -r "$bot_root/requirements.txt"
    fi
    echo "✅ $comp .venv готов ($("$bot_root/.venv/bin/python" -V))"
    return 0
  fi

  common_ensure_bot_venv "$bot_root"
  local py
  py="$(common_resolve_python "$bot_root")"
  echo "✅ $comp → $py ($("$py" -V 2>&1))"
  if ! common_require_python_min "$py" 3 9; then
    echo "❌ Python < 3.9" >&2
    return 1
  fi
}

_expand_components() {
  local c
  for c in "${COMPONENTS[@]}"; do
    if [ "$c" = all ]; then
      echo finance_bot
      echo knowledge_bot
      echo planning_bot
    else
      echo "$c"
    fi
  done
}

failed=0
while IFS= read -r comp; do
  [ -n "$comp" ] || continue
  _ensure_one "$comp" || failed=1
done < <(_expand_components | awk '!seen[$0]++')

exit "$failed"
