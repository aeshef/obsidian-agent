#!/usr/bin/env bash
# Единый venv-контракт: предпочитаем .venv, legacy venv → symlink .venv → venv.
#
#   scripts/ensure_bot_venv.sh finance_bot
#   scripts/ensure_bot_venv.sh all --recreate   # python3.10+ venv + pip install
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

RECREATE=0
COMPONENT="${1:?Usage: ensure_bot_venv.sh <component|all> [--recreate]}"

shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --recreate) RECREATE=1; shift ;;
    *) echo "Неизвестный флаг: $1" >&2; exit 2 ;;
  esac
done

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
    local cons=()
    [ -f "$ROOT/constraints.txt" ] && cons=(-c "$ROOT/constraints.txt")
    "$bot_root/.venv/bin/pip" install -q -r "$bot_root/requirements.txt" "${cons[@]}"
    echo "✅ $comp .venv готов ($("$bot_root/.venv/bin/python" -V))"
    return 0
  fi

  common_ensure_bot_venv "$bot_root"
  local py
  py="$(common_resolve_python "$bot_root")"
  echo "✅ $comp → $py ($("$py" -V 2>&1))"
  if ! common_require_python_min "$py" 3 10; then
    echo "⚠️  Python < 3.10 — запустите: $0 $comp --recreate" >&2
    return 1
  fi
}

case "$COMPONENT" in
  all)
    failed=0
    for c in finance_bot knowledge_bot planning_bot; do
      _ensure_one "$c" || failed=1
    done
    exit "$failed"
    ;;
  finance_bot|knowledge_bot|planning_bot) _ensure_one "$COMPONENT" ;;
  *) echo "Неизвестный компонент: $COMPONENT" >&2; exit 2 ;;
esac
