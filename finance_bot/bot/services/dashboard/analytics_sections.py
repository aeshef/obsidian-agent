"""Spending / balance / chart sections for finance dashboard."""
from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from shared.finance.currency import base_currency, is_base_currency
from bot.broker_portfolio import BROKER_PORTFOLIO_ACCOUNT_TYPE, is_broker_portfolio_account
from bot.services.dashboard.charts import plot_lines_png, plot_stacked_bar_categories_png
from bot.services.dashboard.data import (
    acc_balance,
    external_base_non_portfolio_total,
    parse_datetime,
)
from bot.services.dashboard.filters import (
    is_badge_expense,
    is_excluded_category,
    resolve_badge_category,
    resolve_exclude_spending_categories,
    skip_badge_account,
)
from bot.services.dashboard.format import fmt_num, pie_with_pct, safe_comment
from bot.services.dashboard.series import (
    accumulate_daily_flow,
    accumulate_daily_spending,
    accumulate_weekly_flow,
    accumulate_weekly_regular_spending,
    ordered_top_categories,
    stacked_category_series,
    top_cats_by_total,
)
from bot.services.dashboard.windows import (
    chart_window_int,
    day_range,
    format_day_labels,
    series_floor,
    spending_axis_end,
    week_range,
)
from bot.dashboard_templates import dtpl, dtpl_raw
from shared.charts.mermaid import mermaid_pie, mermaid_xychart_lines
from shared.constants import finance_dashboard_start_date
from shared.finance_classification import misc_category_label


