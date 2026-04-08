from __future__ import annotations

import calendar
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytz
from sqlalchemy import select

from shared.agent.app import build_app
from shared.domain_messages import dmsg
from shared.finance_classification import uncategorized_label
from shared.finance_classification import (
    INVESTMENT_EXPENSE_CATEGORIES,
    is_consumption_expense,
    is_internal_move_expense,
    split_month_flows,
)
from shared.memory import get_history

from ..agent_tools import FINANCE_DOMAIN, FinanceAdapter
from ..config import get_settings
from ..config_loader import CONFIG_DIR
from ..db import AsyncSessionLocal
from ..llm import LLMClient
from ..models import Transaction, User

log = logging.getLogger("finance.analyst")


def get_conversation_history(telegram_id: int) -> List[Dict]:
    return [
        {"role": m.role, "content": m.content or ""}
        for m in get_history(telegram_id, FINANCE_DOMAIN)
    ]


def clear_conversation(telegram_id: int) -> None:
    from shared.memory.session import clear_history

    clear_history(telegram_id, FINANCE_DOMAIN)


def _load_user_context() -> str:
    path = CONFIG_DIR / "user_context.md"
    if not path.exists():
        return dmsg("finance_analyst", "user_context_missing")
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception as e:
        log.warning("Could not read user_context.md: %s", e)
        return dmsg("finance_analyst", "user_context_read_error")


def _load_prompt(filename: str) -> str:
    path = CONFIG_DIR / filename
    if not path.exists():
        log.warning("Prompt not found: %s", path)
        return ""
    return path.read_text(encoding="utf-8").strip()


