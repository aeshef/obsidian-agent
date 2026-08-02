"""Transaction queries for agent tools (date range, aggregates)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from shared.domain_messages import dmsg
from shared.finance.category_match import category_matches
from shared.finance_classification import is_consumption_expense, misc_category_label
from shared.parsing.date_range import DateRange


async def fetch_transaction_rows(
    session,
    user_id: int,
    *,
    dr: DateRange,
    category: str | None = None,
    txn_type: str | None = None,
) -> list[dict[str, Any]]:
    from bot.models import Transaction

    q = select(Transaction).where(Transaction.user_id == user_id)
    if dr.start:
        q = q.where(Transaction.occurred_at >= datetime.combine(dr.start, datetime.min.time()))
    if dr.end:
        q = q.where(
            Transaction.occurred_at
            < datetime.combine(dr.end, datetime.max.time()).replace(hour=23, minute=59, second=59)
        )
    if txn_type in ("expense", "income"):
        q = q.where(Transaction.type == txn_type)
    rows = (await session.execute(q.order_by(Transaction.occurred_at.desc()))).scalars().all()
    out: list[dict[str, Any]] = []
    for t in rows:
        if not category_matches(category, t.category):
            continue
        out.append(
            {
                "date": t.occurred_at.strftime("%Y-%m-%d"),
                "type": t.type,
                "amount": float(t.amount),
                "currency": t.currency or "RUB",
                "category": t.category or "",
                "description": t.description or "",
            }
        )
    return out


def format_spending_by_category(
    rows: list[dict[str, Any]],
    *,
    label: str,
    category: str | None = None,
    group_by_day: bool = False,
) -> str:
    """Aggregate consumption expenses; optional hierarchical category filter + daily split."""
    filtered: list[dict[str, Any]] = []
    for r in rows:
        if r.get("type") != "expense" or not is_consumption_expense(r):
            continue
        cat = (r.get("category") or misc_category_label()).strip()
        if not category_matches(category, cat):
            continue
        filtered.append({**r, "category": cat})

    if not filtered:
        return f"{label}\n{dmsg('finance_txn_query', 'no_expenses_in_period')}"

    total = sum(float(r["amount"]) for r in filtered)
    lines = [label, dmsg("finance_txn_query", "expenses_total", total=total)]
    if category and str(category).strip():
        lines.append(dmsg("finance_txn_query", "category_filter", category=str(category).strip()))

    if group_by_day:
        by_day_cat: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        by_day_total: dict[str, float] = defaultdict(float)
        for r in filtered:
            day = str(r.get("date") or "")
            amt = float(r["amount"])
            by_day_cat[day][r["category"]] += amt
            by_day_total[day] += amt
        lines.append(dmsg("finance_txn_query", "by_day_header"))
        for day in sorted(by_day_total):
            parts = [
                f"{cat}={amt:,.0f}"
                for cat, amt in sorted(by_day_cat[day].items(), key=lambda x: -x[1])
            ]
            detail = "; ".join(parts)
            lines.append(
                dmsg(
                    "finance_txn_query",
                    "by_day_line",
                    day=day,
                    total=by_day_total[day],
                    detail=detail,
                )
            )
        return "\n".join(lines)

    by_cat: dict[str, float] = defaultdict(float)
    for r in filtered:
        by_cat[r["category"]] += float(r["amount"])
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        pct = (amt / total * 100) if total else 0
        lines.append(f"  {cat}: {amt:,.0f} ({pct:.0f}%)")
    return "\n".join(lines)


def spending_total(
    rows: list[dict[str, Any]],
    *,
    category: str | None = None,
) -> float:
    """Sum consumption expenses, optional hierarchical category filter."""
    total = 0.0
    for r in rows:
        if r.get("type") != "expense" or not is_consumption_expense(r):
            continue
        cat = (r.get("category") or misc_category_label()).strip()
        if not category_matches(category, cat):
            continue
        total += float(r["amount"])
    return total


def format_period_compare(
    *,
    label_a: str,
    total_a: float,
    label_b: str,
    total_b: float,
    category: str | None = None,
) -> str:
    """Human-readable A vs B spend comparison."""
    delta = total_a - total_b
    if total_b:
        pct = (delta / total_b) * 100.0
        pct_s = f"{pct:+.0f}%"
    else:
        pct_s = "n/a"
    cat = (category or "").strip() or "all"
    lines = [
        f"Compare spend ({cat})",
        f"  A {label_a}: {total_a:,.0f}",
        f"  B {label_b}: {total_b:,.0f}",
        f"  Δ A−B: {delta:+,.0f} ({pct_s})",
    ]
    return "\n".join(lines)


async def format_debts_summary(session, user_id: int) -> str:
    from bot.models import Account

    accs = (
        await session.execute(select(Account).where(Account.user_id == user_id))
    ).scalars().all()
    recv = [a for a in accs if a.type == "receivable"]
    pay = [a for a in accs if a.type == "liability_payable"]
    if not recv and not pay:
        return dmsg("finance_txn_query", "debts_empty")
    lines = [dmsg("finance_txn_query", "debts_header")]
    for a in recv:
        bal = Decimal(a.external_balance or 0)
        if bal != 0:
            lines.append(
                dmsg(
                    "finance_txn_query",
                    "receivable_line",
                    name=a.name,
                    balance=f"{bal:,.2f}",
                    currency=a.currency,
                )
            )
    for a in pay:
        bal = Decimal(a.external_balance or 0)
        if bal != 0:
            lines.append(
                dmsg(
                    "finance_txn_query",
                    "payable_line",
                    name=a.name,
                    balance=f"{bal:,.2f}",
                    currency=a.currency,
                )
            )
    if len(lines) == 1:
        lines.append(dmsg("finance_txn_query", "all_zero"))
    return "\n".join(lines)


async def format_broker_overview(session, user_id: int) -> str:
    from bot.models import Account

    accs = (
        await session.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.type.in_(("broker", "crypto")),
            )
        )
    ).scalars().all()
    ext = (
        await session.execute(
            select(Account).where(
                Account.user_id == user_id,
                Account.is_external_balance.is_(True),
            )
        )
    ).scalars().all()
    seen = {a.id for a in accs}
    for a in ext:
        if a.id not in seen and a.type not in ("receivable", "liability_payable"):
            accs.append(a)
            seen.add(a.id)
    if not accs:
        return dmsg("finance_txn_query", "broker_empty")
    lines = [dmsg("finance_txn_query", "broker_header")]
    for a in accs:
        bal = a.external_balance
        if bal is None:
            lines.append(
                dmsg(
                    "finance_txn_query",
                    "balance_unset",
                    name=a.name,
                    acct_type=a.type,
                )
            )
        else:
            lines.append(f"  {a.name} ({a.type}): {float(bal):,.2f} {a.currency}")
    return "\n".join(lines)
