"""Transaction queries for agent tools (date range, aggregates)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from shared.domain_messages import dmsg
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
    cat_q = (category or "").strip()
    cat_l = cat_q.lower()
    for t in rows:
        if cat_l:
            tc = (t.category or "").lower()
            if cat_q.endswith("/"):
                if not tc.startswith(cat_l):
                    continue
            elif cat_l not in tc:
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


def format_spending_by_category(rows: list[dict[str, Any]], *, label: str) -> str:
    by_cat: dict[str, float] = defaultdict(float)
    total = 0.0
    for r in rows:
        if r.get("type") != "expense" or not is_consumption_expense(r):
            continue
        amt = float(r["amount"])
        cat = (r.get("category") or misc_category_label()).strip()
        by_cat[cat] += amt
        total += amt
    if not by_cat:
        return f"{label}\n{dmsg('finance_txn_query', 'no_expenses_in_period')}"
    lines = [label, dmsg("finance_txn_query", "expenses_total", total=total)]
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        pct = (amt / total * 100) if total else 0
        lines.append(f"  {cat}: {amt:,.0f} ({pct:.0f}%)")
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
