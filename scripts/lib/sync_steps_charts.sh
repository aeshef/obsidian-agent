# shellcheck shell=bash
# Chart / dashboard rebuild steps for obsidian_sync (planning, calendar, nutrition, finance).
# Sourced by scripts/obsidian_sync.sh — do not run standalone.

sync_steps_charts_planning() {
# 5. Графики дашборда по action-логам: раз в день + повтор, если лог месяца новее маркера сборки (конец дня).
# Иначе прогон в 00:03 ставит маркер «сегодня», а события дня в графики не попадают до следующей полуночи.
# FORCE_CHARTS=1 ~/bin/obsidian_sync.sh
MARKER="$SYNC_DIR/daily_charts_date.txt"
LOGS_DIR="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_LOGS}"
_CUR_LOG="$LOGS_DIR/${VAULT_FILE_ACTION_LOG_PREFIX}$(date +%Y-%m).md"
HAS_LOGS=
[ -d "$LOGS_DIR" ] && [ "$(find "$LOGS_DIR" -maxdepth 1 -name "${VAULT_FILE_ACTION_LOG_PREFIX}*.md" 2>/dev/null | wc -l)" -gt 0 ] && HAS_LOGS=1

# 5b-pre. Goals mapping reconcile — before planning charts so kanban WIP segments use fresh mapping.
if cap_module_enabled PLANNING; then
  PLANNING_BOT="${PLANNING_BOT:-$AGENT_ROOT/planning_bot}"
  if [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_goals_mapping_review.py" ]; then
    export VAULT_PATH="$LOCAL_VAULT"
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
    _gmr_py="${CHART_PYTHON:-python3}"
    cd "$PLANNING_BOT" && common_run_python_script "$_gmr_py" "$PLANNING_BOT/scripts/build_goals_mapping_review.py" --vault "$LOCAL_VAULT" --reconcile --json >> logs/charts.log 2>&1 || true
  fi
fi
unset _gmr_py

if cap_step_enabled SYNC_PLANNING_CHARTS && [ -n "$CHART_PYTHON" ]; then
  VAULT_PATH="$LOCAL_VAULT" PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}" \
    "$CHART_PYTHON" "$AGENT_ROOT/planning_bot/scripts/build_task_completions_index.py" --vault "$LOCAL_VAULT" \
    >> "$AGENT_ROOT/planning_bot/logs/charts.log" 2>&1 || _sync_fail "task-completions-index"
fi

_SHOULD_CHARTS=0
if [ -n "${FORCE_CHARTS:-}" ] || [ ! -f "$MARKER" ] || [ "$(cat "$MARKER" 2>/dev/null)" != "$TODAY" ] || [ "$_CUR_LOG" -nt "$MARKER" ]; then
  _SHOULD_CHARTS=1
fi
if ! cap_step_enabled SYNC_PLANNING_CHARTS; then
  _SHOULD_CHARTS=0
fi
if [ "$_SHOULD_CHARTS" = "1" ]; then
  PLANNING_BOT="$AGENT_ROOT/planning_bot"
  if [ -n "$HAS_LOGS" ] && [ -n "$CHART_PYTHON" ] && [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_open_tasks_snapshot.py" ]; then
    echo "$(sh_msgf scripts.obsidian_sync.step_5_charts '{"python":"'$CHART_PYTHON'","log":"'$PLANNING_BOT/logs/charts.log'"}')" >&2
    export LOCAL_VAULT
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
    if cd "$PLANNING_BOT" && common_run_python_script "$CHART_PYTHON" "$PLANNING_BOT/scripts/build_open_tasks_snapshot.py" --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1 \
       && common_run_python_script "$CHART_PYTHON" "$PLANNING_BOT/scripts/build_kanban_flow_dashboard.py" --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1; then
      echo "$TODAY" > "$MARKER"
    else
      echo "$(sh_msg scripts.obsidian_sync.step_5_charts_fail)" >&2
      _sync_fail "5-planning-charts"
    fi
  fi
fi
# Interactive charts consume JSON, not the PNGs above. Refresh on every sync,
# including runs where the daily/static-chart marker is already current.
if cap_step_enabled SYNC_PLANNING_CHARTS && [ -n "$CHART_PYTHON" ]; then
  VAULT_PATH="$LOCAL_VAULT" PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}" \
    "$CHART_PYTHON" -m unified_bot.integrations.dashboard_datasets --vault "$LOCAL_VAULT" \
    >> "$AGENT_ROOT/planning_bot/logs/charts.log" 2>&1 || _sync_fail "planning-interactive-data"
fi
unset _SHOULD_CHARTS _CUR_LOG
}

