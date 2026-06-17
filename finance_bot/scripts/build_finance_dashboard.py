#!/usr/bin/env python3
"""
Build finance dashboard markdown from finance.db.

Run:
  python scripts/build_finance_dashboard.py
  python scripts/build_finance_dashboard.py --vault /path/to/vault
"""

import argparse
import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterable, List, Optional

from shared.bootstrap import setup_bot

setup_bot("finance_bot")
from bot.broker_portfolio import BROKER_PORTFOLIO_ACCOUNT_TYPE, is_broker_portfolio_account  # noqa: E402
from bot.config_loader import get_badge_config, is_badge_enabled  # noqa: E402
from bot.services.dashboard import (
    acc_balance,
    build_badge_section,
    ensure_account_balance_snapshots_table,
    external_rub_non_portfolio_total,
    fmt_num,
    load_data,
    parse_datetime,
    pie_with_pct,
    plot_lines_png,
    plot_stacked_bar_categories_png,
    safe_comment,
)
from bot.dashboard_templates import dtpl, dtpl_raw  # noqa: E402
from bot.vault_paths import VaultPaths  # noqa: E402
from shared.domain_messages import dmsg  # noqa: E402
from shared.finance_classification import misc_category_label  # noqa: E402
from shared.charts.mermaid import mermaid_pie, mermaid_xychart_lines
from shared.constants import finance_dashboard_start_date  # noqa: E402


def find_vault_and_db(args) -> tuple[Path, Path, Path]:
    """Return (vault, db_path, out_path)."""
    if args.vault:
        vault = Path(args.vault).resolve()
    else:
        script_dir = Path(__file__).resolve().parent
        vault = script_dir.parent.parent.parent.parent
    vp = VaultPaths(vault)
    return vault, args.db or vp.finance_db(), args.out or vp.finance_dashboard_md()


