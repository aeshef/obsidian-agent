"""Инструменты finance для shared agent core."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func, select

from shared.agent.app import DomainAdapter
from shared.agent.budget import format_txn_recent, format_txn_summary
from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import AgentContext, ModelRole
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
        return f"последние {days} дн."
    return "всё время"


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
    """Транзакции за интервал: from_date/to_date YYYY-MM-DD или days. category: точное имя или префикс «Еда/»."""
    analyst = _analyst(ctx)
    uid, rows = await _fetch_rows(
        ctx, from_date=from_date, to_date=to_date, days=days, default_days=30, category=category or None
    )
    if uid is None:
        return "Пользователь не найден."
    dr = resolve_date_range(
        from_date=from_date, to_date=to_date, days=days, default_days=30, anchor=analyst._now().date()
    )
    label = f"Транзакции ({_range_label(dr, days=days)})"
    monthly = analyst._monthly_summary_text(rows) if rows else ""
    body = format_txn_summary(rows, label=label)
    if monthly:
        body += "\n\nПомесячно:\n" + monthly
    return body


@tool(category="transactions")
async def get_spending_by_category(
    ctx: AgentContext,
    from_date: str = "",
    to_date: str = "",
    days: int = 0,
) -> str:
    """Расходы по категориям (только потребление) за интервал (from/to или days)."""
    uid, rows = await _fetch_rows(ctx, from_date=from_date, to_date=to_date, days=days, default_days=30)
    if uid is None:
        return "Пользователь не найден."
    dr = resolve_date_range(from_date=from_date, to_date=to_date, days=days, default_days=30)
    return format_spending_by_category(rows, label=f"Расходы по категориям ({_range_label(dr, days=days)})")


@tool(category="balance")
async def get_balance(ctx: AgentContext) -> str:
    """Текущие балансы по счетам (компактно)."""
    tg_id = await _telegram_id(ctx)
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == tg_id))
        ).scalar_one_or_none()
        if user is None:
            return "Пользователь не найден."

        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()

        lines = ["Балансы по счетам:"]
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
            lines.append("  (нет ненулевых счетов)")
        return "\n".join(lines)


@tool(category="transactions")
async def get_recent(
    ctx: AgentContext,
    n: int = 10,
    from_date: str = "",
    to_date: str = "",
) -> str:
    """Последние N операций (опционально в интервале from/to)."""
    uid, rows = await _fetch_rows(ctx, from_date=from_date, to_date=to_date, default_days=None)
    if uid is None:
        return "Пользователь не найден."
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
    """Сводка доходов/расходов за интервал (from/to YYYY-MM-DD или days)."""
    analyst = _analyst(ctx)
    uid, subset = await _fetch_rows(ctx, from_date=from_date, to_date=to_date, days=days, default_days=30)
    if uid is None:
        return "Пользователь не найден."
    all_rows = await analyst._fetch_transactions(uid, days=None)
    dr = resolve_date_range(
        from_date=from_date, to_date=to_date, days=days, default_days=30, anchor=analyst._now().date()
    )
    label = f"Сводка ({_range_label(dr, days=days)})"
    baselines = analyst._compute_baselines(all_rows)
    monthly = analyst._monthly_summary_text(all_rows)
    parts = [
        format_txn_summary(subset, label=label),
        f"Базлайны (медиана прошлых месяцев): {baselines}" if baselines else "",
        f"Помесячно:\n{monthly}" if monthly else "",
    ]
    return "\n\n".join(p for p in parts if p)


@tool(category="planning")
async def get_planned_expenses(ctx: AgentContext, status: str = "active") -> str:
    """Запланированные расходы (status: active | done | cancelled | all)."""
    tg_id = await _telegram_id(ctx)
    st = (status or "active").strip().lower()
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == tg_id))
        ).scalar_one_or_none()
        if not user:
            return "Пользователь не найден."
        q = select(PlannedExpense).where(PlannedExpense.user_id == user.id)
        if st != "all":
            q = q.where(PlannedExpense.status == st)
        plans = (await session.execute(q.order_by(PlannedExpense.due_date.asc().nullslast()))).scalars().all()
    if not plans:
        return f"Запланированные расходы ({st}): (нет)"
    lines = [f"Запланированные расходы ({st}):"]
    for p in plans:
        due = p.due_date.strftime("%Y-%m-%d") if p.due_date else "без срока"
        lines.append(f"  {p.name}: {float(p.amount):,.0f} {p.currency} (к {due})")
    return "\n".join(lines)


@tool(category="planning")
async def get_finance_forecast(ctx: AgentContext) -> str:
    """LLM-прогноз: хватает ли денег на планы (контекст из БД + subscriptions.yaml)."""
    from bot.services.planning_forecast import generate_forecast

    tg_id = await _telegram_id(ctx)
    return await generate_forecast(tg_id)


@tool(category="subscriptions")
async def get_subscriptions(ctx: AgentContext) -> str:
    """Регулярные подписки из config/subscriptions.yaml."""
    subs = load_subscriptions()
    if not subs:
        return "Подписки: (файл пуст или не настроен)"
    lines = ["Подписки (регулярные):"]
    for s in subs:
        lines.append(f"  {s.name}: {s.amount} {s.currency}/{s.period}, след. {s.next_charge}")
    return "\n".join(lines)


@tool(category="debts")
async def get_debts_summary(ctx: AgentContext) -> str:
    """Сводка долгов (счета receivable / liability_payable)."""
    uid = await _user_id(ctx)
    if not uid:
        return "Пользователь не найден."
    async with AsyncSessionLocal() as session:
        return await format_debts_summary(session, uid)


@tool(category="investments")
async def get_broker_overview(ctx: AgentContext) -> str:
    """Брокерские и внешние балансы счетов."""
    uid = await _user_id(ctx)
    if not uid:
        return "Пользователь не найден."
    async with AsyncSessionLocal() as session:
        return await format_broker_overview(session, uid)


@tool(category="badge")
async def get_badge_status(ctx: AgentContext, day: str = "") -> str:
    """Статус бейджа питания: day=YYYY-MM-DD или сегодня."""
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
            return "Пользователь не найден."
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
        date_hint = (
            f"Сегодня: {now.strftime('%Y-%m-%d')}. Текущий месяц: {now.strftime('%B %Y')}."
        )
        return (
            f"{base}\n\n{date_hint}\n"
            "Обязательно вызывай инструменты для любых сумм, балансов, операций и сводок. "
            "Интервалы задавай through from_date/to_date (YYYY-MM-DD) или days. "
            "Не выдумывай цифры."
        )

    def memory_layers(self, ctx: AgentContext):
        from shared.memory.layers import build_memory_layers

        return build_memory_layers(FINANCE_DOMAIN)

    async def prepare_extras(self, user_id: int) -> dict:
        return {"analyst": self._analyst, "telegram_id": user_id}