sync_steps_charts_calendar() {
# 5c. PNG встреч (calendar_sync) — раз в день + если JSON календаря новее PNG.
CAL_MARKER="$SYNC_DIR/calendar_charts_date.txt"
_CAL_JSON="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_DATA}/${VAULT_FILE_CALENDAR_JSON}"
_CAL_TXT="${_CAL_JSON%.json}.txt"
_CAL_PNG="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_DATA}/Assistant UI/calendar.json"
PLANNING_BOT="${PLANNING_BOT:-$AGENT_ROOT/planning_bot}"
_SHOULD_CAL=0
if [ -n "${FORCE_CHARTS:-}" ]; then
  _SHOULD_CAL=1
elif [ ! -f "$CAL_MARKER" ] || [ "$(cat "$CAL_MARKER" 2>/dev/null)" != "$TODAY" ]; then
  _SHOULD_CAL=1
elif [ ! -f "$_CAL_PNG" ] || [ ! -f "$_CAL_JSON" ]; then
  _SHOULD_CAL=1
elif [ -f "$_CAL_TXT" ] && [ "$_CAL_TXT" -nt "$_CAL_JSON" ]; then
  _SHOULD_CAL=1
elif [ -f "$_CAL_JSON" ] && [ -f "$_CAL_PNG" ]; then
  _cal_j=$(stat -f '%m' "$_CAL_JSON" 2>/dev/null || echo 0)
  _cal_p=$(stat -f '%m' "$_CAL_PNG" 2>/dev/null || echo 0)
  [ "$_cal_j" -gt "$_cal_p" ] && _SHOULD_CAL=1
fi
if ! cap_step_enabled SYNC_CALENDAR; then
  _SHOULD_CAL=0
fi
if [ "$_SHOULD_CAL" = "1" ]; then
  if [ -n "$CHART_PYTHON" ] && [ -d "$PLANNING_BOT" ]; then
    echo "$(sh_msgf scripts.obsidian_sync.step_5c '{"python":"'$CHART_PYTHON'","log":"logs/charts.log"}')" >&2
    export LOCAL_VAULT
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
    if cd "$PLANNING_BOT" && common_run_python_script "$CHART_PYTHON" "$PLANNING_BOT/tools/calendar_sync.py" >> logs/charts.log 2>&1; then
      echo "$TODAY" > "$CAL_MARKER"
    else
      echo "$(sh_msg scripts.obsidian_sync.step_5c_fail)" >&2
      _sync_fail "5c-calendar-charts"
    fi
  fi
fi
unset _SHOULD_CAL _CAL_JSON _CAL_TXT _CAL_PNG _cal_j _cal_p
}

