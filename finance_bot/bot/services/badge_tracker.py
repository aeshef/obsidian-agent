"""Badge meal metrics: daily buckets, quota burn, income tax, month summary."""

from __future__ import annotations

import calendar
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.domain_messages import dmsg

from ..config_loader import get_badge_config
from bot.ui import fmsg
from ..models import Account, Transaction, User


@dataclass
class BadgeDayStats:
    date: date
    is_working_day: bool
    limit: Decimal
    spent: Decimal
    burned: Decimal
    ndfl_cost: Decimal
    over_limit: Decimal

    @property
    def utilization_pct(self) -> float:
        if self.limit <= 0:
            return 0.0
        return float(self.spent / self.limit * 100)


@dataclass
class BadgeMonthStats:
    year: int
    month: int
    working_days: int
    days_with_spend: int
    total_entitlement: Decimal
    total_spent: Decimal
    total_burned: Decimal
    total_ndfl: Decimal
    total_over_limit: Decimal
    utilization_pct: float
    zero_spend_days: int
    days: List[BadgeDayStats]


def _cfg_decimal(cfg: dict, key: str, default: str) -> Decimal:
    return Decimal(str(cfg.get(key, default)))


def _parse_dates(raw: Any) -> set[date]:
    out: set[date] = set()
    if not raw:
        return out
    for item in raw:
        s = str(item).strip()[:10]
        try:
            out.add(date.fromisoformat(s))
        except ValueError:
            continue
    return out


