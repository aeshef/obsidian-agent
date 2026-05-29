"""Compact tool-result formatting (fewer tokens in loop)."""
from __future__ import annotations

from typing import Any, Iterable

from shared.domain_messages import dmsg
from shared.finance_classification import is_consumption_expense, is_real_income, uncategorized_label


def compact_lines(header: str, lines: Iterable[str], *, max_lines: int = 40) -> str:
    items = list(lines)
    if not items:
        return f"{header}\n{dmsg('budget', 'no_data')}"
    shown = items[:max_lines]
    out = [header] + shown
    if len(items) > max_lines:
        out.append(dmsg("budget", "truncated", count=len(items) - max_lines))
    return "\n".join(out)


def format_txn_summary(rows: list[dict[str, Any]], *, label: str) -> str:
    """Aggregates + top categories + anomalies (large amounts)."""
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
            exp_sum=f"{exp_sum:,.0f}",
            inc_sum=f"{inc_sum:,.0f}",
        ),
        dmsg("budget", "top_categories"),
    ]
    for cat, amt in top:
        pct = amt / exp_sum * 100 if exp_sum else 0
        lines.append(f"  - {cat}: {amt:,.0f}₽ ({pct:.0f}%)")

    if expenses:
        threshold = max(float(r.get("amount", 0)) for r in expenses) * 0.5
        anomalies = [
            r for r in expenses if float(r.get("amount", 0)) >= threshold and threshold > 0
        ][:5]
        if anomalies:
            lines.append(dmsg("budget", "large_expenses"))
            for r in sorted(anomalies, key=lambda x: -float(x.get("amount", 0))):
                lines.append(
                    f"  {r.get('date')} | {r.get('category')} | -{float(r.get('amount', 0)):,.0f}₽"
                )

    return "\n".join(lines)


def format_txn_recent(rows: list[dict[str, Any]], *, n: int) -> str:
    if not rows:
        return dmsg("budget", "no_operations")
    type_map = {
        "expense": dmsg("budget", "txn_type_expense"),
        "income": dmsg("budget", "txn_type_income"),
        "transfer": dmsg("budget", "txn_type_transfer"),
    }
    lines = []
    for r in rows[:n]:
        sign = "+" if r.get("type") == "income" else "-"
        ttype = type_map.get(r.get("type", ""), r.get("type", ""))
        desc = f" ({r.get('description')})" if r.get("description") else ""
        lines.append(
            f"{r.get('date')} | {ttype} | {sign}{float(r.get('amount', 0)):,.0f}₽"
            f" | {r.get('category', '')}{desc}"
        )
    return compact_lines(dmsg("budget", "recent_header", n=min(n, len(rows))), lines, max_lines=n)
