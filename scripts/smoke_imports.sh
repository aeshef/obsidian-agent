#!/usr/bin/env bash
# Smoke: py_compile + import ключевых модулей (локально или в CI с SMOKE_INSTALL=1).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib/bootstrap_python.sh
source "$ROOT/scripts/lib/bootstrap_python.sh"

INSTALL="${SMOKE_INSTALL:-0}"
FAILED=0

echo "=== py_compile (без зависимостей) ==="
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if ! python3 -m py_compile "$f" 2>/dev/null; then
    echo "  FAIL $f" >&2
    FAILED=1
  fi
done <<EOF
$(find "$ROOT"/shared "$ROOT"/finance_bot/bot "$ROOT"/knowledge_bot "$ROOT"/planning_bot \
  -name '*.py' ! -path '*/venv/*' ! -path '*/.venv/*' ! -path '*/__pycache__/*' 2>/dev/null)
EOF
[ "$FAILED" -eq 0 ] && echo "  compile OK"

_smoke_import() {
  local comp="$1" code="$2"
  echo -n "  import $comp: "
  local venv_py=""
  for v in .venv venv; do
    [ -x "$ROOT/$comp/$v/bin/python" ] && venv_py="$ROOT/$comp/$v/bin/python"
  done
  if [ -n "$venv_py" ] && [ "$INSTALL" != 1 ]; then
    if ! "$venv_py" -m pip show -q requests 2>/dev/null; then
      echo "SKIP (venv without deps, set SMOKE_INSTALL=1)"
      return 0
    fi
  fi
  if [ -z "$venv_py" ] && [ "$INSTALL" != 1 ]; then
    echo "SKIP (no venv, set SMOKE_INSTALL=1)"
    return 0
  fi
  if ! bootstrap_python "$comp" 2>/dev/null; then
    echo "FAIL bootstrap" >&2
    FAILED=1
    return
  fi
  if [ "$INSTALL" = 1 ]; then
    "$PYTHON_CMD" -m pip install -q --upgrade pip
    local cons=()
    [ -f "$ROOT/constraints.txt" ] && cons=(-c "$ROOT/constraints.txt")
    "$PYTHON_CMD" -m pip install -q -r "$ROOT/$comp/requirements.txt" "${cons[@]}"
  fi
  if "$PYTHON_CMD" -c "$code" 2>/dev/null; then
    echo OK
  else
    echo FAIL >&2
    "$PYTHON_CMD" -c "$code" 2>&1 | tail -5 >&2 || true
    FAILED=1
  fi
}

echo "=== import smoke ==="
_smoke_import finance_bot 'import bot.main'
_smoke_import knowledge_bot 'from knowledge_bot.app.bot import main'
_smoke_import planning_bot 'from planning_bot.tools.vault_maintenance import run_all'

if bootstrap_python finance_bot 2>/dev/null; then
  if "$PYTHON_CMD" -c 'import shared.bootstrap, shared.charts.mermaid' 2>/dev/null; then
    echo "  import shared: OK"
  else
    echo "  import shared: SKIP (deps)" >&2
  fi
fi

if [ "$FAILED" -ne 0 ]; then
  echo "❌ smoke_imports FAILED" >&2
  exit 1
fi
echo "✅ smoke_imports OK"