sync_steps_charts_agent_cost() {
# 5c.1 Стоимость агента — traces с VPS → PNG/MD в Графики/Система/ + хаб 🛠 Система.md.
# Не валим весь sync при SSH-флапе: трейсы живут только на сервере, без них графики просто остаются вчерашними.
# Тянем jsonl каждый цикл (файл маленький). PNG пересобираем, когда содержимое traces
# изменилось / нет картинки / FORCE. Старый маркер «уже сегодня» + TRACE_DAY==TODAY
# оставлял хаб с свежей датой и графики на утреннем снимке.
AGENT_COST_MARKER="$SYNC_DIR/agent_cost_dashboard_date.txt"
_AC_COST_PNG="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_DATA}/Assistant UI/system.json"
_TRACE_LOCAL="$AGENT_ROOT/logs/agent_traces.jsonl"
_AC_LOG="$AGENT_ROOT/logs/agent_cost_dashboard.log"
_rebuild_system_hub() {
  PLANNING_BOT="${PLANNING_BOT:-$AGENT_ROOT/planning_bot}"
  if [ ! -f "$PLANNING_BOT/scripts/build_system_dashboard_hub.py" ]; then
    return 0
  fi
  export VAULT_PATH="$LOCAL_VAULT"
  export LOCAL_VAULT
  export PYTHONPATH="${CHART_PYTHONPATH:-$AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  _hub_py="${CHART_PYTHON:-}"
  if [ -z "$_hub_py" ] && [ -x "$AGENT_ROOT/planning_bot/venv/bin/python" ]; then
    _hub_py="$AGENT_ROOT/planning_bot/venv/bin/python"
  fi
  [ -z "$_hub_py" ] && _hub_py=python3
  mkdir -p "$PLANNING_BOT/logs" 2>/dev/null || true
  (cd "$PLANNING_BOT" && common_run_python_script "$_hub_py" "$PLANNING_BOT/scripts/build_system_dashboard_hub.py" \
      --vault "$LOCAL_VAULT") >>"$PLANNING_BOT/logs/charts.log" 2>&1 || true
  unset _hub_py
}
_ac_build_dashboard() {
  _AC_PY="${CHART_PYTHON:-}"
  if [ -z "$_AC_PY" ] && [ -x "$AGENT_ROOT/planning_bot/venv/bin/python" ]; then
    _AC_PY="$AGENT_ROOT/planning_bot/venv/bin/python"
  fi
  if [ -z "$_AC_PY" ] || [ ! -f "$AGENT_ROOT/scripts/build_agent_cost_dashboard.py" ]; then
    return 1
  fi
  export LOCAL_VAULT AGENT_ROOT
  export PYTHONPATH="${AGENT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
  (cd "$AGENT_ROOT" && common_run_python_script "$_AC_PY" "$AGENT_ROOT/scripts/build_agent_cost_dashboard.py" \
      --vault "$LOCAL_VAULT" --days 30 --path "$_TRACE_LOCAL") >>"$_AC_LOG" 2>&1
}
mkdir -p "$AGENT_ROOT/logs" 2>/dev/null || true
_AC_CHANGED=0
_AC_FORCE=0
if [ -n "${FORCE_CHARTS:-}" ] || [ -n "${FORCE_AGENT_COST:-}" ]; then
  _AC_FORCE=1
fi
if [ -n "$SERVER" ] && [ -n "$SERVER_BOTS" ]; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=5c.1-agent-cost" >> "$DEBUG_LOG" 2>/dev/null || true
  _TRACE_TMP="${_TRACE_LOCAL}.scp.$$"
  if scp "${SSH_OPTS[@]}" "$SERVER:$SERVER_BOTS/logs/agent_traces.jsonl" "$_TRACE_TMP" >>"$_AC_LOG" 2>&1; then
    if [ ! -f "$_TRACE_LOCAL" ] || ! cmp -s "$_TRACE_TMP" "$_TRACE_LOCAL"; then
      mv -f "$_TRACE_TMP" "$_TRACE_LOCAL"
      _AC_CHANGED=1
    else
      rm -f "$_TRACE_TMP"
    fi
  else
    rm -f "$_TRACE_TMP"
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=5c.1-agent-cost scp-fail (soft)" >> "$DEBUG_LOG" 2>/dev/null || true
  fi
  unset _TRACE_TMP
fi
_SHOULD_AGENT_COST=0
if [ "$_AC_FORCE" = "1" ]; then
  _SHOULD_AGENT_COST=1
elif [ ! -f "$_AC_COST_PNG" ]; then
  _SHOULD_AGENT_COST=1
elif [ "$_AC_CHANGED" = "1" ]; then
  _SHOULD_AGENT_COST=1
elif [ -f "$_TRACE_LOCAL" ] && [ "$_TRACE_LOCAL" -nt "$_AC_COST_PNG" ]; then
  _SHOULD_AGENT_COST=1
fi
if [ "$_SHOULD_AGENT_COST" = "1" ] && [ -f "$_TRACE_LOCAL" ]; then
  if _ac_build_dashboard; then
    echo "$TODAY" > "$AGENT_COST_MARKER"
    _rebuild_system_hub
  else
    echo "$(date '+%Y-%m-%dT%H:%M:%S') pid=$$ step=5c.1-agent-cost build-fail (see logs/agent_cost_dashboard.log)" >> "$DEBUG_LOG" 2>/dev/null || true
  fi
fi
unset _SHOULD_AGENT_COST _AC_COST_PNG _TRACE_LOCAL _AC_LOG _AC_CHANGED _AC_FORCE _AC_PY
}

