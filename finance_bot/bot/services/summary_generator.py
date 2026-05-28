from typing import Dict
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from sqlalchemy import select, func

from shared.domain_messages import dmsg
from shared.finance_classification import (
    INVESTMENT_EXPENSE_CATEGORIES,
    exclude_income_categories,
    exclude_spending_categories,
)

from ..llm import LLMClient
from ..db import AsyncSessionLocal
from ..models import Transaction, User
from ..config_loader import get_summary_prompt, get_summary_config

log = logging.getLogger("finance.summary")


def _excluded_consumption_categories() -> list[str]:
    return sorted(exclude_spending_categories() | INVESTMENT_EXPENSE_CATEGORIES)


def _excluded_income_categories() -> list[str]:
    return sorted(exclude_income_categories())


class FinanceSummaryGenerator:
    """Generate finance summaries for reflection."""

    def __init__(self):
        self.llm = LLMClient()
        self.prompt_template = get_summary_prompt()
        if not self.prompt_template:
            log.warning("Summary prompt not loaded, using empty prompt")
            self.prompt_template = ""
        self.config = get_summary_config()
        self.top_categories_limit = self.config.get("top_categories_limit", 5)
        self.periods = self.config.get("periods", {"week": 7, "month": 30})

    async def generate(self, telegram_id: int, period: str = "week") -> str:
        """Generate summary for period (week or month)."""
        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(select(User).where(User.telegram_id == telegram_id))
            ).scalar_one_or_none()
            if not user:
                return dmsg("finance_summary", "user_not_found")
            user_id = user.id

        data = await self._get_period_data(user_id, period)
        data_text = self._format_data_for_prompt(data, period)

        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": self.prompt_template},
                {"role": "user", "content": dmsg("finance_summary", "period_user", period=period) + "\n\n" + data_text},
            ]
        )

        if not response:
            raise RuntimeError(dmsg("finance_summary", "llm_empty"))

        return response

    async def _get_period_data(self, user_id: int, period: str) -> Dict:
        """Fetch aggregated data for period."""
        async with AsyncSessionLocal() as session:
            end_date = datetime.now()
            days = self.periods.get(period, self.periods.get("week", 7))
            start_date = end_date - timedelta(days=days)
            excl_exp = _excluded_consumption_categories()
            excl_inc = _excluded_income_categories()

            income_q = (
                select(func.sum(Transaction.amount))
                .where(
                    Transaction.user_id == user_id,
                    Transaction.type == "income",
                    Transaction.occurred_at >= start_date,
                )
            )
            if excl_inc:
                income_q = income_q.where(Transaction.category.notin_(excl_inc))
            income = (await session.execute(income_q)).scalar_one() or Decimal(0)

            expense_q = (
                select(func.sum(Transaction.amount))
                .where(
                    Transaction.user_id == user_id,
                    Transaction.type == "expense",
                    Transaction.occurred_at >= start_date,
                )
            )
            if excl_exp:
                expense_q = expense_q.where(Transaction.category.notin_(excl_exp))
            expenses = (await session.execute(expense_q)).scalar_one() or Decimal(0)

            category_expenses = (
                await session.execute(
                    select(Transaction.category, func.sum(Transaction.amount))
                    .where(
                        Transaction.user_id == user_id,
                        Transaction.type == "expense",
                        Transaction.occurred_at >= start_date,
                        Transaction.category.isnot(None),
                        Transaction.category.notin_(excl_exp) if excl_exp else True,
                    )
                    .group_by(Transaction.category)
                    .order_by(func.sum(Transaction.amount).desc())
                    .limit(self.top_categories_limit)
                )
            ).all()

            prev_start = start_date - (end_date - start_date)
            prev_expense_q = (
                select(func.sum(Transaction.amount))
                .where(
                    Transaction.user_id == user_id,
                    Transaction.type == "expense",
                    Transaction.occurred_at >= prev_start,
                    Transaction.occurred_at < start_date,
                )
            )
            if excl_exp:
                prev_expense_q = prev_expense_q.where(Transaction.category.notin_(excl_exp))
            prev_expenses = (await session.execute(prev_expense_q)).scalar_one() or Decimal(0)

            return {
                "income": float(income),
                "expenses": float(expenses),
                "category_expenses": [(cat, float(amt)) for cat, amt in category_expenses],
                "prev_expenses": float(prev_expenses),
                "start_date": start_date,
                "end_date": end_date,
            }

    def _format_data_for_prompt(self, data: Dict, period: str) -> str:
        """Format period stats for LLM prompt."""
        lines = []
        lines.append(
            dmsg(
                "finance_summary",
                "prompt_period",
                from_date=data["start_date"].strftime("%Y-%m-%d"),
                to_date=data["end_date"].strftime("%Y-%m-%d"),
            )
        )
        lines.append(dmsg("finance_summary", "income_line", amount=data["income"]))
        lines.append(dmsg("finance_summary", "expense_line", amount=data["expenses"]))
        lines.append(dmsg("finance_summary", "balance_line", amount=data["income"] - data["expenses"]))
        lines.append("")
        lines.append(dmsg("finance_summary", "top_categories"))
        total_expenses = data["expenses"]
        for cat, amt in data["category_expenses"]:
            pct = (amt / total_expenses * 100) if total_expenses > 0 else 0
            lines.append(dmsg("finance_summary", "category_line", category=cat, amount=amt, pct=pct))
        lines.append("")
        if data["prev_expenses"] > 0:
            change = ((data["expenses"] - data["prev_expenses"]) / data["prev_expenses"]) * 100
            lines.append(dmsg("finance_summary", "expense_change", change=change))

        return "\n".join(lines)