class BadgeTracker:
    def __init__(self, config: Optional[dict] = None) -> None:
        self.cfg = config if config is not None else get_badge_config()
        if "daily_limit" in self.cfg:
            self.daily_limit = _cfg_decimal(self.cfg, "daily_limit", "0")
        else:
            self.daily_limit = _cfg_decimal(self.cfg, "daily_limit_rub", "1000")
        # Income-tax estimate on meal benefit (e.g. RU NDFL). 0 = disabled / non-taxable.
        self.ndfl_rate = Decimal(str(self.cfg.get("ndfl_rate", 0)))
        self.account_name = str(self.cfg.get("account_name", "Meal Badge"))
        self.category = str(self.cfg.get("category") or "")
        self._extra_off = _parse_dates(self.cfg.get("extra_non_working_days"))
        self._extra_on = _parse_dates(self.cfg.get("extra_working_days"))
        alerts = self.cfg.get("alerts") or {}
        self.burn_threshold_pct = float(alerts.get("burn_threshold_pct", 40))

    def is_working_day(self, d: date) -> bool:
        if d in self._extra_off:
            return False
        if d in self._extra_on:
            return True
        return d.weekday() < 5

    def working_days_in_month(self, year: int, month: int) -> List[date]:
        _, last = calendar.monthrange(year, month)
        return [date(year, month, day) for day in range(1, last + 1) if self.is_working_day(date(year, month, day))]

    def _day_metrics(self, d: date, spent: Decimal) -> BadgeDayStats:
        working = self.is_working_day(d)
        limit = self.daily_limit if working else Decimal(0)
        in_limit = min(spent, limit) if limit > 0 else Decimal(0)
        burned = max(Decimal(0), limit - spent) if working else Decimal(0)
        over = max(Decimal(0), spent - limit) if working else Decimal(0)
        ndfl = (in_limit * self.ndfl_rate).quantize(Decimal("0.01"))
        return BadgeDayStats(
            date=d,
            is_working_day=working,
            limit=limit,
            spent=spent,
            burned=burned,
            ndfl_cost=ndfl,
            over_limit=over,
        )

    @staticmethod
    def _spent_by_day_from_rows(rows: Sequence[Tuple[str, float]]) -> Dict[date, Decimal]:
        by_day: Dict[date, Decimal] = {}
        for occurred_at, amount in rows:
            if not occurred_at:
                continue
            s = str(occurred_at)[:10]
            try:
                d = date.fromisoformat(s)
            except ValueError:
                continue
            by_day[d] = by_day.get(d, Decimal(0)) + Decimal(str(amount))
        return by_day

    def compute_month_stats(self, year: int, month: int, spent_by_day: Dict[date, Decimal]) -> BadgeMonthStats:
        wdays = self.working_days_in_month(year, month)
        days_stats: List[BadgeDayStats] = []
        total_spent = Decimal(0)
        total_burned = Decimal(0)
        total_ndfl = Decimal(0)
        total_over = Decimal(0)
        days_with_spend = 0
        zero_days = 0

        for d in wdays:
            spent = spent_by_day.get(d, Decimal(0))
            ds = self._day_metrics(d, spent)
            days_stats.append(ds)
            total_spent += ds.spent
            total_burned += ds.burned
            total_ndfl += ds.ndfl_cost
            total_over += ds.over_limit
            if ds.spent > 0:
                days_with_spend += 1
            if ds.spent <= 0:
                zero_days += 1

        entitlement = self.daily_limit * len(wdays)
        util = float(total_spent / entitlement * 100) if entitlement > 0 else 0.0

        return BadgeMonthStats(
            year=year,
            month=month,
            working_days=len(wdays),
            days_with_spend=days_with_spend,
            total_entitlement=entitlement,
            total_spent=total_spent,
            total_burned=total_burned,
            total_ndfl=total_ndfl,
            total_over_limit=total_over,
            utilization_pct=util,
            zero_spend_days=zero_days,
            days=days_stats,
        )

    async def _fetch_spent_by_day(
        self, session: AsyncSession, user_id: int, year: int, month: int, account_id: int
    ) -> Dict[date, Decimal]:
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)
        q = (
            select(Transaction.occurred_at, Transaction.amount)
            .where(
                Transaction.user_id == user_id,
                Transaction.account_id == account_id,
                Transaction.type == "expense",
                Transaction.category == self.category,
                Transaction.occurred_at >= datetime.combine(start, datetime.min.time()),
                Transaction.occurred_at < datetime.combine(end, datetime.min.time()),
            )
        )
        rows = (await session.execute(q)).all()
        return self._spent_by_day_from_rows([(r[0], float(r[1])) for r in rows])

    async def get_or_create_badge_account(self, session: AsyncSession, user_id: int) -> Account:
        acc = (
            await session.execute(
                select(Account).where(Account.user_id == user_id, Account.name == self.account_name)
            )
        ).scalar_one_or_none()
        if acc:
            return acc
        acc = Account(
            user_id=user_id,
            name=self.account_name,
            type="badge",
            currency="RUB",
            is_external_balance=False,
            external_balance=Decimal(0),
        )
        session.add(acc)
        await session.flush()
        return acc

    async def day_stats(self, session: AsyncSession, user_id: int, d: date, account_id: int) -> BadgeDayStats:
        start = datetime.combine(d, datetime.min.time())
        end = start + timedelta(days=1)
        q = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
            Transaction.type == "expense",
            Transaction.category == self.category,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )
        spent = Decimal(str((await session.execute(q)).scalar_one()))
        return self._day_metrics(d, spent)

    async def month_stats(self, session: AsyncSession, user_id: int, year: int, month: int) -> BadgeMonthStats:
        acc = await self.get_or_create_badge_account(session, user_id)
        spent_by_day = await self._fetch_spent_by_day(session, user_id, year, month, acc.id)
        return self.compute_month_stats(year, month, spent_by_day)

    def month_stats_sync(self, conn: sqlite3.Connection, user_id: int, year: int, month: int) -> Optional[BadgeMonthStats]:
        acc = conn.execute(
            "SELECT id FROM accounts WHERE user_id=? AND name=? LIMIT 1",
            (user_id, self.account_name),
        ).fetchone()
        if not acc:
            return None
        account_id = acc[0]
        start = f"{year:04d}-{month:02d}-01"
        if month == 12:
            end = f"{year + 1:04d}-01-01"
        else:
            end = f"{year:04d}-{month + 1:02d}-01"
        rows = conn.execute(
            """SELECT occurred_at, amount FROM transactions
               WHERE user_id=? AND account_id=? AND type='expense' AND category=?
                 AND occurred_at >= ? AND occurred_at < ?""",
            (user_id, account_id, self.category, start, end),
        ).fetchall()
        spent_by_day = self._spent_by_day_from_rows(rows)
        return self.compute_month_stats(year, month, spent_by_day)

    def _tip(self, key: str, **kwargs: object) -> Optional[str]:
        tips = (self.cfg.get("coaching") or {}).get("tips") or {}
        tpl = tips.get(key)
        if not tpl:
            return None
        try:
            return str(tpl).format(**kwargs)
        except KeyError:
            return str(tpl)

    def rule_coaching_after_spend(
        self,
        ds: BadgeDayStats,
        ms: BadgeMonthStats,
        amount_added: Decimal,
    ) -> list[str]:
        """Threshold tips from config/coaching (no hardcoded scenarios in code)."""
        out: list[str] = []
        if ds.is_working_day and ds.over_limit > 0:
            t = self._tip("over_limit", over=_fmt(ds.over_limit))
            if t:
                out.append(t)
        elif ds.is_working_day:
            rem = ds.limit - ds.spent
            if rem > 0:
                t = self._tip("quota_left", remaining=_fmt(rem))
                if t:
                    out.append(t)
        burn_pct = (
            float(ms.total_burned / ms.total_entitlement * 100)
            if ms.total_entitlement > 0
            else 0.0
        )
        warn = float((self.cfg.get("coaching") or {}).get("month_burn_warn_pct", 25))
        if burn_pct >= warn:
            t = self._tip("month_burn", burned=_fmt(ms.total_burned), burn_pct=f"{burn_pct:.0f}")
            if t:
                out.append(t)
        if (self.cfg.get("dashboard") or {}).get("show_ndfl_estimate", False) and ms.total_ndfl > 0:
            t = self._tip("ndfl_month", ndfl=_fmt(ms.total_ndfl))
            if t and len(out) < 2:
                out.append(t)
        return out[:2]

    async def _llm_chat_coaching(self, user_content: str, ds: BadgeDayStats, ms: BadgeMonthStats, **extra: str) -> Optional[str]:
        llm_cfg = self.cfg.get("llm") or {}
        tpl = llm_cfg.get("after_spend_prompt") or ""
        if not tpl.strip():
            return None
        from ..llm import LLMClient

        client = LLMClient()
        if not client.api_key:
            return None
        rules = (self.cfg.get("rules_context") or "").strip()
        prompt = tpl.replace("{rules_context}", rules)
        prompt = prompt.replace("{daily_limit}", _fmt(self.daily_limit))
        prompt = prompt.replace("{ndfl_pct}", str(int(float(self.ndfl_rate) * 100)))
        for k, v in extra.items():
            prompt = prompt.replace("{" + k + "}", str(v))
        prompt = prompt.replace("{spent_today}", _fmt(ds.spent))
        prompt = prompt.replace("{over_today}", _fmt(ds.over_limit))
        prompt = prompt.replace("{spent_month}", _fmt(ms.total_spent))
        prompt = prompt.replace("{entitlement_month}", _fmt(ms.total_entitlement))
        prompt = prompt.replace("{burned_month}", _fmt(ms.total_burned))
        try:
            resp = await client.chat([
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ])
            return resp.strip() if resp else None
        except Exception:
            return None

    async def llm_coaching_after_spend(
        self,
        amount: Decimal,
        comment: Optional[str],
        ds: BadgeDayStats,
        ms: BadgeMonthStats,
    ) -> Optional[str]:
        if not (self.cfg.get("llm") or {}).get("after_spend_enabled"):
            return None
        return await self._llm_chat_coaching(
            dmsg("badge", "llm_after_spend_user"),
            ds,
            ms,
            amount=_fmt(amount),
            comment=(comment or dmsg("badge", "dash_none")).strip(),
        )

    def format_post_save_message(
        self,
        amount: Decimal,
        comment: Optional[str],
        ds: BadgeDayStats,
        ms: BadgeMonthStats,
        rule_tips: list[str],
        llm_tip: Optional[str],
    ) -> str:
        desc = f" ({comment})" if comment else ""
        lines = [
            fmsg("badge_recorded", amount=_fmt(amount), desc=desc),
            "",
            self.format_day_status(ds, ms),
        ]
        if rule_tips:
            lines.append("")
            lines.extend(f"💡 {t}" for t in rule_tips)
        if llm_tip:
            lines.append("")
            lines.append(f"🧠 {llm_tip}")
        hint = (self.cfg.get("ui") or {}).get("dashboard_hint")
        if hint:
            lines.append("")
            lines.append(f"📈 {hint}")
        return "\n".join(lines)

    def dashboard_where_hint(self) -> str:
        return str((self.cfg.get("ui") or {}).get("dashboard_hint") or "").strip()

    async def today_alert_text(self, session: AsyncSession, user_id: int) -> Optional[str]:
        today = date.today()
        if not self.is_working_day(today):
            return None
        acc = await self.get_or_create_badge_account(session, user_id)
        ds = await self.day_stats(session, user_id, today, acc.id)
        if ds.limit <= 0:
            return None
        pct = float(ds.spent / ds.limit * 100) if ds.limit else 100.0
        if pct >= (100 - self.burn_threshold_pct):
            return None
        remaining = ds.limit - ds.spent
        lines = [
            dmsg("badge", "today_alert_spent", spent=_fmt(ds.spent), limit=_fmt(ds.limit)),
            dmsg("badge", "today_alert_remaining", remaining=_fmt(remaining)),
        ]
        if ds.over_limit > 0:
            lines.append(dmsg("badge", "line_over_limit", amount=_fmt(ds.over_limit)))
        return "\n".join(lines)

    def format_day_status(self, ds: BadgeDayStats, month: Optional[BadgeMonthStats] = None) -> str:
        if not ds.is_working_day:
            return dmsg("badge", "day_off")
        lines = [dmsg("badge", "day_spent_line", spent=_fmt(ds.spent), limit=_fmt(ds.limit))]
        rem = ds.limit - ds.spent
        if rem > 0:
            lines.append(dmsg("badge", "day_remaining", remaining=_fmt(rem)))
        if ds.over_limit > 0:
            lines.append(dmsg("badge", "day_over", over=_fmt(ds.over_limit)))
        if month:
            lines.append(
                dmsg(
                    "badge",
                    "month_spent_line",
                    spent=_fmt(month.total_spent),
                    entitlement=_fmt(month.total_entitlement),
                    pct=month.utilization_pct,
                    burned=_fmt(month.total_burned),
                )
            )
        return "\n".join(lines)

    def format_month_summary(self, m: BadgeMonthStats) -> str:
        lines = [
            dmsg("badge", "month_title", month=m.month, year=m.year),
            dmsg(
                "badge",
                "month_working_days",
                working_days=m.working_days,
                days_with_spend=m.days_with_spend,
            ),
            dmsg(
                "badge",
                "month_spent_total",
                spent=_fmt(m.total_spent),
                entitlement=_fmt(m.total_entitlement),
                pct=m.utilization_pct,
            ),
            dmsg("badge", "month_burned", burned=_fmt(m.total_burned)),
        ]
        if self.cfg.get("dashboard", {}).get("show_ndfl_estimate", False):
            lines.append(dmsg("badge", "month_ndfl", ndfl=_fmt(m.total_ndfl)))
        if m.zero_spend_days:
            lines.append(dmsg("badge", "month_zero_days", days=m.zero_spend_days))
        if m.total_over_limit > 0:
            lines.append(dmsg("badge", "month_over_limit", over=_fmt(m.total_over_limit)))
        return "\n".join(lines)

    def month_stats_json(self, m: BadgeMonthStats) -> str:
        payload = {
            "year": m.year,
            "month": m.month,
            "working_days": m.working_days,
            "total_spent": float(m.total_spent),
            "total_burned": float(m.total_burned),
            "total_ndfl": float(m.total_ndfl),
            "utilization_pct": m.utilization_pct,
            "zero_spend_days": m.zero_spend_days,
        }
        return json.dumps(payload, ensure_ascii=False)


def _fmt(n: Decimal | float) -> str:
    v = float(n)
    if abs(v - round(v)) < 0.01:
        return f"{int(round(v)):,}".replace(",", " ")
    return f"{v:,.2f}".replace(",", " ")


def is_badge_account_name(name: str) -> bool:
    cfg = get_badge_config()
    if not cfg.get("enabled"):
        return False
    return name == str(cfg.get("account_name", "Meal Badge"))
