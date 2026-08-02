"""Finance agent tools for shared agent core."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func, select

from shared.agent.app import DomainAdapter
from shared.agent.budget import format_txn_recent, format_txn_summary
from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import AgentContext, ModelRole
from shared.domain_messages import dmsg
from shared.finance.txn_query import (
    fetch_transaction_rows,
    format_broker_overview,
    format_debts_summary,
    format_spending_by_category,
)
from shared.parsing.date_range import resolve_date_range

if TYPE_CHECKING:
    from bot.services.financial_analyst import FinancialAnalyst

from bot.db import AsyncSessionLocal
from bot.models import Account, PlannedExpense, Transaction, User
from bot.services.badge_tracker import BadgeTracker, is_badge_account_name
from bot.services.subscriptions import load_subscriptions

FINANCE_DOMAIN = "finance"
_FA = ("finance_agent",)


def _analyst(ctx: AgentContext) -> "FinancialAnalyst":
    a = ctx.extras.get("analyst")
    if a is None:
        raise RuntimeError("analyst missing in AgentContext.extras")
    return a


async def _telegram_id(ctx: AgentContext) -> int:
    return int(ctx.extras.get("telegram_id") or ctx.user_id)


async def _user_id(ctx: AgentContext) -> Optional[int]:
    return await _analyst(ctx)._get_user_id(await _telegram_id(ctx))


def _range_label(dr, *, days: int = 0) -> str:
    if dr.start and dr.end:
        return f"{dr.start.isoformat()} … {dr.end.isoformat()}"
    if days:
        return dmsg(*_FA, "range_last_days", days=days)
    return dmsg(*_FA, "range_all_time")


async def _fetch_rows(ctx: AgentContext, **kwargs) -> tuple[Optional[int], list]:
    from shared.parsing.date_range import DateRange

    uid = await _user_id(ctx)
    if not uid:
        return None, []
    fd = kwargs.get("from_date", "")
    td = kwargs.get("to_date", "")
    days = int(kwargs.get("days") or 0)
    default_days = kwargs.get("default_days")
    anchor = _analyst(ctx)._now().date()
    if default_days is None and not fd and not td and not days:
        dr = DateRange(None, None)
    else:
        dr = resolve_date_range(
            from_date=fd,
            to_date=td,
            days=days,
            default_days=default_days if default_days is not None else 30,
            anchor=anchor,
        )
    async with AsyncSessionLocal() as session:
        rows = await fetch_transaction_rows(
            session,
            uid,
            dr=dr,
            category=kwargs.get("category"),
            txn_type=kwargs.get("txn_type"),
        )
    return uid, rows


@tool(category="transactions", always=True)
async def get_transactions(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    category: str = "",
) -> str:
    """Transactions in interval (from/to YYYY-MM-DD or days). category matches parent+children (Еда, Еда/, Еда/* → Еда/Вне дома, Еда/Продукты)."""
    analyst = _analyst(ctx)
    uid, rows = await _fetch_rows(
        ctx, from_date=from_date, to_date=to_date, days=days, default_days=30, category=category or None
    )
    if uid is None:
        return dmsg(*_FA, "user_not_found")
    dr = resolve_date_range(
        from_date=from_date, to_date=to_date, days=days, default_days=30, anchor=analyst._now().date()
    )
    label = dmsg(*_FA, "transactions_label", range=_range_label(dr, days=days))
    monthly = analyst._monthly_summary_text(rows) if rows else ""
    body = format_txn_summary(rows, label=label)
    if monthly:
        body += dmsg(*_FA, "monthly_header") + monthly
    return body


@tool(category="transactions")
async def get_spending_by_category(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
    category: str = "",
    group_by: str = "",
) -> str:
    """Spending by category (consumption). category=parent matches children (Еда → Еда/*). group_by=day for per-day totals (join with task completions)."""
    uid, rows = await _fetch_rows(
        ctx,
        from_date=from_date,
        to_date=to_date,
        days=days,
        default_days=30,
        category=category or None,
    )
    if uid is None:
        return dmsg(*_FA, "user_not_found")
    dr = resolve_date_range(from_date=from_date, to_date=to_date, days=days, default_days=30)
    gb = (group_by or "").strip().lower()
    return format_spending_by_category(
        rows,
        label=dmsg(*_FA, "spending_by_category", range=_range_label(dr, days=days)),
        category=category or None,
        group_by_day=gb in ("day", "days", "daily", "date"),
    )


@tool(category="balance")
async def get_balance(ctx: AgentContext) -> str:
    """Current account balances (compact)."""
    tg_id = await _telegram_id(ctx)
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == tg_id))
        ).scalar_one_or_none()
        if user is None:
            return dmsg(*_FA, "user_not_found")

        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()

        lines = [dmsg(*_FA, "balances_header")]
        for acc in accounts:
            if is_badge_account_name(acc.name):
                continue
            inc = (
                await session.execute(
                    select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                        Transaction.account_id == acc.id, Transaction.type == "income"
                    )
                )
            ).scalar_one()
            exp = (
                await session.execute(
                    select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                        Transaction.account_id == acc.id, Transaction.type == "expense"
                    )
                )
            ).scalar_one()
            if acc.is_external_balance and acc.external_balance is not None:
                bal = Decimal(acc.external_balance)
            else:
                base = Decimal(acc.external_balance) if acc.external_balance is not None else Decimal(0)
                bal = base + Decimal(inc) - Decimal(exp)
            if bal == 0 and acc.type not in ("crypto",):
                continue
            lines.append(f"  {acc.name}: {bal:,.2f} {acc.currency} ({acc.type})")
        if len(lines) == 1:
            lines.append(dmsg(*_FA, "no_nonzero_accounts"))
        return "\n".join(lines)


@tool(category="transactions")
async def get_recent(
    ctx: AgentContext,
    n: int = 10,
    from_date: str = "",
    to_date: str = "",
) -> str:
    """Last N operations (optional from/to interval)."""
    uid, rows = await _fetch_rows(ctx, from_date=from_date, to_date=to_date, default_days=None)
    if uid is None:
        return dmsg(*_FA, "user_not_found")
    if not rows and not (from_date or to_date):
        rows = await _analyst(ctx)._fetch_transactions(uid, days=None)
    return format_txn_recent(rows, n=max(1, min(int(n), 50)))


@tool(category="summary")
async def compute_summary(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
) -> str:
    """Income/expense summary for interval (from/to YYYY-MM-DD or days)."""
    analyst = _analyst(ctx)
    uid, subset = await _fetch_rows(ctx, from_date=from_date, to_date=to_date, days=days, default_days=30)
    if uid is None:
        return dmsg(*_FA, "user_not_found")
    all_rows = await analyst._fetch_transactions(uid, days=None)
    dr = resolve_date_range(
        from_date=from_date, to_date=to_date, days=days, default_days=30, anchor=analyst._now().date()
    )
    label = dmsg(*_FA, "summary_label", range=_range_label(dr, days=days))
    baselines = analyst._compute_baselines(all_rows)
    monthly = analyst._monthly_summary_text(all_rows)
    parts = [
        format_txn_summary(subset, label=label),
        dmsg(*_FA, "baselines", baselines=baselines) if baselines else "",
        dmsg(*_FA, "monthly_header") + monthly if monthly else "",
    ]
    return "\n\n".join(p for p in parts if p)


@tool(category="planning")
async def get_planned_expenses(ctx: AgentContext, status: str = "active") -> str:
    """Planned expenses (status: active | done | cancelled | all)."""
    tg_id = await _telegram_id(ctx)
    st = (status or "active").strip().lower()
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == tg_id))
        ).scalar_one_or_none()
        if not user:
            return dmsg(*_FA, "user_not_found")
        q = select(PlannedExpense).where(PlannedExpense.user_id == user.id)
        if st != "all":
            q = q.where(PlannedExpense.status == st)
        plans = (await session.execute(q.order_by(PlannedExpense.due_date.asc().nullslast()))).scalars().all()
    if not plans:
        return dmsg(*_FA, "planned_empty", status=st)
    lines = [dmsg(*_FA, "planned_header", status=st)]
    for p in plans:
        due = (
            p.due_date.strftime("%Y-%m-%d")
            if p.due_date
            else dmsg(*_FA, "planned_no_due", default="no deadline")
        )
        lines.append(
            dmsg(
                *_FA,
                "planned_line",
                name=p.name,
                amount=float(p.amount),
                currency=p.currency,
                due=due,
            )
        )
    return "\n".join(lines)


@tool(category="planning")
async def get_finance_forecast(ctx: AgentContext) -> str:
    """LLM forecast: cash vs plans (DB + subscriptions.yaml)."""
    from bot.services.planning_forecast import generate_forecast

    tg_id = await _telegram_id(ctx)
    return await generate_forecast(tg_id)


@tool(category="subscriptions")
async def get_subscriptions(ctx: AgentContext) -> str:
    """Recurring subscriptions from config/subscriptions.yaml."""
    subs = load_subscriptions()
    if not subs:
        return dmsg(*_FA, "subscriptions_empty")
    lines = [dmsg(*_FA, "subscriptions_header")]
    for s in subs:
        lines.append(
            dmsg(
                *_FA,
                "subscription_line",
                name=s.name,
                amount=s.amount,
                currency=s.currency,
                period=s.period,
                next_charge=s.next_charge,
            )
        )
    return "\n".join(lines)


@tool(category="debts")
async def get_debts_summary(ctx: AgentContext) -> str:
    """Debt summary (receivable / liability_payable accounts)."""
    uid = await _user_id(ctx)
    if not uid:
        return dmsg(*_FA, "user_not_found")
    async with AsyncSessionLocal() as session:
        return await format_debts_summary(session, uid)


@tool(category="investments")
async def get_broker_overview(ctx: AgentContext) -> str:
    """Broker and external account balances."""
    uid = await _user_id(ctx)
    if not uid:
        return dmsg(*_FA, "user_not_found")
    async with AsyncSessionLocal() as session:
        return await format_broker_overview(session, uid)


@tool(category="badge")
async def get_badge_status(ctx: AgentContext, day: str = "") -> str:
    """Meal badge status: day=YYYY-MM-DD or today."""
    tg_id = await _telegram_id(ctx)
    target = date.today()
    if (day or "").strip():
        from shared.parsing.iso_date import parse_iso_calendar_day

        parsed = parse_iso_calendar_day(day)
        if parsed:
            target = parsed
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == tg_id))
        ).scalar_one_or_none()
        if not user:
            return dmsg(*_FA, "user_not_found")
        tracker = BadgeTracker()
        acc = await tracker.get_or_create_badge_account(session, user.id)
        ds = await tracker.day_stats(session, user.id, target, acc.id)
        ms = await tracker.month_stats(session, user.id, target.year, target.month)
        return tracker.format_day_status(ds, ms)


def build_finance_registry() -> ToolRegistry:
    from shared.capabilities.registry import filter_finance_tools, register_tools
    from shared.memory.episodic import attach_memory_tools

    reg = ToolRegistry()
    register_tools(
        reg,
        filter_finance_tools(
            [
                get_transactions,
                get_spending_by_category,
                get_balance,
                get_recent,
                compute_summary,
                get_planned_expenses,
                get_finance_forecast,
                get_subscriptions,
                get_debts_summary,
                get_broker_overview,
                get_badge_status,
            ]
        ),
    )
    attach_memory_tools(reg)
    return reg


class FinanceAdapter(DomainAdapter):
    domain = FINANCE_DOMAIN
    role = ModelRole.ANALYZE

    def __init__(self, analyst: "FinancialAnalyst") -> None:
        self._analyst = analyst

    def build_registry(self) -> ToolRegistry:
        return build_finance_registry()

    async def base_prompt(self, ctx: AgentContext) -> str:
        from bot.services.financial_analyst import _load_prompt

        base = _load_prompt("query_prompt.txt")
        now = self._analyst._now()
        date_hint = dmsg(
            *_FA,
            "date_hint",
            today=now.strftime("%Y-%m-%d"),
            month=now.strftime("%B %Y"),
        )
        suffix = dmsg(*_FA, "prompt_suffix")
        return f"{base}\n\n{date_hint}\n{suffix}"

    def memory_layers(self, ctx: AgentContext):
        from shared.memory.layers import build_memory_layers

        return build_memory_layers(FINANCE_DOMAIN)

    async def prepare_extras(self, user_id: int) -> dict:
        return {"analyst": self._analyst, "telegram_id": user_id}