def build_analytics_sections(
    *,
    now: datetime,
    accounts: list,
    transactions: list,
    planned: list,
    balances_now: dict,
    acc_by_id: dict,
    broker_snapshots: dict,
    conn: sqlite3.Connection,
    cur: sqlite3.Cursor,
    charts_dir: Path,
    vault_root: Path,
    badge_acc_name: str,
    args_user_id: int,
    total_rub: float,
) -> dict[str, list]:
    """Build analytics markdown parts (structure through quarterly)."""

    def wikilink_png(png_path: Path) -> str:
        rel = png_path.resolve().relative_to(vault_root)
        return f"![[{rel.as_posix()}]]"

    part_structure: list = []
    part_exp_pies: list = []
    part_moves: list = []
    part_day_flow: list = []
    part_day_regular: list = []
    part_day_oneoff: list = []
    part_oneoff_list: list = []
    part_monthly: list = []
    part_quarterly: list = []
    part_exp_by_account: list = []
    part_balances: list = []
    part_top_exp: list = []
    part_total_balance: list = []

    _badge_acc_name = badge_acc_name

    # Balance structure (base currency)
    rub_accounts = [
        (acc_by_id[aid]["name"], float(b))
        for aid, b in balances_now.items()
        if is_base_currency(acc_by_id[aid]["currency"])
        and float(b) > 0
        and not skip_badge_account(aid, acc_by_id, _badge_acc_name)
    ]
    rub_accounts.sort(key=lambda x: -x[1])
    if rub_accounts:
        _lbl_fmt = dtpl("sections", "structure", "pie_label")
        pie_data = [(_lbl_fmt.format(name=n, amount=fmt_num(v, decimals=0)), v) for n, v in rub_accounts[:10]]
        heading = dtpl("sections", "structure", "heading")
        structure_lines = [heading, ""] if heading.strip() else [""]
        part_structure.extend(
            structure_lines + ["```mermaid", mermaid_pie(pie_data, dtpl("sections", "structure", "pie_title")), "```", ""]
        )

    # Spending by category
    # Dashboard start date for daily charts
    _start = finance_dashboard_start_date()
    try:
        dashboard_start_date = datetime.strptime(_start.strip()[:10], "%Y-%m-%d").date()
    except Exception:
        dashboard_start_date = datetime(2026, 2, 15).date()
    # One-off expense threshold
    # Override: FIN_ONEOFF_THRESHOLD / legacy FIN_ONEOFF_THRESHOLD_RUB ...
    oneoff_threshold_rub = int(
        os.environ.get("FIN_ONEOFF_THRESHOLD")
        or os.environ.get("FIN_ONEOFF_THRESHOLD_RUB")
        or "500"
    )
    # Categories excluded from spending/income analytics
    # Internal transfers excluded from spending
    # Override: FIN_EXCLUDE_FROM_SPENDING_CATEGORIES
    exclude_spending_categories = resolve_exclude_spending_categories()
    badge_category = resolve_badge_category()

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
        if not is_base_currency(acc_by_id.get(t["account_id"], {}).get("currency")):
            continue
        if is_excluded_category(t, exclude_spending_categories):
            occ = parse_datetime(t["occurred_at"])
            if occ and occ >= month_start:
                amt = Decimal(str(t["amount"]))
                moves_out_month_total += amt
            date_str = t["occurred_at"][:10] if len(t["occurred_at"]) >= 10 else t["occurred_at"]
            moves_recent.append(("→", t.get("account_name") or dtpl("misc", "unknown_account"), t.get("category"), float(amt), date_str, t.get("description") or ""))
            continue
        cat = t["category"] or misc_category_label()
        if is_badge_expense(t, badge_category):
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
            if not is_base_currency(acc_by_id.get(t["account_id"], {}).get("currency")):
                continue
            if not is_excluded_category(t, exclude_spending_categories):
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
            net = moves_in_month_total - moves_out_month_total
            part_moves.extend([
                dtpl("sections", "moves", "excluded_cats", cats=cats_list),
                dtpl(
                    "sections",
                    "moves",
                    "summary_line",
                    out=fmt_num(float(moves_out_month_total), decimals=0),
                    inn=fmt_num(float(moves_in_month_total), decimals=0),
                    net=fmt_num(float(net), decimals=0),
                ),
                "",
            ])

    # Daily spending: regular vs one-off
    # One-off = expense >= threshold
    day_exp_regular, day_exp_oneoff_total, oneoff_txns = accumulate_daily_spending(
        transactions,
        acc_by_id=acc_by_id,
        exclude_categories=exclude_spending_categories,
        badge_category=badge_category,
        oneoff_threshold_rub=oneoff_threshold_rub,
        misc_label=misc_category_label(),
        parse_datetime=parse_datetime,
        unknown_account_label=dtpl("misc", "unknown_account"),
    )

    today = now.date()
    spending_daily_window = chart_window_int(
        "daily_spending_days", "FIN_SPENDING_DAILY_WINDOW_DAYS", 0
    )
    oneoff_daily_window = chart_window_int("daily_oneoff_days", "FIN_ONEOFF_DAILY_WINDOW_DAYS", 0)
    flow_daily_window = chart_window_int("daily_flow_days", "FIN_FLOW_DAILY_WINDOW_DAYS", 0)
    balance_daily_window = chart_window_int("balance_days", "FIN_BALANCE_DAILY_WINDOW_DAYS", 0)
    weekly_flow_weeks = chart_window_int("weekly_flow_weeks", "FIN_FLOW_WEEKLY_WINDOW_WEEKS", 0)
    weekly_spending_weeks = chart_window_int(
        "weekly_spending_weeks", "FIN_SPENDING_WEEKLY_WINDOW_WEEKS", 0
    )
    last_spend_date = max(day_exp_regular.keys()) if day_exp_regular else None

    if day_exp_regular:
        regular_dates = set(day_exp_regular.keys())
        regular_end = spending_axis_end(regular_dates, today=today)
        regular_floor = series_floor(regular_dates, fallback=dashboard_start_date)
        days_sorted = day_range(regular_end, regular_floor, spending_daily_window)
        all_cats = set()
        for d in day_exp_regular:
            all_cats.update(day_exp_regular[d].keys())
        top8 = ordered_top_categories(
            all_cats, category_order=list(dtpl_raw("category_order") or []), top_n=8
        )
        series, day_totals_all = stacked_category_series(
            day_exp_regular,
            days_sorted,
            top8,
            rest_label=dtpl("misc", "rest_category"),
        )
        x_labels = format_day_labels(days_sorted)
        part_day_regular.extend([
            dtpl("sections", "daily_regular", "heading"),
            "",
            dtpl("sections", "daily_regular", "threshold_note", threshold=oneoff_threshold_rub),
        ])
        if badge_category:
            part_day_regular.append(dtpl("sections", "daily_regular", "badge_note", category=badge_category))
        if last_spend_date:
            gap = (today - last_spend_date).days
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
            y_label=base_currency(),
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
        oneoff_end = spending_axis_end(oneoff_dates, today=today)
        oneoff_floor = series_floor(oneoff_dates, fallback=dashboard_start_date)
        days_sorted_oneoff = day_range(oneoff_end, oneoff_floor, oneoff_daily_window)
        x_labels = format_day_labels(days_sorted_oneoff)
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
            y_label=base_currency(),
            out_path=out_png,
        )
        if ok:
            part_day_oneoff.append(wikilink_png(out_png))
        else:
            part_day_oneoff.append(dtpl("sections", "daily_oneoff", "no_data"))
        part_day_oneoff.extend(["", ""])

    # Daily income vs expense
    day_flow = accumulate_daily_flow(
        transactions,
        acc_by_id=acc_by_id,
        exclude_categories=exclude_spending_categories,
        badge_category=badge_category,
        parse_datetime=parse_datetime,
    )

    if day_flow:
        flow_dates = set(day_flow.keys())
        flow_end_date = spending_axis_end(flow_dates, today=today)
        flow_floor = series_floor(flow_dates, fallback=dashboard_start_date)
        days_sorted_flow = day_range(flow_end_date, flow_floor, flow_daily_window)
        inc_vals = [float(day_flow.get(d, {}).get("income", 0)) for d in days_sorted_flow]
        exp_vals = [float(day_flow.get(d, {}).get("expense", 0)) for d in days_sorted_flow]
        x_labels = format_day_labels(days_sorted_flow)
        part_day_flow.extend([
            dtpl("sections", "daily_flow", "heading"),
            "",
        ])
        out_png = charts_dir / dtpl("charts", "flow_daily_file")
        ok = plot_lines_png(
            x_labels,
            {dtpl("charts", "income"): inc_vals, dtpl("charts", "expense"): exp_vals},
            title=dtpl("charts", "flow_daily_title"),
            y_label=base_currency(),
            out_path=out_png,
        )
        if ok:
            part_day_flow.append(wikilink_png(out_png))
        else:
            part_day_flow.append(dtpl("sections", "daily_flow", "no_data"))
        part_day_flow.extend(["", ""])

        # Weekly charts
        week_flow = accumulate_weekly_flow(
            transactions,
            acc_by_id=acc_by_id,
            exclude_categories=exclude_spending_categories,
            parse_datetime=parse_datetime,
        )

        if week_flow:
            week_end = max(week_flow.keys())
            week_floor = min(week_flow.keys())
            weeks_sorted = week_range(week_end, week_floor, weekly_flow_weeks)
            xw = [w.strftime("%d.%m") for w in weeks_sorted]
            inc_w = [float(week_flow.get(w, {}).get("income", 0)) for w in weeks_sorted]
            exp_w = [float(week_flow.get(w, {}).get("expense", 0)) for w in weeks_sorted]
            out_png = charts_dir / dtpl("charts", "flow_weekly_file")
            ok = plot_lines_png(
                xw,
                {dtpl("charts", "income"): inc_w, dtpl("charts", "expense"): exp_w},
                title=dtpl("charts", "flow_weekly_title"),
                y_label=base_currency(),
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
        week_exp_regular = accumulate_weekly_regular_spending(
            transactions,
            acc_by_id=acc_by_id,
            exclude_categories=exclude_spending_categories,
            badge_category=badge_category,
            oneoff_threshold_rub=oneoff_threshold_rub,
            misc_label=misc_category_label(),
            parse_datetime=parse_datetime,
        )

        if week_exp_regular:
            week_end = max(week_exp_regular.keys())
            week_floor = min(week_exp_regular.keys())
            weeks_sorted = week_range(week_end, week_floor, weekly_spending_weeks)
            top_cats = top_cats_by_total(week_exp_regular, weeks_sorted, top_n=8)
            series, week_totals_labels = stacked_category_series(
                week_exp_regular,
                weeks_sorted,
                top_cats,
                rest_label=dtpl("misc", "rest_category"),
            )
            xw = [w.strftime("%d.%m") for w in weeks_sorted]
            out_png = charts_dir / dtpl("charts", "exp_weekly_file")
            ok = plot_stacked_bar_categories_png(
                xw,
                series,
                title=dtpl("charts", "exp_weekly_title"),
                y_label=base_currency(),
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
        if not is_base_currency(acc_by_id.get(t["account_id"], {}).get("currency")):
            continue
        occ = parse_datetime(t.get("occurred_at"))
        if occ:
            balance_data_dates.add(occ.date())
    for snapshots in broker_snapshots.values():
        for snap_date, _ in snapshots:
            balance_data_dates.add(snap_date)
    balance_floor = series_floor(balance_data_dates, fallback=dashboard_start_date)
    balance_chart_end = max(
        spending_axis_end(balance_data_dates, today=today) if balance_data_dates else today,
        today,
    )
    days_total = day_range(balance_chart_end, balance_floor, balance_daily_window)
    broker_rub_account_ids = [
        aid
        for aid, a in acc_by_id.items()
        if is_base_currency(a.get("currency"))
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
        if not is_base_currency(a.get("currency")):
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
        if not is_base_currency(a.get("currency")):
            continue
        if acc_by_id[a["id"]].get("is_external_balance"):
            continue
        run_by_account[a["id"]] = Decimal(str(a.get("external_balance") or 0))
    plateau_external_rub = external_base_non_portfolio_total(balances_now, acc_by_id)
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
    ])
    out_png = charts_dir / dtpl("charts", "balance_daily_file")
    balance_series = {dtpl("charts", "total_rub"): total_by_day}
    if show_cards:
        balance_series[dtpl("charts", "cards_rub")] = cards_by_day
    if show_broker:
        balance_series[dtpl("charts", "broker_rub")] = broker_by_day
    ok = plot_lines_png(
        format_day_labels(days_total),
        balance_series,
        title=dtpl("charts", "balance_daily_title"),
        y_label=base_currency(),
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

    # Spending by account — current month only (list, not lifetime dump pie)
    exp_by_account = defaultdict(Decimal)
    for t in transactions:
        if t["type"] != "expense" or is_excluded_category(t, exclude_spending_categories) or is_badge_expense(t, badge_category):
            continue
        occ = parse_datetime(t["occurred_at"])
        if not occ or occ < month_start:
            continue
        if not is_base_currency(acc_by_id.get(t["account_id"], {}).get("currency")):
            continue
        exp_by_account[t.get("account_name") or dtpl("misc", "unknown_account")] += Decimal(
            str(t["amount"])
        )
    if exp_by_account:
        part_exp_by_account.append(
            dtpl("sections", "by_account", "month_list_heading") or "**Spend by account (month):**"
        )
        for name, val in sorted(exp_by_account.items(), key=lambda x: -x[1])[:8]:
            part_exp_by_account.append(
                f"- **{name}**: {fmt_num(float(val), decimals=0)} {base_currency()}"
            )
        part_exp_by_account.append("")

    # Balances — skip zeros / noise; cash + broker first
    def _bal_sort_key(a: dict) -> tuple:
        bal = float(balances_now.get(a["id"], 0) or 0)
        name = str(a.get("name") or "")
        is_noise = name.startswith(("receivable:", "liability_")) or abs(bal) < 0.01
        return (is_noise, -abs(bal), name)

    visible_accounts = [
        a
        for a in accounts
        if abs(float(balances_now.get(a["id"], 0) or 0)) >= 1.0
        or (
            _badge_acc_name
            and str(a.get("name") or "") == _badge_acc_name
        )
    ]
    visible_accounts = sorted(visible_accounts, key=_bal_sort_key)
    hidden_n = len(accounts) - len(visible_accounts)
    part_balances.append(dtpl("sections", "balances_table", "list_heading") or "**Balances:**")
    for a in visible_accounts:
        if str(a.get("name") or "").startswith(("receivable:", "liability_")):
            continue
        bal = float(balances_now.get(a["id"], 0) or 0)
        cur = a.get("currency") or base_currency()
        part_balances.append(
            f"- **{a['name']}**: {fmt_num(bal, decimals=2 if abs(bal) < 100 else 0)} {cur}"
        )
    # Debts / receivables — one compact line if any
    debt_bits = []
    for a in visible_accounts:
        name = str(a.get("name") or "")
        if not name.startswith(("receivable:", "liability_")):
            continue
        bal = float(balances_now.get(a["id"], 0) or 0)
        if abs(bal) < 0.01:
            continue
        short = name.split(":", 1)[-1]
        kind = dtpl(
            "sections",
            "balances_table",
            "receivable_kind" if name.startswith("receivable:") else "liability_kind",
        )
        debt_bits.append(f"{short} {fmt_num(bal, decimals=0)} {a.get('currency') or ''} ({kind})")
    if debt_bits:
        part_balances.append(
            dtpl("sections", "balances_table", "debts_line", bits="; ".join(debt_bits[:6]))
        )
    if hidden_n > 0:
        part_balances.append(dtpl("sections", "balances_table", "hidden_zero", n=hidden_n))
    part_balances.append("")

    # Top expenses last 30 days
    cutoff = now - timedelta(days=30)
    recent_exp = []
    for t in transactions:
        if t["type"] != "expense":
            continue
        if is_excluded_category(t, exclude_spending_categories):
            continue
        if is_badge_expense(t, badge_category):
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
        part_top_exp.append(dtpl("sections", "top_expenses", "list_intro") or "")
        for acc, cat, amt, occ, desc in recent_exp[:15]:
            dt = occ[:10] if isinstance(occ, str) else str(occ)[:10]
            comment = safe_comment(desc)
            tail = f" — {comment}" if comment and comment != "—" else ""
            part_top_exp.append(
                f"- **{fmt_num(float(amt), decimals=0)} {base_currency()}** · {cat or dtpl('misc', 'dash')} · {acc} · {dt}{tail}"
            )
        part_top_exp.append("")

    # Monthly income vs expense
    monthly = defaultdict(lambda: {"income": Decimal(0), "expense": Decimal(0)})
    for t in transactions:
        occ = parse_datetime(t["occurred_at"])
        if not occ:
            continue
        if t.get("type") not in ("income", "expense"):
            continue
        if is_excluded_category(t, exclude_spending_categories):
            continue
        if is_badge_expense(t, badge_category):
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
        if is_excluded_category(t, exclude_spending_categories):
            continue
        if is_badge_expense(t, badge_category):
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
            y_label=base_currency(),
            out_path=out_png,
        )
        if ok:
            part_quarterly.append(wikilink_png(out_png))
        else:
            part_quarterly.append(dtpl("sections", "quarterly", "no_data"))
        part_quarterly.extend(["", ""])

    # One-off list (bullets — tables break inside Obsidian <details>)
    if "oneoff_txns" in locals() and oneoff_txns:
        oneoff_txns.sort(key=lambda x: -x[2])
        hint = dtpl("sections", "oneoff_list", "hint", threshold=oneoff_threshold_rub)
        if hint:
            part_oneoff_list.append(hint)
        for acc, cat, amt, dt, desc in oneoff_txns[:10]:
            comment = safe_comment(desc)
            tail = f" — {comment}" if comment and comment != "—" else ""
            part_oneoff_list.append(
                f"- **{fmt_num(float(amt), decimals=0)} {base_currency()}** · {cat or dtpl('misc', 'dash')} · {acc} · {dt}{tail}"
            )
        part_oneoff_list.append("")

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
            y_label=base_currency(),
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


    return {
        "part_structure": part_structure,
        "part_exp_pies": part_exp_pies,
        "part_moves": part_moves,
        "part_day_flow": part_day_flow,
        "part_day_regular": part_day_regular,
        "part_day_oneoff": part_day_oneoff,
        "part_oneoff_list": part_oneoff_list,
        "part_monthly": part_monthly,
        "part_quarterly": part_quarterly,
        "part_exp_by_account": part_exp_by_account,
        "part_balances": part_balances,
        "part_top_exp": part_top_exp,
        "part_total_balance": part_total_balance,
    }