class FinancialAnalyst:
    """LLM-driven financial analyst with persistent user context."""

    def __init__(self) -> None:
        self.llm = LLMClient()
        self.settings = get_settings()

    def _now(self) -> datetime:
        try:
            tz = pytz.timezone(self.settings.TIMEZONE)
            return datetime.now(tz)
        except Exception:
            return datetime.now()

    async def _get_user_id(self, telegram_id: int) -> Optional[int]:
        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
            ).scalar_one_or_none()
            return user.id if user else None

    async def _fetch_transactions(
        self, user_id: int, days: Optional[int] = None
    ) -> List[Dict]:
        """Returns raw transactions as plain dicts. If days is None — entire history."""
        async with AsyncSessionLocal() as session:
            q = select(Transaction).where(Transaction.user_id == user_id)
            if days is not None:
                cutoff = self._now() - timedelta(days=days)
                q = q.where(Transaction.occurred_at >= cutoff)
            rows = (
                await session.execute(q.order_by(Transaction.occurred_at.desc()))
            ).scalars().all()
            return [
                {
                    "date": t.occurred_at.strftime("%Y-%m-%d"),
                    "type": t.type,
                    "amount": float(t.amount),
                    "currency": t.currency or "RUB",
                    "category": t.category or "",
                    "description": t.description or "",
                }
                for t in rows
            ]

    def _compute_baselines(self, transactions: List[Dict]) -> Dict[str, float]:
        """Computes per-category monthly median from past months (pure math).
        Investment categories are excluded — they are savings, not consumption.
        """
        now = self._now()
        current_month_key = now.strftime("%Y-%m")

        by_month: Dict[str, Dict[str, float]] = {}
        for t in transactions:
            if t["type"] != "expense":
                continue
            month_key = t["date"][:7]
            if month_key == current_month_key:
                continue
            cat = t["category"] or uncategorized_label()
            if cat in INVESTMENT_EXPENSE_CATEGORIES:
                continue  # investments are savings, not consumption baselines
            if is_internal_move_expense(t):
                continue
            if month_key not in by_month:
                by_month[month_key] = {}
            by_month[month_key][cat] = by_month[month_key].get(cat, 0.0) + t["amount"]

        if not by_month:
            return {}

        all_cats: set = set()
        for m in by_month.values():
            all_cats.update(m.keys())

        baselines: Dict[str, float] = {}
        for cat in all_cats:
            values = sorted(by_month[m].get(cat, 0.0) for m in by_month)
            n = len(values)
            median = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2
            baselines[cat] = round(median, 0)

        return baselines

    def _monthly_summary_text(self, transactions: List[Dict]) -> str:
        """Builds a per-month text summary for every month that has data (newest first).
        Investment categories (broker, etc.) are shown separately as savings.
        """
        if not transactions:
            return dmsg("finance_analyst", "no_data")

        months = sorted(
            {t["date"][:7] for t in transactions},
            reverse=True,
        )
        lines: List[str] = []

        for month_key in months:
            try:
                y, m = int(month_key[:4]), int(month_key[5:7])
                month_label = datetime(y, m, 1).strftime("%B %Y")
            except (ValueError, IndexError):
                month_label = month_key

            month_txns = [t for t in transactions if t["date"].startswith(month_key)]
            if not month_txns:
                continue

            income, consumption, investments, transfers_out, cat_totals = split_month_flows(
                month_txns
            )
            true_savings = income - consumption
            savings_rate = true_savings / income * 100 if income else 0

            top = sorted(cat_totals.items(), key=lambda x: -x[1])[:5]

            lines.append(f"\n{month_label}:")
            invest_part = dmsg("finance_analyst", "month_invest_part", investments=investments) if investments > 0 else ""
            lines.append(
                dmsg(
                    "finance_analyst",
                    "month_income_line",
                    income=income,
                    consumption=consumption,
                    invest_part=invest_part,
                )
            )
            if transfers_out > 0:
                lines.append(
                    dmsg("finance_analyst", "month_transfers_line", transfers=transfers_out)
                )
            invest_rate_part = (
                dmsg(
                    "finance_analyst",
                    "month_invest_rate_part",
                    rate=(true_savings + investments) / income * 100,
                )
                if investments > 0 and income > 0
                else ""
            )
            lines.append(
                dmsg(
                    "finance_analyst",
                    "month_savings_line",
                    savings=true_savings,
                    rate=savings_rate,
                    invest_rate_part=invest_rate_part,
                )
            )
            lines.append(dmsg("finance_analyst", "month_top_categories"))
            for cat, amt in top:
                pct = amt / consumption * 100 if consumption else 0
                lines.append(dmsg("finance_analyst", "month_category_line", category=cat, amount=amt, pct=pct))

        return "\n".join(lines) if lines else dmsg("finance_analyst", "no_data")

    def _format_transactions_for_llm(
        self, transactions: List[Dict], days: Optional[int] = None
    ) -> str:
        """If days is None, includes all transactions (chronological: oldest first for reading)."""
        if days is not None:
            cutoff = (self._now() - timedelta(days=days)).strftime("%Y-%m-%d")
            subset = [t for t in transactions if t["date"] >= cutoff]
        else:
            subset = list(transactions)
        if not subset:
            return dmsg("finance_analyst", "no_txns_in_period")

        # Oldest first — easier for LLM to scan full history
        subset = sorted(subset, key=lambda x: (x["date"], x.get("description", "")))

        lines = []
        type_map = {"expense": dmsg("budget", "txn_type_expense"), "income": dmsg("budget", "txn_type_income"), "transfer": dmsg("budget", "txn_type_transfer")}
        for t in subset:
            sign = "+" if t["type"] == "income" else "-"
            desc_part = f" ({t['description']})" if t["description"] else ""
            ttype = type_map.get(t["type"], t["type"])
            lines.append(
                f"{t['date']} | {ttype} | {sign}{t['amount']:,.0f}₽"
                f" | {t['category']}{desc_part}"
            )
        return "\n".join(lines)

    def _days_until_month_end(self, now: datetime) -> int:
        last_day = calendar.monthrange(now.year, now.month)[1]
        return last_day - now.day

    def _build_context_block(
        self,
        user_context: str,
        baselines: Dict,
        monthly_summary: str,
        transactions_text: str,
        label: str = "period",
    ) -> str:
        return (
            dmsg("finance_analyst", "context_user", user_context=user_context)
            + dmsg("finance_analyst", "context_baselines", baselines=json.dumps(baselines, ensure_ascii=False, indent=2))
            + dmsg("finance_analyst", "context_monthly", monthly=monthly_summary)
            + dmsg("finance_analyst", "context_txns", label=label.upper(), transactions=transactions_text)
        )

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def route_message(self, text: str, telegram_id: Optional[int] = None) -> Dict:
        """LLM: finance_query | add_transaction | chitchat (shared/agent/llm_classify)."""
        from shared.agent.llm_classify import classify_finance_intent_llm

        intent = await classify_finance_intent_llm(text, chat_id=telegram_id)
        return {"intent": intent}

    async def answer_query(self, telegram_id: int, question: str) -> str:
        """Finance Q&A via agent core."""
        user_id = await self._get_user_id(telegram_id)
        if not user_id:
            return dmsg("finance_analyst", "user_not_found")
        if not _load_prompt("query_prompt.txt"):
            return dmsg("finance_analyst", "prompt_query_missing")

        app = build_app(self.llm, FinanceAdapter(self))
        return await app.answer(FINANCE_DOMAIN, telegram_id, question)

    async def run_analysis(
        self, telegram_id: int, period: str = "week"
    ) -> str:
        """Runs a deep weekly or monthly analysis, returns formatted text."""
        if period == "month":
            return await self.run_calendar_month_analysis(telegram_id)
        return await self._run_analysis_for_days(telegram_id, period)

    async def run_calendar_month_analysis(
        self,
        telegram_id: int,
        *,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> str:
        """Full calendar month analysis (default: previous month)."""
        user_id = await self._get_user_id(telegram_id)
        if not user_id:
            return dmsg("finance_analyst", "user_not_found")

        prompt = _load_prompt("analyst_prompt.txt")
        if not prompt:
            return dmsg("finance_analyst", "prompt_analyst_missing")

        now = self._now()
        if year is None or month is None:
            first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_prev = first_this - timedelta(days=1)
            year, month = last_prev.year, last_prev.month

        month_key = f"{year:04d}-{month:02d}"
        try:
            month_label = datetime(year, month, 1).strftime("%B %Y")
        except ValueError:
            month_label = month_key

        user_context = _load_user_context()
        txns_all = await self._fetch_transactions(user_id, days=None)
        baselines = self._compute_baselines(txns_all)
        monthly = self._monthly_summary_text(txns_all)

        period_text = self._format_transactions_for_llm(
            [t for t in txns_all if t["date"].startswith(month_key)],
            days=None,
        )
        context = self._build_context_block(
            user_context,
            baselines,
            monthly,
            period_text,
            label=dmsg("finance_analyst", "calendar_month_label", month_label=month_label),
        )

        date_hint = dmsg("finance_analyst", "date_hint_calendar", today=now.strftime("%Y-%m-%d"), month_label=month_label)

        response = await self.llm.chat([
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"{date_hint}\n\n{context}"},
        ])
        return response or dmsg("finance_analyst", "analysis_failed")

    async def _run_analysis_for_days(
        self, telegram_id: int, period: str = "week"
    ) -> str:
        """Weekly (rolling) analysis."""
        user_id = await self._get_user_id(telegram_id)
        if not user_id:
            return dmsg("finance_analyst", "user_not_found")

        prompt = _load_prompt("analyst_prompt.txt")
        if not prompt:
            return dmsg("finance_analyst", "prompt_analyst_missing")

        user_context = _load_user_context()
        txns_all = await self._fetch_transactions(user_id, days=None)
        baselines = self._compute_baselines(txns_all)
        monthly = self._monthly_summary_text(txns_all)

        now = self._now()
        days_map = {"week": 7, "month": 30}
        period_days = days_map.get(period, 7)
        period_start = now - timedelta(days=period_days)

        if period == "week":
            period_label = (
                dmsg("finance_analyst", "period_week_label", from_date=period_start.strftime("%d.%m"), to_date=now.strftime("%d.%m.%Y"))
            )
        else:
            period_label = dmsg("finance_analyst", "period_month_label", month_label=now.strftime("%B %Y"))

        period_text = self._format_transactions_for_llm(txns_all, days=period_days)
        context = self._build_context_block(
            user_context, baselines, monthly, period_text, label=f"period ({period_label})"
        )

        date_hint = dmsg("finance_analyst", "date_hint_period", today=now.strftime("%Y-%m-%d"), period_label=period_label)

        response = await self.llm.chat([
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"{date_hint}\n\n{context}"},
        ])
        return response or dmsg("finance_analyst", "analysis_failed")

    _INSIGHT_ANGLES = [
        "spending_velocity",
        "category_deep_dive",
        "savings_rate",
        "unusual_pattern",
        "monthly_prediction",
        "investment_check",
        "best_worst_week",
    ]

    async def daily_insight(self, telegram_id: int) -> Optional[str]:
        """Generates a random daily insight. Returns None if no data or LLM silent."""
        user_id = await self._get_user_id(telegram_id)
        if not user_id:
            return None

        prompt_template = _load_prompt("daily_insight_prompt.txt")
        if not prompt_template:
            return None

        angle = random.choice(self._INSIGHT_ANGLES)
        prompt = prompt_template.replace("{insight_angle}", angle)

        user_context = _load_user_context()
        txns_all = await self._fetch_transactions(user_id, days=None)
        if not txns_all:
            return None

        baselines = self._compute_baselines(txns_all)
        monthly = self._monthly_summary_text(txns_all)
        recent_text = self._format_transactions_for_llm(txns_all, days=None)

        now = self._now()
        context = dmsg(
            "finance_analyst",
            "insight_context",
            user_context=user_context,
            baselines=json.dumps(baselines, ensure_ascii=False, indent=2),
            monthly=monthly,
            count=len(txns_all),
            recent_text=recent_text,
            today=now.strftime("%Y-%m-%d"),
            days_left=self._days_until_month_end(now),
        )

        response = await self.llm.chat([
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
        ])
        return response.strip() if response else None

    async def quick_check(
        self, telegram_id: int, saved_transactions: List[Dict]
    ) -> Optional[str]:
        """Post-transaction check: returns a short alert string or None."""
        if not saved_transactions:
            return None

        user_id = await self._get_user_id(telegram_id)
        if not user_id:
            return None

        prompt = _load_prompt("quick_check_prompt.txt")
        if not prompt:
            return None

        user_context = _load_user_context()
        txns_all = await self._fetch_transactions(user_id, days=None)
        baselines = self._compute_baselines(txns_all)

        now = self._now()
        current_month_key = now.strftime("%Y-%m")
        month_txns = [t for t in txns_all if t["date"].startswith(current_month_key)]

        cat_month: Dict[str, float] = {}
        for t in month_txns:
            if is_consumption_expense(t):
                cat = t["category"] or uncategorized_label()
                cat_month[cat] = cat_month.get(cat, 0.0) + t["amount"]

        saved_text = "\n".join(
            f"- {t.get('type', '?')} | {t.get('amount', 0):,.0f}₽"
            f" | {t.get('category', '')} | {t.get('description', '')}"
            for t in saved_transactions
        )

        context = (
            dmsg("finance_analyst", "context_user", user_context=user_context)
            + dmsg("finance_analyst", "quick_check_saved", saved_text=saved_text)
            + dmsg("finance_analyst", "quick_check_baselines", baselines=json.dumps(baselines, ensure_ascii=False, indent=2))
            + dmsg("finance_analyst", "quick_check_month", cat_month=json.dumps(cat_month, ensure_ascii=False, indent=2))
            + dmsg("finance_analyst", "quick_check_footer", today=now.strftime("%Y-%m-%d"), days_left=self._days_until_month_end(now))
        )

        result = await self.llm.chat_json([
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
        ])
        if not result:
            return None
        alert = result.get("alert")
        return alert if alert else None
