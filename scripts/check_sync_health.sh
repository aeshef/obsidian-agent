#!/usr/bin/env bash
# Health-отчёт по маркерам .sync (шаг 7 obsidian_sync). Пишет в health.log и health_report.md.
#
#   ./scripts/check_sync_health.sh [VAULT_PATH] [SYNC_DIR]
set -euo pipefail

VAULT="${1:-${VAULT_PATH:-${LOCAL_VAULT:-$HOME/Documents/Obsidian Vault}}}"
SYNC_DIR="${2:-${SYNC_STATE_DIR:-$VAULT/.sync}}"
REPORT="$SYNC_DIR/health_report.md"
NOW="$(date '+%Y-%m-%d %H:%M:%S')"

_read() {
  local f="$1"
  if [ -f "$f" ]; then tr -d '\n' <"$f"; else echo "—"; fi
}

last_sync="$(_read "$SYNC_DIR/last_sync_ok.txt")"
charts="$(_read "$SYNC_DIR/daily_charts_date.txt")"
finance="$(_read "$SYNC_DIR/finance_dashboard_last_ok.txt")"
mobile="$(_read "$SYNC_DIR/mobile_vault_last_ok.txt")"
maint="$(_read "$SYNC_DIR/daily_vault_write_maintenance_date.txt")"

{
  echo "# Sync health — $NOW"
  echo ""
  echo "| Маркер | Значение |"
  echo "|--------|----------|"
  echo "| last_sync_ok | $last_sync |"
  echo "| daily_charts | $charts |"
  echo "| finance_dashboard | $finance |"
  echo "| mobile_vault | $mobile |"
  echo "| vault_maintenance | $maint |"
} >"$REPORT" 2>/dev/null || true

line="[$NOW] sync=$last_sync charts=$charts finance=$finance mobile=$mobile maint=$maint"
echo "$line" >>"$SYNC_DIR/health.log" 2>/dev/null || true

# trim health.log (keep last ~300 lines)
if [ -f "$SYNC_DIR/health.log" ]; then
  tail -n 300 "$SYNC_DIR/health.log" >"$SYNC_DIR/health.log.tmp" 2>/dev/null \
    && mv "$SYNC_DIR/health.log.tmp" "$SYNC_DIR/health.log" 2>/dev/null || true
fi
