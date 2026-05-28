#!/usr/bin/env bash
# Сборка трёх sandbox-venv на ТОЧНОМ прод-питоне (3.12.7), как на сервере/в локальных venv.
# Полные прод-зависимости (как для polling), но боты не запускаются.
# Полные логи в venv_logs/<bot>.log (без обрезки).
set -uo pipefail

SANDBOX="${SANDBOX:-$HOME/obsidian-monorepo-sandbox}"
PY312="${PY312:-$HOME/.pyenv/versions/3.12.7/bin/python3}"
LOGDIR="$SANDBOX/venv_logs"
mkdir -p "$LOGDIR"

"$PY312" --version || { echo "Нет $PY312"; exit 1; }

# bot:venv_dir
SPECS=("planning_bot:venv" "finance_bot:.venv" "knowledge_bot:venv")

rc_total=0
for spec in "${SPECS[@]}"; do
  bot="${spec%%:*}"; vdir="${spec##*:}"
  log="$LOGDIR/$bot.log"
  echo "==== [$bot] $(date) — venv на $($PY312 --version 2>&1) ====" | tee "$log"
  rm -rf "$SANDBOX/$bot/$vdir"
  "$PY312" -m venv "$SANDBOX/$bot/$vdir" >>"$log" 2>&1
  pip="$SANDBOX/$bot/$vdir/bin/pip"
  "$pip" install --upgrade pip >>"$log" 2>&1
  echo "==== [$bot] pip install -r requirements.txt ====" | tee -a "$log"
  if "$pip" install -r "$SANDBOX/$bot/requirements.txt" >>"$log" 2>&1; then
    echo "✓ [$bot] OK ($("$pip" list 2>/dev/null | wc -l | tr -d ' ') пакетов)"
  else
    echo "✗ [$bot] FAILED — см. $log"; rc_total=1
  fi
done
echo "==== ALL DONE rc=$rc_total $(date) ===="
exit $rc_total
