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

    charts = []

    def publish(chart_id, dates, series, title, *, method='sum', chart_type='line'):
        from shared.obsidian_ui.series import series_chart
        charts.append(series_chart(chart_id, title, dates, series, method=method,
                                   chart_type=chart_type, unit=base_currency(), filter_fields=[]))

    part_structure: list = []
    part_exp_pies: list = []
    part_moves: list = []
    part_oneoff_list: list = []
    part_exp_by_account: list = []
    part_balances: list = []
    part_top_exp: list = []

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
    balance_daily_window = chart_window_int('balance_days','FIN_BALANCE_DAILY_WINDOW_DAYS',0)

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
    out_png = charts_dir / dtpl("charts", "balance_daily_file")
    balance_series = {dtpl("charts", "total_rub"): total_by_day}
    if show_cards:
        balance_series[dtpl("charts", "cards_rub")] = cards_by_day
    if show_broker:
        balance_series[dtpl("charts", "broker_rub")] = broker_by_day
    publish('balance', days_total, balance_series, dtpl('charts','balance_daily_title'), method='last')

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

    return {
        "charts": charts,
        "oneoff_threshold": oneoff_threshold_rub,
        "part_structure": part_structure,
        "part_exp_pies": part_exp_pies,
        "part_moves": part_moves,
        "part_oneoff_list": part_oneoff_list,
        "part_exp_by_account": part_exp_by_account,
        "part_balances": part_balances,
        "part_top_exp": part_top_exp,
    }
