"""Daily / weekly aggregation helpers for finance dashboard charts."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Callable, Mapping, Optional, Sequence

from bot.services.dashboard.filters import is_badge_expense, is_excluded_category

from shared.finance.currency import is_base_currency

ParseDatetime = Callable[[object], Optional[object]]


def _is_base_ccy(acc_by_id: Mapping, account_id: object) -> bool:
    return is_base_currency(acc_by_id.get(account_id, {}).get("currency"))


def accumulate_daily_spending(
    transactions: Sequence[Mapping],
    *,
    acc_by_id: Mapping,
    exclude_categories: set[str],
    badge_category: Optional[str],
    oneoff_threshold_rub: float,
    misc_label: str,
    parse_datetime: ParseDatetime,
    unknown_account_label: str,
) -> tuple[
    dict[date, dict[str, Decimal]],
    dict[date, Decimal],
    list[tuple[str, str, float, str, str]],
]:
    """Return (day_exp_regular, day_exp_oneoff_total, oneoff_txns)."""
    day_exp_regular: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    day_exp_oneoff_total: dict[date, Decimal] = defaultdict(Decimal)
    oneoff_txns: list[tuple[str, str, float, str, str]] = []
    for t in transactions:
        if t["type"] != "expense":
            continue
        occ = parse_datetime(t["occurred_at"])
        if not occ:
            continue
        if not _is_base_ccy(acc_by_id, t["account_id"]):
            continue
        if is_excluded_category(t, exclude_categories):
            continue
        if is_badge_expense(t, badge_category):
            continue
        amt = Decimal(str(t["amount"]))
        cat = t["category"] or misc_label
        if float(amt) >= oneoff_threshold_rub:
            day_exp_oneoff_total[occ.date()] += amt  # type: ignore[union-attr]
            date_str = t["occurred_at"][:10] if len(t["occurred_at"]) >= 10 else t["occurred_at"]
            oneoff_txns.append(
                (
                    t.get("account_name") or unknown_account_label,
                    cat,
                    float(amt),
                    date_str,
                    t.get("description") or "",
                )
            )
        else:
            day_exp_regular[occ.date()][cat] += amt  # type: ignore[union-attr]
    return day_exp_regular, day_exp_oneoff_total, oneoff_txns


def accumulate_daily_flow(
    transactions: Sequence[Mapping],
    *,
    acc_by_id: Mapping,
    exclude_categories: set[str],
    badge_category: Optional[str],
    parse_datetime: ParseDatetime,
) -> dict[date, dict[str, Decimal]]:
    """Return day -> {income, expense} for base-currency non-excluded / non-badge txns."""
    day_flow: dict[date, dict[str, Decimal]] = defaultdict(
        lambda: {"income": Decimal(0), "expense": Decimal(0)}
    )
    for t in transactions:
        occ = parse_datetime(t["occurred_at"])
        if not occ:
            continue
        if not _is_base_ccy(acc_by_id, t["account_id"]):
            continue
        if is_excluded_category(t, exclude_categories):
            continue
        if is_badge_expense(t, badge_category):
            continue
        dday = occ.date()  # type: ignore[union-attr]
        amt = Decimal(str(t["amount"]))
        if t["type"] == "income":
            day_flow[dday]["income"] += amt
        elif t["type"] == "expense":
            day_flow[dday]["expense"] += amt
    return day_flow


def accumulate_weekly_flow(
    transactions: Sequence[Mapping],
    *,
    acc_by_id: Mapping,
    exclude_categories: set[str],
    parse_datetime: ParseDatetime,
) -> dict[date, dict[str, Decimal]]:
    """Return week_start (Monday) -> {income, expense}. Badge expenses are included."""
    week_flow: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for t in transactions:
        if not _is_base_ccy(acc_by_id, t["account_id"]):
            continue
        if is_excluded_category(t, exclude_categories):
            continue
        occ = parse_datetime(t.get("occurred_at"))
        if not occ:
            continue
        dday = occ.date()  # type: ignore[union-attr]
        week_start = dday - timedelta(days=dday.weekday())
        amt = Decimal(str(t["amount"]))
        if t["type"] == "income":
            week_flow[week_start]["income"] += amt
        elif t["type"] == "expense":
            week_flow[week_start]["expense"] += amt
    return week_flow


def accumulate_weekly_regular_spending(
    transactions: Sequence[Mapping],
    *,
    acc_by_id: Mapping,
    exclude_categories: set[str],
    badge_category: Optional[str],
    oneoff_threshold_rub: float,
    misc_label: str,
    parse_datetime: ParseDatetime,
) -> dict[date, dict[str, Decimal]]:
    """Return week_start -> category -> amount for regular (below-threshold) expenses."""
    week_exp_regular: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for t in transactions:
        if t["type"] != "expense":
            continue
        if not _is_base_ccy(acc_by_id, t["account_id"]):
            continue
        if is_excluded_category(t, exclude_categories):
            continue
        if is_badge_expense(t, badge_category):
            continue
        occ = parse_datetime(t.get("occurred_at"))
        if not occ:
            continue
        amt = Decimal(str(t["amount"]))
        if float(amt) >= oneoff_threshold_rub:
            continue
        cat = t["category"] or misc_label
        dday = occ.date()  # type: ignore[union-attr]
        week_start = dday - timedelta(days=dday.weekday())
        week_exp_regular[week_start][cat] += amt
    return week_exp_regular


def ordered_top_categories(
    all_cats: set[str],
    *,
    category_order: Sequence[str],
    top_n: int = 8,
) -> list[str]:
    sorted_cats = [c for c in category_order if c in all_cats]
    sorted_cats += sorted(all_cats - set(sorted_cats))
    return sorted_cats[:top_n]


def stacked_category_series(
    by_period: Mapping[date, Mapping[str, Decimal]],
    periods: Sequence[date],
    top_cats: Sequence[str],
    *,
    rest_label: str,
    rest_threshold: float = 0.5,
) -> tuple[dict[str, list[float]], list[float]]:
    """Build stacked series + period totals; add rest bucket when above threshold."""
    series = {
        cat: [float(by_period.get(p, {}).get(cat, 0)) for p in periods] for cat in top_cats
    }
    rest_vals: list[float] = []
    for p in periods:
        bucket = by_period.get(p, {})
        total_p = sum(bucket.values())
        in_top = sum(bucket.get(c, 0) for c in top_cats)
        rest_vals.append(float(total_p - in_top))
    if any(v > rest_threshold for v in rest_vals):
        series[rest_label] = rest_vals
    totals = [float(sum(by_period.get(p, {}).values())) for p in periods]
    return series, totals


def top_cats_by_total(
    by_period: Mapping[date, Mapping[str, Decimal]],
    periods: Sequence[date],
    *,
    top_n: int = 8,
) -> list[str]:
    total_by_cat: dict[str, Decimal] = defaultdict(Decimal)
    for p in periods:
        for cat, v in by_period.get(p, {}).items():
            total_by_cat[cat] += v
    return [c for c, _ in sorted(total_by_cat.items(), key=lambda x: -x[1])[:top_n]]
