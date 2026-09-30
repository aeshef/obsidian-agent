#!/usr/bin/env bash
# Build full life-OS chart PNGs / dashboard hubs into the English demo vault only.
# Does NOT touch Agent/.env or your personal vault.
#
# Important: does NOT source .env (your AGENT_LOCALE=ru / BASE_CURRENCY=RUB would poison EN/USD output).
#
#   ./scripts/build_demo_charts.sh
#   ./scripts/build_demo_charts.sh "/abs/path/to/demo-vault-en"
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEMO="${1:-${ROOT}/../demo-vault-en}"
DEMO="$(cd "$DEMO" && pwd)"

case "$DEMO" in
  */demo-vault-en|*/demo-vault-en/) ;;
  *)
    echo "Refusing: path must be a dedicated demo-vault-en (got: $DEMO)" >&2
    exit 2
    ;;
esac

# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"
PY="$(common_resolve_python "$ROOT/finance_bot")"

# Force EN + USD demo topology — never source .env here (personal RUB/ru would poison output).
export AGENT_LOCALE=en
export AGENT_EN_STRICT=1
export BASE_CURRENCY=USD
export FIN_ONEOFF_THRESHOLD=500
export FIN_INVESTMENT_EXPENSE_CATEGORIES=Savings
export OA_CALENDAR_CLASSIFY=0
export FINANCE_CONFIG_DIR="$ROOT/scripts/demo/finance_config"
export VAULT_PATH="$DEMO"
export LOCAL_VAULT="$DEMO"
export FINANCE_DB_PATH="$DEMO/300_Dashboards/Data/finance.db"
export AGENT_ROOT="$ROOT"
export PYTHONPATH="$ROOT:$ROOT/finance_bot:$ROOT/planning_bot"
export MPLCONFIGDIR="${TMPDIR:-/tmp}/oa-demo-mpl"
mkdir -p "$MPLCONFIGDIR"

# EN chart destinations (match vault_paths.en.yaml.example)
mkdir -p \
  "$DEMO/300_Dashboards/Charts/Planning" \
  "$DEMO/300_Dashboards/Charts/Health" \
  "$DEMO/300_Dashboards/Charts/Finance" \
  "$DEMO/300_Dashboards/Charts/Cross" \
  "$DEMO/300_Dashboards/Charts/Analytics" \
  "$DEMO/300_Dashboards/Charts/System" \
  "$DEMO/300_Dashboards/Data/Actions/IPhone" \
  "$DEMO/300_Dashboards/Data/Actions/Mac" \
  "$DEMO/300_Dashboards/Logs" \
  "$DEMO/400_Routines/Charts/Routines" \
  "$DEMO/400_Routines/Charts/Signals"

# Drop accidental RU scaffold from a prior poisoned run
if [[ -d "$DEMO/300_Дашборды" ]]; then
  echo "Removing accidental RU folder 300_Дашборды from demo vault"
  rm -rf "$DEMO/300_Дашборды"
fi

echo "Building full life-OS demo charts → $DEMO (AGENT_LOCALE=$AGENT_LOCALE BASE_CURRENCY=$BASE_CURRENCY)"

run() {
  echo "+ $*"
  AGENT_LOCALE=en AGENT_EN_STRICT=1 BASE_CURRENCY=USD FIN_ONEOFF_THRESHOLD=500 \
    FIN_INVESTMENT_EXPENSE_CATEGORIES=Savings \
    OA_CALENDAR_CLASSIFY=0 FINANCE_CONFIG_DIR="$FINANCE_CONFIG_DIR" \
    VAULT_PATH="$DEMO" LOCAL_VAULT="$DEMO" FINANCE_DB_PATH="$FINANCE_DB_PATH" \
    PYTHONPATH="$PYTHONPATH" MPLCONFIGDIR="$MPLCONFIGDIR" AGENT_ROOT="$ROOT" \
    "$PY" "$@" || echo "  (skip/fail non-fatal: $*)" >&2
}

# Hubs first (Main / Progress). Routines stats are EN stubs from seed — skip RU templates.
run "$ROOT/scripts/scaffold_vault_dashboards.py" --vault "$DEMO" --locale en --force
# Do NOT force routines scaffold (templates are still Russian).
# Planning
run "$ROOT/planning_bot/scripts/build_open_tasks_snapshot.py" --vault "$DEMO"
run "$ROOT/planning_bot/scripts/build_kanban_flow_dashboard.py" --vault "$DEMO"
run "$ROOT/planning_bot/scripts/build_goals_mapping_review.py" --vault "$DEMO" --json

# Calendar (Meetings hub + workload PNG)
run "$ROOT/planning_bot/tools/calendar_sync.py"

# Health + cross + analytics
run "$ROOT/planning_bot/scripts/build_cross_domain_analytics.py" --vault "$DEMO"
run "$ROOT/planning_bot/scripts/build_analytics_insights.py" --vault "$DEMO"
run "$ROOT/planning_bot/scripts/build_analytics_dashboard_hub.py" --vault "$DEMO"
run "$ROOT/planning_bot/scripts/build_health_dashboard_hub.py" --vault "$DEMO"

# Agent cost → System hub
TRACES="$DEMO/Agent/logs/agent_traces.jsonl"
if [[ -f "$TRACES" ]]; then
  run "$ROOT/scripts/build_agent_cost_dashboard.py" --path "$TRACES" --vault "$DEMO" --days 30
fi
run "$ROOT/planning_bot/scripts/build_system_dashboard_hub.py" --vault "$DEMO"

# Finance (USD templates via FINANCE_CONFIG_DIR)
rm -f "$DEMO/300_Dashboards/Charts/Finance/"*.png
run "$ROOT/finance_bot/scripts/build_finance_dashboard.py" --vault "$DEMO" --db "$FINANCE_DB_PATH"

echo "PNG count under EN Charts:"
find "$DEMO/300_Dashboards/Charts" -name '*.png' 2>/dev/null | tee /tmp/oa-demo-pngs.txt | wc -l
head -50 /tmp/oa-demo-pngs.txt
echo "Top-level demo vault:"
ls -1 "$DEMO"
echo "Done."
