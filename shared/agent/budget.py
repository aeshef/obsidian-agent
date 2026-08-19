"""Compact tool-result formatting (fewer tokens in loop)."""
from __future__ import annotations

from typing import Any, Iterable

from shared.domain_messages import dmsg
from shared.finance_classification import is_consumption_expense, is_real_income, uncategorized_label


def format_int_amount(value: float | int) -> str:
    """Grouping with spaces so verify and LLM see the same integer as tools."""
    n = int(round(float(value)))
    sign = "-" if n < 0 else ""
    return f"{sign}{abs(n):,}".replace(",", " ")


def compact_lines(header: str, lines: Iterable[str], *, max_lines: int = 40) -> str:
    items = list(lines)
    if not items:
        return f"{header}\n{dmsg('budget', 'no_data')}"
    shown = items[:max_lines]
    out = [header] + shown
    if len(items) > max_lines:
        out.append(dmsg("budget", "truncated", count=len(items) - max_lines))
    return "\n".join(out)


def filter_rows_by_query(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Casefold substring match on description + category (universal, not scenario-specific)."""
    q = (query or "").strip().casefold()
    if not q:
        return list(rows)
    out: list[dict[str, Any]] = []
    for r in rows:
        hay = f"{r.get('description') or ''} {r.get('category') or ''}".casefold()
        if q in hay:
            out.append(r)
    return out


def _format_line(r: dict[str, Any]) -> str:
    sign = "+" if r.get("type") == "income" else "-"
    type_map = {
        "expense": dmsg("budget", "txn_type_expense"),
        "income": dmsg("budget", "txn_type_income"),
        "transfer": dmsg("budget", "txn_type_transfer"),
    }
    ttype = type_map.get(r.get("type", ""), r.get("type", ""))
    desc = (r.get("description") or "").strip()
    desc_part = f" | {desc}" if desc else ""
    return (
        f"{r.get('date')} | {ttype} | {sign}{format_int_amount(r.get('amount', 0))}₽"
        f" | {r.get('category', '')}{desc_part}"
    )


def format_txn_summary(
    rows: list[dict[str, Any]],
    *,
    label: str,
) -> str:
    """Aggregates and category totals. Line dumps: format_txn_matches / format_txn_recent."""
    if not rows:
        return f"{label}\n{dmsg('budget', 'no_transactions')}"

    expenses = [r for r in rows if is_consumption_expense(r)]
    income = [r for r in rows if is_real_income(r)]
    exp_sum = sum(float(r.get("amount", 0)) for r in expenses)
    inc_sum = sum(float(r.get("amount", 0)) for r in income)

    by_cat: dict[str, float] = {}
    for r in expenses:
        cat = r.get("category") or uncategorized_label()
        by_cat[cat] = by_cat.get(cat, 0.0) + float(r.get("amount", 0))

    top = sorted(by_cat.items(), key=lambda x: -x[1])[:8]
    lines = [
        dmsg(
            "budget",
            "summary",
            label=label,
            count=len(rows),
            exp_sum=format_int_amount(exp_sum),
            inc_sum=format_int_amount(inc_sum),
        ),
        dmsg("budget", "top_categories"),
    ]
    for cat, amt in top:
        pct = amt / exp_sum * 100 if exp_sum else 0
        lines.append(f"  - {cat}: {format_int_amount(amt)}₽ ({pct:.0f}%)")

    by_inc: dict[str, float] = {}
    for r in income:
        cat = r.get("category") or uncategorized_label()
        by_inc[cat] = by_inc.get(cat, 0.0) + float(r.get("amount", 0))
    if by_inc:
        lines.append(dmsg("budget", "income_categories"))
        for cat, amt in sorted(by_inc.items(), key=lambda x: -x[1]):
            pct = amt / inc_sum * 100 if inc_sum else 0
            lines.append(f"  - {cat}: {format_int_amount(amt)}₽ ({pct:.0f}%)")

    if expenses:
        threshold = max(float(r.get("amount", 0)) for r in expenses) * 0.5
        anomalies = [
            r for r in expenses if float(r.get("amount", 0)) >= threshold and threshold > 0
        ][:5]
        if anomalies:
            lines.append(dmsg("budget", "large_expenses"))
            for r in sorted(anomalies, key=lambda x: -float(x.get("amount", 0))):
                lines.append(f"  {_format_line(r)}")

    return "\n".join(lines)


def format_txn_recent(rows: list[dict[str, Any]], *, n: int) -> str:
    if not rows:
        return dmsg("budget", "no_operations")
    lines = [_format_line(r) for r in rows[:n]]
    return compact_lines(
        dmsg("budget", "recent_header", n=min(n, len(rows))), lines, max_lines=n
    )


def format_txn_matches(
    rows: list[dict[str, Any]],
    *,
    label: str,
    query: str,
    limit: int = 80,
    requested_start: Any = None,
    requested_end: Any = None,
) -> str:
    """Line listing for query matches (always includes comments when present)."""
    if not rows:
        return f"{label}\n{dmsg('budget', 'no_query_matches', query=query)}"
    total = sum(float(r.get("amount", 0)) for r in rows if r.get("type") == "income")
    exp = sum(float(r.get("amount", 0)) for r in rows if r.get("type") == "expense")
    header = dmsg(
        "budget",
        "query_matches_header",
        label=label,
        query=query,
        count=len(rows),
        inc_sum=format_int_amount(total),
        exp_sum=format_int_amount(exp),
    )
    shown = sorted(rows, key=lambda x: x.get("date") or "", reverse=True)
    display = shown[: max(1, limit)]
    from shared.query.log_dump import assemble_log_dump, coverage_of, events_from_pairs, format_event_shares
    from shared.query.ts import parse_iso_dt

    chrono = sorted(rows, key=lambda x: x.get("date") or "")
    chrono_shown = sorted(display, key=lambda x: x.get("date") or "")
    cov = coverage_of(
        requested_start=parse_iso_dt(requested_start) if requested_start is not None else None,
        requested_end=parse_iso_dt(requested_end) if requested_end is not None else None,
        matched_ts=[parse_iso_dt(r.get("date")) for r in chrono],
        shown_ts=[parse_iso_dt(r.get("date")) for r in chrono_shown],
        slice_kind="tail" if len(display) < len(rows) else "all",
    )
    pairs = [(r.get("date"), r.get("category") or r.get("type") or "?") for r in rows]
    lines = [_format_line(r) for r in display]
    return assemble_log_dump(
        title=header,
        coverage=cov,
        shares=format_event_shares(events_from_pairs(pairs), column="category"),
        rows=lines,
    )