sync_steps_charts_nutrition_health() {
# Health and nutrition observations are exported by the health hub below each sync.
# 5d-c. Cross-domain analytics
_CROSS_MARKER="$SYNC_DIR/daily_cross_analytics_date.txt"
_SHOULD_CROSS=1
if ! cap_step_enabled SYNC_CROSS_ANALYTICS; then
  _SHOULD_CROSS=0
fi
if [ "$_SHOULD_CROSS" = "1" ]; then
  if [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_cross_domain_analytics.py" ]; then
    export VAULT_PATH="$LOCAL_VAULT"
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
    _nutr_py="${CHART_PYTHON:-python3}"
    if cd "$PLANNING_BOT" && common_run_python_script "$_nutr_py" "$PLANNING_BOT/scripts/build_cross_domain_analytics.py" --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1; then
      echo "$TODAY" > "$_CROSS_MARKER"
    fi
  fi
  if [ -f "$PLANNING_BOT/scripts/build_analytics_insights.py" ]; then
    export VAULT_PATH="$LOCAL_VAULT"
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
    _nutr_py="${CHART_PYTHON:-python3}"
    cd "$PLANNING_BOT" && common_run_python_script "$_nutr_py" "$PLANNING_BOT/scripts/build_analytics_insights.py" --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1 || true
  fi
  if [ -f "$PLANNING_BOT/scripts/build_analytics_dashboard_hub.py" ]; then
    export VAULT_PATH="$LOCAL_VAULT"
    export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
    _nutr_py="${CHART_PYTHON:-python3}"
    cd "$PLANNING_BOT" && common_run_python_script "$_nutr_py" "$PLANNING_BOT/scripts/build_analytics_dashboard_hub.py" --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1 || true
  fi
fi
unset _SHOULD_CROSS _CROSS_MARKER

# 5d-c2. System hub — каждый цикл (дешёвый markdown), не только при daily CROSS.
# Иначе после переезда Аналитика→Система хаб остаётся пустым до следующего дня.
if [ -d "${PLANNING_BOT:-}" ] && [ -f "$PLANNING_BOT/scripts/build_system_dashboard_hub.py" ]; then
  _rebuild_system_hub
fi

# 5d-d. Health hub markdown (locale template; not overwritten by nutrition chart)
if cap_step_enabled SYNC_HEALTH_ANALYTICS && [ -d "$PLANNING_BOT" ] && [ -f "$PLANNING_BOT/scripts/build_health_dashboard_hub.py" ]; then
  export VAULT_PATH="$LOCAL_VAULT"
  export PYTHONPATH="${CHART_PYTHONPATH}${PYTHONPATH:+:$PYTHONPATH}"
  _nutr_py="${CHART_PYTHON:-python3}"
  if (cd "$PLANNING_BOT" && common_run_python_script "$_nutr_py" "$PLANNING_BOT/scripts/build_health_dashboard_hub.py" --vault "$LOCAL_VAULT" >> logs/charts.log 2>&1); then
    echo "$TODAY" > "$SYNC_DIR/daily_iphone_nutrition_date.txt"
    echo "$TODAY" > "$SYNC_DIR/daily_health_analytics_date.txt"
  else
    _sync_fail "health-interactive-data"
  fi
fi
}

sync_steps_charts_finance() {
# 6. Финансы: каждый синк — pull канонической БД с сервера; PNG/markdown — раз в день или FORCE
FINANCE_MARKER="$SYNC_DIR/finance_dashboard_date.txt"
FINANCE_BOT="$AGENT_ROOT/finance_bot"
FIN_DB="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_DATA}/finance.db"
FIN_CHART_REF="$LOCAL_VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_DATA}/Assistant UI/finance.json"
FIN_DB_NEWER=
if [ -f "$FIN_DB" ] && [ -f "$FIN_CHART_REF" ] && [ "$FIN_DB" -nt "$FIN_CHART_REF" ]; then
  FIN_DB_NEWER=1
fi
if cap_step_enabled SYNC_FINANCE_DASHBOARD && [ -d "$FINANCE_BOT" ] && [ -f "$FINANCE_BOT/scripts/sync_finance_db.sh" ]; then
  if [ -n "$SYNC_STATE_DIR" ]; then FIN_LOG="$SYNC_DIR/finance_dashboard_daily.log"; else FIN_LOG="$FINANCE_BOT/logs/finance_dashboard_daily.log"; fi
  mkdir -p "$(dirname "$FIN_LOG")" 2>/dev/null || true
  _FIN_BUILD=0
  if [ -n "${FORCE_FINANCE_DASHBOARD:-}" ] || [ -n "$FIN_DB_NEWER" ] || [ ! -f "$FIN_CHART_REF" ] || [ ! -f "$FINANCE_MARKER" ] || [ "$(cat "$FINANCE_MARKER" 2>/dev/null)" != "$TODAY" ]; then
    _FIN_BUILD=1
  fi
  echo "$(sh_msgf scripts.obsidian_sync.step_6 '{"build":"'${_FIN_BUILD}'","log":"'$FIN_LOG'"}')" >&2
  export VAULT_PATH="$LOCAL_VAULT"
  if [ "$_FIN_BUILD" = "1" ]; then
    if (cd "$FINANCE_BOT" && ./scripts/run_finance_dashboard_daily.sh >> "$FIN_LOG" 2>&1); then
      echo "$TODAY" > "$FINANCE_MARKER"
      echo "$NOW_ISO" > "$SYNC_DIR/finance_dashboard_last_ok.txt"
    else
      echo "⚠️ finance dashboard build failed (see $FIN_LOG)" >&2
      SYNC_OK=0
    fi
  else
    if ! (
      FINANCE_REFRESH_BROKER_BEFORE_PULL=0
      FINANCE_BUILD_DASHBOARD_AFTER_PULL=0
      cd "$FINANCE_BOT" && ./scripts/sync_finance_db.sh >> "$FIN_LOG" 2>&1
    ); then
      echo "⚠️ finance.db pull failed (see $FIN_LOG)" >&2
      SYNC_OK=0
    elif [ -f "$FIN_DB" ] && [ -f "$FIN_CHART_REF" ] && {
      [ -n "${FORCE_FINANCE_DASHBOARD:-}" ] || [ "$FIN_DB" -nt "$FIN_CHART_REF" ]
    }; then
      # FIN_DB_NEWER выше — до pull; после scp БД часто новее PNG, а build=0 — графики не обновлялись весь день
      echo "$(sh_msg scripts.obsidian_sync.finance_db_rebuild)" >&2
      if (cd "$FINANCE_BOT" && ./scripts/run_finance_dashboard.sh >> "$FIN_LOG" 2>&1); then
        echo "$NOW_ISO" > "$SYNC_DIR/finance_dashboard_last_ok.txt"
      else
        echo "⚠️ finance dashboard rebuild after pull failed (see $FIN_LOG)" >&2
        SYNC_OK=0
      fi
    fi
  fi
fi
unset _FIN_BUILD FIN_DB_NEWER
}
