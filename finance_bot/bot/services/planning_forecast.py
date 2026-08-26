"""Planning forecast service — LLM with plans, subscriptions, balances context."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import select, func
import logging
import re

from shared.domain_messages import dmsg
from shared.finance.currency import base_currency, is_base_currency

from ..llm import LLMClient
from ..db import AsyncSessionLocal
from ..models import User, Account, Transaction, PlannedExpense

log = logging.getLogger("finance.planning")


def _month_name(m: int) -> str:
    names = dmsg("planning_forecast", "month_names").split(",")
    return names[m].strip() if 1 <= m < len(names) else str(m)


async def get_planning_data(telegram_id: int) -> str:
    """Build planning prompt context block."""
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not user:
            return dmsg("planning_forecast", "user_not_found")

        from bot.services.month_plan import lapse_past_planned_orm

        await lapse_past_planned_orm(session, today=datetime.now().date(), user_id=user.id)

        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()
        total_rub_planned = Decimal(0)
        total_rub_all = Decimal(0)
        for a in accounts:
            if not is_base_currency(a.currency):
                continue
            if a.is_external_balance and a.external_balance:
                bal = a.external_balance
            else:
                base = a.external_balance or 0
                inc = (
                    await session.execute(
                        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                            Transaction.account_id == a.id, Transaction.type == "income"
                        )
                    )
                ).scalar_one()
                exp = (
                    await session.execute(
                        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                            Transaction.account_id == a.id, Transaction.type == "expense"
                        )
                    )
                ).scalar_one()
                bal = base + Decimal(inc) - Decimal(exp)
            total_rub_all += bal
            if not a.is_external_balance:
                total_rub_planned += bal

        plans = (
            await session.execute(
                select(PlannedExpense)
                .where(PlannedExpense.user_id == user.id, PlannedExpense.status == "active")
                .order_by(PlannedExpense.due_date.asc())
            )
        ).scalars().all()

        from datetime import timedelta
        three_months_ago = datetime.now() - timedelta(days=90)
        income_3m = (
            await session.execute(
                select(func.sum(Transaction.amount)).where(
                    Transaction.user_id == user.id,
                    Transaction.type == "income",
                    Transaction.occurred_at >= three_months_ago,
                )
            )
        ).scalar_one() or 0
        expense_3m = (
            await session.execute(
                select(func.sum(Transaction.amount)).where(
                    Transaction.user_id == user.id,
                    Transaction.type == "expense",
                    Transaction.occurred_at >= three_months_ago,
                )
            )
        ).scalar_one() or 0

    now = datetime.now()
    lines = []
    lines.append(
        dmsg(
            "planning_forecast",
            "current_date",
            date=now.strftime("%Y-%m-%d"),
            day=now.day,
            month_name=_month_name(now.month),
            year=now.year,
        )
    )
    lines.append("")
    lines.append(dmsg("planning_forecast", "balance_planned", amount=float(total_rub_planned)))
    lines.append(dmsg("planning_forecast", "balance_all", amount=float(total_rub_all)))
    lines.append(dmsg("planning_forecast", "avg_income_3m", amount=float(income_3m) / 3))
    lines.append(dmsg("planning_forecast", "avg_expense_3m", amount=float(expense_3m) / 3))
    lines.append("")
    lines.append(dmsg("planning_forecast", "planned_header"))
    if plans:
        for p in plans:
            due = p.due_date.strftime("%Y-%m-%d") if p.due_date else dmsg("planning_forecast", "no_due")
            lines.append(
                dmsg(
                    "planning_forecast",
                    "planned_line",
                    name=p.name,
                    amount=float(p.amount),
                    currency=p.currency,
                    due=due,
                )
            )
    else:
        lines.append(dmsg("planning_forecast", "planned_empty"))

    try:
        from pathlib import Path
        import yaml
        sub_path = Path(__file__).parent.parent.parent / "config" / "subscriptions.yaml"
        if sub_path.exists():
            with open(sub_path, encoding="utf-8") as f:
                subs = yaml.safe_load(f) or []
            if isinstance(subs, list):
                lines.append("")
                lines.append(dmsg("planning_forecast", "subscriptions_header"))
                for s in subs:
                    amt = s.get("amount", 0)
                    name = s.get("name", "")
                    period = s.get("period", "monthly")
                    lines.append(
                        dmsg(
                            "planning_forecast",
                            "subscription_line",
                            name=name,
                            amount=amt,
                            currency=s.get("currency") or base_currency(),
                            period=period,
                        )
                    )
    except Exception:
        pass

    return "\n".join(lines)


async def generate_forecast(telegram_id: int) -> str:
    """Generate forecast via LLM."""
    from ..config_loader import load_text_config
    prompt_template = load_text_config("planning_prompt.txt")
    if not prompt_template.strip():
        return dmsg("planning_forecast", "prompt_missing")

    data = await get_planning_data(telegram_id)
    llm = LLMClient()
    response = await llm.chat(
        messages=[
            {"role": "system", "content": prompt_template},
            {"role": "user", "content": data},
        ]
    )
    if not response:
        return dmsg("planning_forecast", "forecast_failed")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", response)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return text.strip()


async def generate_month_plan_summary(telegram_id: int) -> str:
    """Flexible month plan: income − commitments → daily free-to-spend."""
    from bot.ui import fmsg
    from bot.services.month_plan import (
        build_month_plan,
        inferred_from_config,
        load_month_plan_config,
        load_subscriptions,
        month_plan_config_path,
        planned_for_month,
        resolve_savings_buffer,
        subscriptions_yaml_path,
    )

    now = datetime.now()
    ym = f"{now.year:04d}-{now.month:02d}"
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not user:
            return fmsg("plan_month_need_user")

        from bot.services.month_plan import lapse_past_planned_orm

        await lapse_past_planned_orm(session, today=now.date(), user_id=user.id)

        plans = (
            await session.execute(
                select(PlannedExpense).where(
                    PlannedExpense.user_id == user.id,
                    PlannedExpense.status == "active",
                )
            )
        ).scalars().all()
        planned_rows = [
            {
                "name": p.name,
                "amount": float(p.amount or 0),
                "currency": p.currency or base_currency(),
                "due_date": p.due_date,
                "category": getattr(p, "category", "") or "",
            }
            for p in plans
        ]
        month_spend = (
            await session.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.user_id == user.id,
                    Transaction.type == "expense",
                    Transaction.occurred_at >= datetime(now.year, now.month, 1),
                )
            )
        ).scalar_one()
        try:
            month_spend_f = float(month_spend or 0)
        except (TypeError, ValueError):
            month_spend_f = 0.0

    mp_cfg = load_month_plan_config(month_plan_config_path())
    income = float(mp_cfg.get("income_expected_rub") or 0)
    if income <= 0:
        return fmsg("plan_month_need_income", path=str(month_plan_config_path().name))

    buffer, savings_rate = resolve_savings_buffer(mp_cfg, income)
    inferred = inferred_from_config(mp_cfg)
    subs = load_subscriptions(subscriptions_yaml_path())
    specifics = planned_for_month(planned_rows, ym)
    recurring_sum = sum(x.amount for x in subs) + sum(x.amount for x in inferred)
    flexible_spent = max(0.0, month_spend_f - recurring_sum)
    snap = build_month_plan(
        ym=ym,
        today=now.date(),
        income_expected=income,
        subscriptions=subs,
        specifics=specifics,
        inferred=inferred,
        buffer_savings=buffer,
        savings_rate_pct=savings_rate,
        flexible_spent=flexible_spent,
    )
    lines = [
        fmsg("plan_month_header", ym=ym),
        fmsg("plan_month_income", amount=snap.income_expected),
        fmsg("plan_month_commitment", amount=snap.commitment),
        fmsg("plan_month_flexible", amount=snap.flexible_pool),
        fmsg("plan_month_spent", amount=snap.flexible_spent, burn=snap.burn_pct),
        fmsg("plan_month_fair_daily", amount=snap.daily_allowance),
        fmsg("plan_month_daily", amount=snap.daily_allowance_remaining),
        "",
        fmsg("plan_month_hint"),
    ]
    return "\n".join(lines)