def main() -> None:
    parser = argparse.ArgumentParser(description="Finance dashboard from finance.db")
    parser.add_argument("--vault", type=Path, default=None, help="Vault root")
    parser.add_argument("--db", type=Path, default=None, help="Path to finance.db")
    parser.add_argument("--out", type=Path, default=None, help="Output markdown file")
    parser.add_argument("--user-id", type=int, default=1)
    args = parser.parse_args()

    vault, db_path, out_path = find_vault_and_db(args)
    vp = VaultPaths(vault)
    charts_dir = vp.finance_charts_dir()
    vault_root = vault.resolve()

    def wikilink_png(png_path: Path) -> str:
        rel = png_path.resolve().relative_to(vault_root)
        return f"![[{rel.as_posix()}]]"

    log_file = Path(__file__).resolve().parent.parent / "logs" / "build_finance_dashboard.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_dashboard(f"vault={vault} db_path={db_path} exists={db_path.exists()}", log_file)

    if not db_path.exists():
        rel_db = db_path.relative_to(vault) if vault in db_path.parents else db_path
        body = dtpl("errors", "db_not_found", db_path=rel_db)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
        print(dtpl("errors", "db_not_found_log", out_path=out_path))
        return

    db_mtime = datetime.fromtimestamp(db_path.stat().st_mtime)
    accounts, transactions, planned = load_data(db_path, args.user_id)
    print(dtpl("logs", "loaded", accounts=len(accounts), transactions=len(transactions), planned=len(planned)))

    conn = sqlite3.connect(db_path)
    ensure_account_balance_snapshots_table(conn)
    cur = conn.cursor()

    # Broker balance snapshots by day (one row per sync)
    broker_snapshots: dict[int, list[tuple[datetime.date, float]]] = defaultdict(list)
    try:
        cur.execute(
            """SELECT s.account_id, s.snapshot_date, s.balance
               FROM account_balance_snapshots s
               JOIN accounts a ON a.id = s.account_id
               WHERE a.user_id = ? AND a.type = ?""",
            (args.user_id, BROKER_PORTFOLIO_ACCOUNT_TYPE),
        )
        for row in cur.fetchall():
            aid, sd, bal = row[0], row[1], float(row[2])
            d = sd if isinstance(sd, date) else datetime.strptime(str(sd)[:10], "%Y-%m-%d").date()
            broker_snapshots[aid].append((d, bal))
        for aid in broker_snapshots:
            broker_snapshots[aid].sort(key=lambda x: x[0])
    except sqlite3.OperationalError:
        pass  # table may not exist in old DB

    # Current balances
    acc_by_id = {a["id"]: a for a in accounts}
    balances_now = {}
    for a in accounts:
        balances_now[a["id"]] = acc_balance(cur, a["id"], bool(a["is_external_balance"]), a["external_balance"])

    _badge_acc_name = (
        str(get_badge_config().get("account_name", "Meal Badge")) if is_badge_enabled() else ""
    )

    def _skip_badge_account(aid: int) -> bool:
        if not _badge_acc_name:
            return False
        return acc_by_id.get(aid, {}).get("name") == _badge_acc_name

    total_rub = sum(
        float(b) for aid, b in balances_now.items()
        if acc_by_id[aid]["currency"] in ("RUB", "RUR") and not _skip_badge_account(aid)
    )
    total_usd = sum(
        float(b) for aid, b in balances_now.items()
        if acc_by_id[aid]["currency"] == "USD"
    )

    # Dashboard sections (assembled at end)
    part_summary = []
    part_planned = []
    part_structure = []
    part_exp_pies = []
    part_moves = []
    part_day_flow = []
    part_day_regular = []
    part_day_oneoff = []
    part_oneoff_list = []
    part_monthly = []
    part_quarterly = []
    part_exp_by_account = []
    part_balances = []
    part_top_exp = []
    part_total_balance = []
    part_badge = []

    # Summary
    part_summary.extend([
        dtpl("sections", "summary", "heading"),
        "",
        dtpl("sections", "summary", "db_updated", mtime=db_mtime.strftime("%Y-%m-%d %H:%M")),
    ])
    db_age_days = (datetime.now() - db_mtime).total_seconds() / 86400
    if db_age_days > 1:
        part_summary.append(
            dtpl("sections", "summary", "stale_data", mtime=db_mtime.strftime("%Y-%m-%d %H:%M"))
        )
    part_summary.extend([
        dtpl("sections", "summary", "total_rub", amount=fmt_num(total_rub, decimals=2)),
    ])
    if total_usd != 0:
        part_summary.append(dtpl("sections", "summary", "total_usd", amount=fmt_num(total_usd, decimals=2)))
    part_summary.extend(["", ""])

    # Planned expenses
    if planned:
        part_planned.extend([
            dtpl("sections", "planned", "heading"),
            "",
        ])
        for p in planned:
            due = p["due_date"][:10] if p.get("due_date") else dtpl("misc", "no_due_date")
            part_planned.append(dtpl("sections", "planned", "line", name=p["name"], amount=fmt_num(float(p["amount"]), decimals=0), currency=p["currency"], due=due))
        part_planned.extend([
            "",
            dtpl("sections", "planned", "hint"),
            "",
        ])

    # Balance structure (RUB)
    rub_accounts = [
        (acc_by_id[aid]["name"], float(b))
        for aid, b in balances_now.items()
        if acc_by_id[aid]["currency"] in ("RUB", "RUR") and float(b) > 0 and not _skip_badge_account(aid)
    ]
    rub_accounts.sort(key=lambda x: -x[1])
    if rub_accounts:
        pie_data = [(f"{n} — {fmt_num(v, decimals=0)}", v) for n, v in rub_accounts[:10]]
        part_structure.extend([
            dtpl("sections", "structure", "heading"),
            "",
            "```mermaid",
            mermaid_pie(pie_data, dtpl("sections", "structure", "pie_title")),
            "```",
            "",
        ])

    # Spending by category
    now = datetime.now()
    # Dashboard start date for daily charts
    _start = finance_dashboard_start_date()
    try:
        dashboard_start_date = datetime.strptime(_start.strip()[:10], "%Y-%m-%d").date()
    except Exception:
        dashboard_start_date = datetime(2026, 2, 15).date()
    # One-off expense threshold
    # Override: FIN_ONEOFF_THRESHOLD_RUB=50000 ...
    oneoff_threshold_rub = int(os.environ.get("FIN_ONEOFF_THRESHOLD_RUB", "30000"))
    # Categories excluded from spending/income analytics
    # Internal transfers excluded from spending
    # Override: FIN_EXCLUDE_FROM_SPENDING_CATEGORIES
    exclude_cats_raw = os.environ.get("FIN_EXCLUDE_FROM_SPENDING_CATEGORIES", "")
    if not exclude_cats_raw.strip():
        from shared.finance_classification import exclude_spending_categories as _excl

        exclude_spending_categories = set(_excl())
    else:
        exclude_spending_categories = {c.strip() for c in exclude_cats_raw.split(",") if c.strip()}
    badge_category = (
        str(get_badge_config().get('category') or '') if is_badge_enabled() else None
    )

    def _is_excluded_category(txn: dict) -> bool:
        cat = (txn.get("category") or "").strip()
        return bool(cat) and cat in exclude_spending_categories

    def _is_badge_expense(txn: dict) -> bool:
        return bool(badge_category) and (txn.get("category") or "") == badge_category

    moves_out_month_total = Decimal(0)
    moves_in_month_total = Decimal(0)
    moves_recent = []  # (direction, account_name, category, amount, date_str)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    exp_this_month = defaultdict(Decimal)
    exp_all = defaultdict(Decimal)
    exp_this_month_regular = defaultdict(Decimal)
    for t in transactions:
        if t["type"] != "expense":
            continue
        if acc_by_id.get(t["account_id"], {}).get("currency") not in ("RUB", "RUR"):
            continue
        if _is_excluded_category(t):
            occ = parse_datetime(t["occurred_at"])
            if occ and occ >= month_start:
                amt = Decimal(str(t["amount"]))
                moves_out_month_total += amt
            date_str = t["occurred_at"][:10] if len(t["occurred_at"]) >= 10 else t["occurred_at"]
            moves_recent.append(("→", t.get("account_name") or dtpl("misc", "unknown_account"), t.get("category"), float(amt), date_str, t.get("description") or ""))
            continue
        cat = t["category"] or misc_category_label()
        if _is_badge_expense(t):
            continue
        amt = Decimal(str(t["amount"]))
        exp_all[cat] += amt
        occ = parse_datetime(t["occurred_at"])
        if occ and occ >= month_start:
            exp_this_month[cat] += amt
            if float(amt) < oneoff_threshold_rub:
                exp_this_month_regular[cat] += amt

    if exp_this_month:
        pie_data = pie_with_pct(exp_this_month, limit=10)
        part_exp_pies.extend([
            dtpl("sections", "expenses", "month_heading"),
            "",
            "```mermaid",
            mermaid_pie(pie_data, dtpl("sections", "expenses", "month_pie_title", month=now.strftime("%B %Y"))),
            "```",
            "",
        ])
        if exp_this_month_regular and exp_this_month_regular != exp_this_month:
            pie_data = pie_with_pct(exp_this_month_regular, limit=10)
            part_exp_pies.extend([
                dtpl("sections", "expenses", "regular_heading"),
                "",
                "```mermaid",
                mermaid_pie(pie_data, dtpl("sections", "expenses", "regular_pie_title", month=now.strftime("%B %Y"), threshold=oneoff_threshold_rub)),
                "```",
                "",
            ])
    elif exp_all:
        pie_data = [(k, float(v)) for k, v in sorted(exp_all.items(), key=lambda x: -x[1])[:10]]
        part_exp_pies.extend([
            dtpl("sections", "expenses", "all_heading"),
            "",
            "```mermaid",
            mermaid_pie(pie_data, dtpl("sections", "expenses", "all_pie_title")),
            "```",
            "",
        ])
    else:
        part_exp_pies.extend([
            dtpl("sections", "expenses", "empty_heading"),
            "",
            dtpl("sections", "expenses", "empty_hint"),
            "",
        ])

    # Internal moves section
    if exclude_spending_categories:
        for t in transactions:
            if t["type"] != "income":
                continue
            if acc_by_id.get(t["account_id"], {}).get("currency") not in ("RUB", "RUR"):
                continue
            if not _is_excluded_category(t):
                continue
            occ = parse_datetime(t["occurred_at"])
            if not occ or occ < month_start:
                continue
            amt = Decimal(str(t["amount"]))
            moves_in_month_total += amt
            date_str = t["occurred_at"][:10] if len(t["occurred_at"]) >= 10 else t["occurred_at"]
            moves_recent.append(("←", t.get("account_name") or dtpl("misc", "unknown_account"), t.get("category"), float(amt), date_str, t.get("description") or ""))

        if moves_out_month_total or moves_in_month_total:
            cats_list = ", ".join(sorted(exclude_spending_categories))
            part_moves.extend([
                dtpl("sections", "moves", "heading"),
                "",
                dtpl("sections", "moves", "excluded_cats", cats=cats_list),
                "",
                dtpl("sections", "moves", "out_month", amount=fmt_num(float(moves_out_month_total), decimals=0)),
                dtpl("sections", "moves", "in_month", amount=fmt_num(float(moves_in_month_total), decimals=0)),
            ])
            net = moves_in_month_total - moves_out_month_total
            part_moves.extend([
                dtpl("sections", "moves", "net", amount=fmt_num(float(net), decimals=0)),
                "",
                dtpl("sections", "moves", "recent_header"),
                "",
                dtpl("sections", "moves", "table_header"),
                dtpl("sections", "moves", "table_sep"),
            ])
            moves_recent.sort(key=lambda x: x[4], reverse=True)
            for direction, acc, cat, amt, dt, desc in moves_recent[:12]:
                part_moves.append(f"| {direction} | {acc} | {cat or _dash()} | {fmt_num(float(amt), decimals=0)} | {dt} | {safe_comment(desc)} |")
            part_moves.append("")

    # Daily spending: regular vs one-off
    # One-off = expense >= threshold
    day_exp_regular = defaultdict(lambda: defaultdict(Decimal))
    day_exp_oneoff_total = defaultdict(Decimal)
    oneoff_txns = []  # (account_name, category, amount, date_str, description)
    for t in transactions:
        if t["type"] != "expense":
            continue
        occ = parse_datetime(t["occurred_at"])
        if not occ:
            continue
        if acc_by_id.get(t["account_id"], {}).get("currency") not in ("RUB", "RUR"):
            continue
        if _is_excluded_category(t):
            continue
        if _is_badge_expense(t):
            continue
        amt = Decimal(str(t["amount"]))
        cat = t["category"] or misc_category_label()
        if float(amt) >= oneoff_threshold_rub:
            day_exp_oneoff_total[occ.date()] += amt
            date_str = t["occurred_at"][:10] if len(t["occurred_at"]) >= 10 else t["occurred_at"]
            oneoff_txns.append((t.get("account_name") or dtpl("misc", "unknown_account"), cat, float(amt), date_str, t.get("description") or ""))
        else:
            day_exp_regular[occ.date()][cat] += amt

    def _series_floor(dates: Iterable[date], *, fallback: date) -> date:
        dated = list(dates)
        return min(dated) if dated else fallback

    def _chart_window_int(key: str, env_key: str, legacy: int) -> int:
        cw = dtpl_raw("chart_windows")
        if isinstance(cw, dict) and key in cw and cw[key] is not None:
            try:
                return int(cw[key])
            except (TypeError, ValueError):
                pass
        env_raw = os.environ.get(env_key, "").strip()
        if env_raw:
            try:
                return int(env_raw)
            except ValueError:
                pass
        return legacy

    def _day_range(end: date, floor: date, window_days: int) -> list[date]:
        if window_days > 0:
            start = max(floor, end - timedelta(days=window_days - 1))
        else:
            start = floor
        if start > end:
            return [end]
        span = (end - start).days + 1
        return [start + timedelta(days=i) for i in range(span)]

    def _week_range(week_end: date, floor: date, max_weeks: int) -> list[date]:
        weeks: list[date] = []
        cur = week_end
        while cur >= floor:
            weeks.append(cur)
            if max_weeks > 0 and len(weeks) >= max_weeks:
                break
            cur = cur - timedelta(days=7)
        weeks.reverse()
        return weeks

    def _format_day_labels(days: list[date]) -> list[str]:
        if len(days) > 120:
            return [d.strftime("%m.%y") if d.day == 1 else "" for d in days]
        if len(days) > 60:
            return [d.strftime("%d.%m.%y") for d in days]
        return [d.strftime("%d.%m") for d in days]

    def _spending_axis_end(spending_dates: set[date]) -> date:
        """Spending chart axis end: last day with data (+ up to 3 days to today)."""
        if not spending_dates:
            return now.date()
        last = max(spending_dates)
        if last < now.date() and (now.date() - last).days <= 3:
            return now.date()
        return last

    spending_daily_window = _chart_window_int(
        "daily_spending_days", "FIN_SPENDING_DAILY_WINDOW_DAYS", 0
    )
    oneoff_daily_window = _chart_window_int("daily_oneoff_days", "FIN_ONEOFF_DAILY_WINDOW_DAYS", 0)
    flow_daily_window = _chart_window_int("daily_flow_days", "FIN_FLOW_DAILY_WINDOW_DAYS", 0)
    balance_daily_window = _chart_window_int("balance_days", "FIN_BALANCE_DAILY_WINDOW_DAYS", 0)
    weekly_flow_weeks = _chart_window_int("weekly_flow_weeks", "FIN_FLOW_WEEKLY_WINDOW_WEEKS", 0)
    weekly_spending_weeks = _chart_window_int(
        "weekly_spending_weeks", "FIN_SPENDING_WEEKLY_WINDOW_WEEKS", 0
    )
    last_spend_date = max(day_exp_regular.keys()) if day_exp_regular else None

    if day_exp_regular:
        regular_dates = set(day_exp_regular.keys())
        regular_end = _spending_axis_end(regular_dates)
        regular_floor = _series_floor(regular_dates, fallback=dashboard_start_date)
        days_sorted = _day_range(regular_end, regular_floor, spending_daily_window)
        all_cats = set()
        for d in day_exp_regular:
            all_cats.update(day_exp_regular[d].keys())
        cat_order = list(dtpl_raw('category_order') or [])
        sorted_cats = [c for c in cat_order if c in all_cats]
        sorted_cats += sorted(all_cats - set(sorted_cats))
        top8 = sorted_cats[:8]
        series = {cat: [float(day_exp_regular[d].get(cat, 0)) for d in days_sorted] for cat in top8}
        rest_vals = []
        for d in days_sorted:
            total_d = sum(day_exp_regular[d].values())
            in_top = sum(day_exp_regular[d].get(c, 0) for c in top8)
            rest_vals.append(float(total_d - in_top))
        if any(v > 0.5 for v in rest_vals):
            series[dtpl("misc", "rest_category")] = rest_vals
        day_totals_all = [float(sum(day_exp_regular[d].values())) for d in days_sorted]
        x_labels = _format_day_labels(days_sorted)
        part_day_regular.extend([
            dtpl("sections", "daily_regular", "heading"),
            "",
            dtpl("sections", "daily_regular", "threshold_note", threshold=oneoff_threshold_rub),
        ])
        if badge_category:
            part_day_regular.append(dtpl("sections", "daily_regular", "badge_note", category=badge_category))
        if last_spend_date:
            gap = (now.date() - last_spend_date).days
            part_day_regular.append(
                dtpl("sections", "daily_regular", "last_spend_gap", date=last_spend_date.strftime("%d.%m.%Y"), gap=gap)
                if gap > 0
                else dtpl("sections", "daily_regular", "last_spend", date=last_spend_date.strftime("%d.%m.%Y"))
            )
        part_day_regular.extend(["", ""])
        out_png = charts_dir / dtpl("charts", "daily_categories_file")
        ok = plot_stacked_bar_categories_png(
            x_labels,
            series,
            title=dtpl("charts", "daily_categories_title"),
            y_label="RUB",
            out_path=out_png,
            totals_for_labels=day_totals_all,
        )
        if ok:
            part_day_regular.append(wikilink_png(out_png))
        else:
            part_day_regular.append(dtpl("sections", "daily_regular", "no_data"))
        part_day_regular.extend(["", ""])
    else:
        part_day_regular.extend([
            dtpl("sections", "daily_regular", "empty_heading"),
            "",
            dtpl("sections", "daily_regular", "empty_hint"),
            "",
        ])

    # One-off large expenses by day
    if day_exp_oneoff_total:
        oneoff_dates = set(day_exp_oneoff_total.keys())
        oneoff_end = _spending_axis_end(oneoff_dates)
        oneoff_floor = _series_floor(oneoff_dates, fallback=dashboard_start_date)
        days_sorted_oneoff = _day_range(oneoff_end, oneoff_floor, oneoff_daily_window)
        x_labels = _format_day_labels(days_sorted_oneoff)
        vals = [float(day_exp_oneoff_total.get(d, 0)) for d in days_sorted_oneoff]
        part_day_oneoff.extend([
            dtpl("sections", "daily_oneoff", "heading"),
            "",
            dtpl("sections", "daily_oneoff", "threshold_note", threshold=oneoff_threshold_rub),
            "",
        ])
        out_png = charts_dir / dtpl("charts", "oneoff_daily_file")
        ok = plot_lines_png(
            x_labels,
            {dtpl("charts", "oneoff_series"): vals},
            title=dtpl("charts", "oneoff_daily_title"),
            y_label="RUB",
            out_path=out_png,
        )
        if ok:
            part_day_oneoff.append(wikilink_png(out_png))
        else:
            part_day_oneoff.append(dtpl("sections", "daily_oneoff", "no_data"))
        part_day_oneoff.extend(["", ""])

    # Daily income vs expense
    day_flow = defaultdict(lambda: {"income": Decimal(0), "expense": Decimal(0)})
    for t in transactions:
        occ = parse_datetime(t["occurred_at"])
        if not occ:
            continue
        if acc_by_id.get(t["account_id"], {}).get("currency") not in ("RUB", "RUR"):
            continue
        if _is_excluded_category(t):
            continue
        if _is_badge_expense(t):
            continue
        dday = occ.date()
        amt = Decimal(str(t["amount"]))
        if t["type"] == "income":
            day_flow[dday]["income"] += amt
        elif t["type"] == "expense":
            day_flow[dday]["expense"] += amt

    if day_flow:
        flow_dates = set(day_flow.keys())
        flow_end_date = _spending_axis_end(flow_dates)
        flow_floor = _series_floor(flow_dates, fallback=dashboard_start_date)
        days_sorted_flow = _day_range(flow_end_date, flow_floor, flow_daily_window)
        inc_vals = [float(day_flow.get(d, {}).get("income", 0)) for d in days_sorted_flow]
        exp_vals = [float(day_flow.get(d, {}).get("expense", 0)) for d in days_sorted_flow]
        x_labels = _format_day_labels(days_sorted_flow)
        part_day_flow.extend([
            dtpl("sections", "daily_flow", "heading"),
            "",
        ])
        out_png = charts_dir / dtpl("charts", "flow_daily_file")
        ok = plot_lines_png(
            x_labels,
            {dtpl("charts", "income"): inc_vals, dtpl("charts", "expense"): exp_vals},
            title=dtpl("charts", "flow_daily_title"),
            y_label="RUB",
            out_path=out_png,
        )
        if ok:
            part_day_flow.append(wikilink_png(out_png))
        else:
            part_day_flow.append(dtpl("sections", "daily_flow", "no_data"))
        part_day_flow.extend(["", ""])

        # Weekly charts
        week_flow = defaultdict(lambda: defaultdict(Decimal))  # week_start_date -> {"income"/"expense" -> Decimal}
        last_occ_date = None
        for t in transactions:
            if acc_by_id.get(t["account_id"], {}).get("currency") not in ("RUB", "RUR"):
                continue
            if _is_excluded_category(t):
                continue
            occ = parse_datetime(t.get("occurred_at"))
            if not occ:
                continue
            dday = occ.date()
            if last_occ_date is None or dday > last_occ_date:
                last_occ_date = dday
            week_start = dday - timedelta(days=dday.weekday())  # Monday
            amt = Decimal(str(t["amount"]))
            if t["type"] == "income":
                week_flow[week_start]["income"] += amt
            elif t["type"] == "expense":
                week_flow[week_start]["expense"] += amt

        if week_flow:
            week_end = max(week_flow.keys())
            week_floor = min(week_flow.keys())
            weeks_sorted = _week_range(week_end, week_floor, weekly_flow_weeks)
            xw = [w.strftime("%d.%m") for w in weeks_sorted]
            inc_w = [float(week_flow.get(w, {}).get("income", 0)) for w in weeks_sorted]
            exp_w = [float(week_flow.get(w, {}).get("expense", 0)) for w in weeks_sorted]
            out_png = charts_dir / dtpl("charts", "flow_weekly_file")
            ok = plot_lines_png(
                xw,
                {dtpl("charts", "income"): inc_w, dtpl("charts", "expense"): exp_w},
                title=dtpl("charts", "flow_weekly_title"),
                y_label="RUB",
                out_path=out_png,
            )
            if ok:
                part_day_flow.extend([
                    dtpl("sections", "daily_flow", "weekly_heading"),
                    "",
                    wikilink_png(out_png),
                    "",
                ])

        # Weekly spending by category
        week_exp_regular = defaultdict(lambda: defaultdict(Decimal))  # week_start -> cat -> amt
        for t in transactions:
            if t["type"] != "expense":
                continue
            if acc_by_id.get(t["account_id"], {}).get("currency") not in ("RUB", "RUR"):
                continue
            if _is_excluded_category(t):
                continue
            if _is_badge_expense(t):
                continue
            occ = parse_datetime(t.get("occurred_at"))
            if not occ:
                continue
            amt = Decimal(str(t["amount"]))
            if float(amt) >= oneoff_threshold_rub:
                continue
            cat = t["category"] or misc_category_label()
            dday = occ.date()
            week_start = dday - timedelta(days=dday.weekday())
            week_exp_regular[week_start][cat] += amt

        if week_exp_regular:
            week_end = max(week_exp_regular.keys())
            week_floor = min(week_exp_regular.keys())
            weeks_sorted = _week_range(week_end, week_floor, weekly_spending_weeks)

            # top categories by spend
            total_by_cat = defaultdict(Decimal)
            for w in weeks_sorted:
                for cat, v in week_exp_regular.get(w, {}).items():
                    total_by_cat[cat] += v
            top_cats = [c for c, _ in sorted(total_by_cat.items(), key=lambda x: -x[1])[:8]]
            series = {cat: [float(week_exp_regular.get(w, {}).get(cat, 0)) for w in weeks_sorted] for cat in top_cats}
            rest_w = []
            for w in weeks_sorted:
                total_w = sum(week_exp_regular.get(w, {}).values())
                in_top = sum(week_exp_regular.get(w, {}).get(c, 0) for c in top_cats)
                rest_w.append(float(total_w - in_top))
            if any(v > 0.5 for v in rest_w):
                series[dtpl("misc", "rest_category")] = rest_w
            week_totals_labels = [float(sum(week_exp_regular.get(w, {}).values())) for w in weeks_sorted]
            xw = [w.strftime("%d.%m") for w in weeks_sorted]
            out_png = charts_dir / dtpl("charts", "exp_weekly_file")
            ok = plot_stacked_bar_categories_png(
                xw,
                series,
                title=dtpl("charts", "exp_weekly_title"),
                y_label="RUB",
                out_path=out_png,
                totals_for_labels=week_totals_labels,
            )
            if ok:
                part_day_flow.extend([
                    dtpl("sections", "daily_flow", "weekly_exp_heading"),
                    "",
                    dtpl("sections", "daily_regular", "threshold_note", threshold=oneoff_threshold_rub),
                    "",
                    wikilink_png(out_png),
                    "",
                ])
    else:
        part_day_flow.extend([
            dtpl("sections", "daily_flow", "empty_heading"),
            "",
            dtpl("sections", "daily_flow", "empty_hint"),
            "",
        ])

    # Total balance over time
    balance_data_dates: set[date] = set()
    for t in transactions:
        if acc_by_id.get(t["account_id"], {}).get("currency") not in ("RUB", "RUR"):
            continue
        occ = parse_datetime(t.get("occurred_at"))
        if occ:
            balance_data_dates.add(occ.date())
    for snapshots in broker_snapshots.values():
        for snap_date, _ in snapshots:
            balance_data_dates.add(snap_date)
    balance_floor = _series_floor(balance_data_dates, fallback=dashboard_start_date)
    balance_chart_end = max(
        _spending_axis_end(balance_data_dates) if balance_data_dates else now.date(),
        now.date(),
    )
    days_total = _day_range(balance_chart_end, balance_floor, balance_daily_window)
    broker_rub_account_ids = [
        aid
        for aid, a in acc_by_id.items()
        if a.get("currency") in ("RUB", "RUR")
        and is_broker_portfolio_account(a.get("type"), bool(a.get("is_external_balance")))
    ]

    def _broker_balance_at(aid: int, d: date) -> float:
        """Broker balance at date d from latest snapshot on or before d."""
        lst = broker_snapshots.get(aid, [])
        cand = [(sd, b) for sd, b in lst if sd <= d]
        if cand:
            return cand[-1][1]
        if lst and d < lst[0][0]:
            return float(lst[0][1])
        if not lst:
            return float(balances_now.get(aid, 0))
        if d >= now.date():
            return float(balances_now.get(aid, 0))
        return 0.0

    account_daily_delta = defaultdict(lambda: defaultdict(Decimal))
    for t in transactions:
        acc_id = t["account_id"]
        a = acc_by_id.get(acc_id, {})
        if a.get("currency") not in ("RUB", "RUR"):
            continue
        occ = parse_datetime(t.get("occurred_at"))
        if not occ:
            continue
        d = occ.date()
        amt = Decimal(str(t["amount"]))
        if t["type"] == "income":
            account_daily_delta[acc_id][d] += amt
        elif t["type"] == "expense":
            account_daily_delta[acc_id][d] -= amt
    run_by_account = {}
    for a in accounts:
        if a.get("currency") not in ("RUB", "RUR"):
            continue
        if acc_by_id[a["id"]].get("is_external_balance"):
            continue
        run_by_account[a["id"]] = Decimal(str(a.get("external_balance") or 0))
    plateau_external_rub = external_rub_non_portfolio_total(balances_now, acc_by_id)
    from shared.capabilities.finance_gates import broker_sync_enabled
    from shared.capabilities.finance_ui import domestic_cards_enabled

    show_cards = domestic_cards_enabled()
    show_broker = broker_sync_enabled()
    cards_by_day: list[float] = []
    broker_by_day: list[float] = []
    total_by_day: list[float] = []
    card_rub_account_ids = list(run_by_account.keys()) if show_cards else []
    last_chart_day = days_total[-1] if days_total else None
    for d in days_total:
        for aid, run in list(run_by_account.items()):
            run_by_account[aid] = run + account_daily_delta[aid].get(d, Decimal(0))
        if last_chart_day is not None and d == last_chart_day:
            cards_d = sum(float(balances_now[aid]) for aid in card_rub_account_ids) if show_cards else 0.0
            broker_d = (
                sum(float(balances_now[aid]) for aid in broker_rub_account_ids) if show_broker else 0.0
            )
            day_total = float(total_rub)
        else:
            broker_d = (
                sum(_broker_balance_at(aid, d) for aid in broker_rub_account_ids) if show_broker else 0.0
            )
            cards_d = sum(float(run_by_account[aid]) for aid in card_rub_account_ids) if show_cards else 0.0
            day_total = plateau_external_rub + broker_d + cards_d
        cards_by_day.append(cards_d)
        broker_by_day.append(broker_d)
        total_by_day.append(day_total)
    part_total_balance.extend([
        dtpl("sections", "balance", "heading"),
        "",
        dtpl("sections", "balance", "description"),
        "",
    ])
    out_png = charts_dir / dtpl("charts", "balance_daily_file")
    balance_series = {dtpl("charts", "total_rub"): total_by_day}
    if show_cards:
        balance_series[dtpl("charts", "cards_rub")] = cards_by_day
    if show_broker:
        balance_series[dtpl("charts", "broker_rub")] = broker_by_day
    ok = plot_lines_png(
        _format_day_labels(days_total),
        balance_series,
        title=dtpl("charts", "balance_daily_title"),
        y_label="RUB",
        out_path=out_png,
    )
    if ok:
        part_total_balance.append(wikilink_png(out_png))
        if total_by_day and days_total:
            ld = days_total[-1]
            fv = days_total[0]
            lv = total_by_day[-1]
            cv = cards_by_day[-1]
            bv = broker_by_day[-1]
            part_total_balance.append(
                dtpl(
                    "sections", "balance", "axis_note",
                    from_date=fv.strftime("%d.%m.%Y"),
                    to_date=ld.strftime("%d.%m.%Y"),
                    days=len(days_total),
                    total=fmt_num(float(lv), decimals=0),
                    cards=fmt_num(float(cv), decimals=0),
                    broker=fmt_num(float(bv), decimals=0),
                    built_at=now.strftime("%Y-%m-%d %H:%M"),
                )
            )
    else:
        part_total_balance.append(dtpl("sections", "balance", "no_data"))
    part_total_balance.extend(["", ""])

    # Spending by account
    exp_by_account = defaultdict(Decimal)
    for t in transactions:
        if t["type"] == "expense" and not _is_excluded_category(t) and not _is_badge_expense(t):
            exp_by_account[t.get("account_name") or dtpl("misc", "unknown_account")] += Decimal(str(t["amount"]))
    if exp_by_account:
        by_acc_data = [(k, float(v)) for k, v in sorted(exp_by_account.items(), key=lambda x: -x[1])[:8]]
        part_exp_by_account.extend([
            dtpl("sections", "by_account", "heading"),
            "",
            "```mermaid",
            mermaid_pie(by_acc_data, dtpl("sections", "by_account", "pie_title")),
            "```",
            "",
        ])

    # Balances table
    part_balances.extend([
        dtpl("sections", "balances_table", "heading"),
        "",
        dtpl("sections", "balances_table", "header"),
        dtpl("sections", "balances_table", "sep"),
    ])
    for a in sorted(accounts, key=lambda x: (-float(balances_now.get(x["id"], 0)), x["name"])):
        bal = balances_now.get(a["id"], 0)
        part_balances.append(f"| {a['name']} | {fmt_num(float(bal), decimals=2)} | {a['currency']} |")
    part_balances.append("")
    part_balances.append("")

    # Top expenses last 30 days
    cutoff = now - timedelta(days=30)
    recent_exp = []
    for t in transactions:
        if t["type"] != "expense":
            continue
        if _is_excluded_category(t):
            continue
        if _is_badge_expense(t):
            continue
        occ = parse_datetime(t["occurred_at"])
        if not occ or occ < cutoff:
            continue
        if occ.date() < dashboard_start_date:
            continue
        date_str = t["occurred_at"][:10] if len(t["occurred_at"]) >= 10 else t["occurred_at"]
        recent_exp.append((t.get("account_name") or dtpl("misc", "unknown_account"), t.get("category"), float(t["amount"]), date_str, t.get("description") or ""))
    recent_exp.sort(key=lambda x: -x[2])
    if recent_exp[:15]:
        part_top_exp.extend([
            dtpl("sections", "top_expenses", "heading"),
            "",
            dtpl("sections", "top_expenses", "header"),
            dtpl("sections", "top_expenses", "sep"),
        ])
        for acc, cat, amt, occ, desc in recent_exp[:15]:
            dt = occ[:10] if isinstance(occ, str) else str(occ)[:10]
            part_top_exp.append(f"| {acc} | {cat or dtpl('misc', 'dash')} | {fmt_num(float(amt), decimals=2)} | {dt} | {safe_comment(desc)} |")
        part_top_exp.extend(["", ""])

    # Monthly income vs expense
    monthly = defaultdict(lambda: {"income": Decimal(0), "expense": Decimal(0)})
    for t in transactions:
        occ = parse_datetime(t["occurred_at"])
        if not occ:
            continue
        if t.get("type") not in ("income", "expense"):
            continue
        if _is_excluded_category(t):
            continue
        if _is_badge_expense(t):
            continue
        key = occ.strftime("%Y-%m")
        amt = Decimal(str(t["amount"]))
        monthly[key][t["type"]] += amt

    # Quarterly dynamics
    quarterly = defaultdict(lambda: {"income": Decimal(0), "expense": Decimal(0)})
    for t in transactions:
        occ = parse_datetime(t["occurred_at"])
        if not occ:
            continue
        if t.get("type") not in ("income", "expense"):
            continue
        if _is_excluded_category(t):
            continue
        if _is_badge_expense(t):
            continue
        q = (occ.month - 1) // 3 + 1
        key = f"{occ.year}Q{q}"
        amt = Decimal(str(t["amount"]))
        quarterly[key][t["type"]] += amt
    if quarterly:
        q_keys = sorted(quarterly.keys())[-6:]
        inc_q = [float(quarterly[k]["income"]) for k in q_keys]
        exp_q = [float(quarterly[k]["expense"]) for k in q_keys]
        part_quarterly.extend([
            dtpl("sections", "quarterly", "heading"),
            "",
            dtpl("sections", "quarterly", "hint"),
            "",
        ])
        out_png = charts_dir / dtpl("charts", "quarterly_file")
        ok = plot_lines_png(
            q_keys,
            {dtpl("charts", "income"): inc_q, dtpl("charts", "expense"): exp_q},
            title=dtpl("charts", "quarterly_title"),
            y_label="RUB",
            out_path=out_png,
        )
        if ok:
            part_quarterly.append(wikilink_png(out_png))
        else:
            part_quarterly.append(dtpl("sections", "quarterly", "no_data"))
        part_quarterly.extend(["", ""])

    # One-off list
    if "oneoff_txns" in locals() and oneoff_txns:
        oneoff_txns.sort(key=lambda x: -x[2])
        part_oneoff_list.extend([
            dtpl("sections", "oneoff_list", "heading"),
            "",
            dtpl("sections", "oneoff_list", "hint", threshold=oneoff_threshold_rub),
            "",
            dtpl("sections", "top_expenses", "header"),
            dtpl("sections", "top_expenses", "sep"),
        ])
        for acc, cat, amt, dt, desc in oneoff_txns[:10]:
            part_oneoff_list.append(f"| {acc} | {cat or dtpl('misc', 'dash')} | {fmt_num(float(amt), decimals=0)} | {dt} | {safe_comment(desc)} |")
        part_oneoff_list.extend(["", ""])

    if monthly:
        months = sorted(monthly.keys())[-6:]
        inc_vals = [float(monthly[m]["income"]) for m in months]
        exp_vals = [float(monthly[m]["expense"]) for m in months]
        x_labels = [m.replace("-", ".") for m in months]
        part_monthly.extend([
            dtpl("sections", "monthly", "heading"),
            "",
        ])
        out_png = charts_dir / dtpl("charts", "monthly_file")
        ok = plot_lines_png(
            x_labels,
            {dtpl("charts", "income"): inc_vals, dtpl("charts", "expense"): exp_vals},
            title=dtpl("charts", "monthly_title"),
            y_label="RUB",
            out_path=out_png,
        )
        if ok:
            part_monthly.append(wikilink_png(out_png))
        else:
            part_monthly.append(dtpl("sections", "monthly", "no_data"))
        part_monthly.extend(["", ""])
    else:
        part_monthly.extend([
            dtpl("sections", "monthly", "heading"),
            "",
            dtpl("sections", "monthly", "empty_hint"),
            "",
        ])

    part_badge.extend(build_badge_section(conn, args.user_id, charts_dir, now, chart_wikilink=wikilink_png))

    conn.close()

    # Assemble dashboard sections
    footer = [
        "---",
        "",
        dtpl("footer", "refresh").strip(),
        "",
    ]
    sections = (
        part_summary
        + part_planned
        + part_structure
        + part_exp_pies
        + part_badge
        + part_moves
        + part_day_flow
        + part_total_balance
        + part_day_regular
        + part_day_oneoff
        + part_oneoff_list
        + part_monthly
        + part_quarterly
        + part_exp_by_account
        + part_balances
        + part_top_exp
        + footer
    )

    body = dtpl("title") + "\n\n" + "\n".join(sections)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    print(dtpl("logs", "written", out_path=out_path))



def log_dashboard(msg: str, log_path: Optional[Path] = None) -> None:
    """Print and optionally append to log file (launchd/cron)."""
    print(msg)
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] {msg}\n")
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    script_dir = Path(__file__).resolve().parent
    log_file = script_dir.parent / "logs" / "build_finance_dashboard.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        main()
    except Exception as e:
        log_dashboard(f"ERROR: {e}", log_file)
        import traceback
        traceback.print_exc()
        sys.exit(1)
