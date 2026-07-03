#!/usr/bin/env bash
# Health-отчёт по маркерам .sync (шаг 7 obsidian_sync). Пишет в health.log и health_report.md.
#
#   ./scripts/check_sync_health.sh [VAULT_PATH] [SYNC_DIR]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$AGENT_ROOT/scripts/lib/common.sh"
# shellcheck source=scripts/lib/vault_paths_defaults.sh
source "$AGENT_ROOT/scripts/lib/vault_paths_defaults.sh"
vault_paths_load_from_agent "$AGENT_ROOT"

VAULT="${1:-${VAULT_PATH:-${LOCAL_VAULT:-$(common_resolve_vault "$AGENT_ROOT" 2>/dev/null || true)}}}"
if [ -z "$VAULT" ]; then
  echo "check_sync_health: VAULT_PATH is not configured" >&2
  exit 1
fi
SYNC_DIR="${2:-${SYNC_STATE_DIR:-$VAULT/.sync}}"
REPORT="$SYNC_DIR/health_report.md"
NOW="$(date '+%Y-%m-%d %H:%M:%S')"

_read() {
  local f="$1"
  if [ -f "$f" ]; then tr -d '\n' <"$f"; else echo "—"; fi
}

last_sync="$(_read "$SYNC_DIR/last_sync_ok.txt")"
last_fail="$(_read "$SYNC_DIR/last_sync_failed.txt")"
charts="$(_read "$SYNC_DIR/daily_charts_date.txt")"
_charts_stale=""
_ref="$VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_CHARTS}/${VAULT_FILE_CHART_DAILY_ACTIVITY}"
_log="$VAULT/${VAULT_FOLDER_DASHBOARDS}/${VAULT_DASH_LOGS}/📊 Логи_Действий_$(date +%Y-%m).md"
if [ -f "$_log" ] && [ -f "$_ref" ]; then
  _lm=$(stat -f '%m' "$_log" 2>/dev/null || echo 0)
  _pm=$(stat -f '%m' "$_ref" 2>/dev/null || echo 0)
  [ "$_lm" -gt "$_pm" ] && _charts_stale=" (лог новее PNG — нужен шаг 5)"
fi
unset _ref _log _lm _pm
finance="$(_read "$SYNC_DIR/finance_dashboard_last_ok.txt")"
mobile="$(_read "$SYNC_DIR/mobile_vault_last_ok.txt")"
maint="$(_read "$SYNC_DIR/daily_vault_write_maintenance_date.txt")"

mobile_stale=""
if [ "$mobile" != "—" ] && [ -n "$mobile" ]; then
  _mobile_epoch="$(date -j -f '%Y-%m-%dT%H:%M:%S' "${mobile%%.*}" '+%s' 2>/dev/null || echo 0)"
  _now_epoch="$(date '+%s')"
  if [ "$_mobile_epoch" -gt 0 ] && [ $((_now_epoch - _mobile_epoch)) -gt 43200 ]; then
    mobile_stale=" STALE"
  fi
elif [ -f "$AGENT_ROOT/config/agent/platform.yaml" ] || [ -n "${MOBILE_VAULT:-}" ]; then
  mobile_stale=" MISSING"
fi
unset _mobile_epoch _now_epoch

mac_ctx=""
_mac_dir=""
_mac_py=""
for _candidate in \
  "$AGENT_ROOT/planning_bot/.venv/bin/python" \
  "$(common_launchagent_python "$AGENT_ROOT/planning_bot" 2>/dev/null || true)"; do
  [ -n "$_candidate" ] && [ -x "$_candidate" ] && _mac_py="$_candidate" && break
done
if [ -n "$_mac_py" ]; then
  _mac_dir="$(
    VAULT_PATH="$VAULT" PYTHONPATH="$AGENT_ROOT" "$_mac_py" -c \
      "from planning_bot.core.config import CONTEXT_MAC_DIR; print(CONTEXT_MAC_DIR)" 2>/dev/null || true
  )"
fi
if [ -z "$_mac_dir" ] && [ -f "$AGENT_ROOT/config/vault_paths.yaml" ]; then
  _vd="$(_vault_yaml_field folders dashboards "$AGENT_ROOT/config/vault_paths.yaml")"
  _dd="$(_vault_yaml_field dashboards data "$AGENT_ROOT/config/vault_paths.yaml")"
  _am="$(_vault_yaml_field paths actions_mac "$AGENT_ROOT/config/vault_paths.yaml")"
  if [ -n "$_vd" ] && [ -n "$_dd" ] && [ -n "$_am" ]; then
    _mac_dir="$VAULT/$_vd/$_dd/$_am"
  fi
fi
if [ -z "$_mac_dir" ]; then
  _mac_dir="$VAULT/${VAULT_FOLDER_DASHBOARDS:?}/${VAULT_DASH_DATA:?}/${VAULT_PATH_ACTIONS_MAC:-Действия/Mac}"
fi
unset _mac_py _candidate _vd _dd _am
if [ -d "$_mac_dir" ]; then
  _mac_newest="$(
    find "$_mac_dir" -maxdepth 1 -name '*.txt' -type f -print0 2>/dev/null \
      | xargs -0 stat -f '%m' 2>/dev/null \
      | sort -rn \
      | head -1 \
      || true
  )"
  if [ -n "${_mac_newest:-}" ] && [ "$_mac_newest" -gt 0 ]; then
    _now_epoch="$(date '+%s')"
    _age=$((_now_epoch - _mac_newest))
    mac_ctx="$(date -r "$_mac_newest" '+%Y-%m-%d %H:%M')"
    if [ "$_age" -gt 7200 ]; then
      mac_ctx="$mac_ctx STALE"
    fi
  else
    mac_ctx="MISSING"
  fi
else
  mac_ctx="MISSING"
fi
unset _mac_dir _mac_newest _now_epoch _age

{
  echo "# Sync health — $NOW"
  echo ""
  echo "| Маркер | Значение |"
  echo "|--------|----------|"
  echo "| last_sync_ok | $last_sync |"
  echo "| last_sync_failed | $last_fail |"
  echo "| daily_charts | $charts$_charts_stale |"
  echo "| finance_dashboard | $finance |"
  echo "| mobile_vault | $mobile$mobile_stale |"
  echo "| mac_context | $mac_ctx |"
  echo "| vault_maintenance | $maint |"
} >"$REPORT" 2>/dev/null || true

line="[$NOW] sync=$last_sync fail=$last_fail charts=$charts finance=$finance mobile=$mobile$mobile_stale mac=$mac_ctx maint=$maint"
echo "$line" >>"$SYNC_DIR/health.log" 2>/dev/null || true

common_rotate_log "$SYNC_DIR/health.log" 3000 1200
