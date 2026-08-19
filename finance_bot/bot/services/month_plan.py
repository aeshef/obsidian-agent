"""Month flexible spend plan: recurring + planned specifics → daily free-to-spend.

Composes existing pieces:
  - subscriptions.yaml (recurring)
  - planned_expenses rows for the month (month-specific)
  - optional inferred_recurring + buffer in month_plan.yaml / per-month JSON
  - actual consumption from transactions (caller supplies)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence


@dataclass
class PlanLine:
    name: str
    amount: float
    currency: str = "RUB"
    kind: str = "planned"  # subscription | inferred | planned | buffer
    category: str = ""


@dataclass
class MonthPlanSnapshot:
    year_month: str  # YYYY-MM
    income_expected: float
    recurring: list[PlanLine] = field(default_factory=list)
    specifics: list[PlanLine] = field(default_factory=list)
    buffer_savings: float = 0.0
    savings_rate_pct: float = 0.0
    commitment: float = 0.0
    flexible_pool: float = 0.0
    days_in_month: int = 30
    days_elapsed: int = 0
    days_left: int = 30
    flexible_spent: float = 0.0
    daily_allowance: float = 0.0
    daily_allowance_remaining: float = 0.0
    burn_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _parse_ym(ym: str) -> tuple[int, int]:
    y, m = ym.split("-", 1)
    return int(y), int(m)


def month_bounds(ym: str) -> tuple[date, date]:
    y, m = _parse_ym(ym)
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    from datetime import timedelta

    return start, end - timedelta(days=1)


def days_in_month(ym: str) -> int:
    start, end = month_bounds(ym)
    return (end - start).days + 1


def load_subscriptions(path: Path) -> list[PlanLine]:
    if not path.is_file():
        return []
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except Exception:
        return []
    out: list[PlanLine] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        try:
            amount = float(item.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if not name or amount <= 0:
            continue
        period = str(item.get("period") or "monthly").lower()
        # Only monthly-ish for month plan; weekly ≈ 4.3×
        if period.startswith("week"):
            amount *= 4.3
        elif period.startswith("year"):
            amount /= 12.0
        out.append(
            PlanLine(
                name=name,
                amount=round(amount, 2),
                currency=str(item.get("currency") or "RUB"),
                kind="subscription",
                category=str(item.get("category") or ""),
            )
        )
    return out


_BOT_ROOT = Path(__file__).resolve().parent.parent.parent


def _config_dir() -> Path:
    return _BOT_ROOT / "config"


def month_plan_config_path() -> Path:
    """Prefer live month_plan.yaml; fall back to .example."""
    live = _config_dir() / "month_plan.yaml"
    if live.is_file():
        return live
    return _config_dir() / "month_plan.yaml.example"


def subscriptions_yaml_path() -> Path:
    """Live subscriptions only — never fall back to .example (would invent charges)."""
    return _config_dir() / "subscriptions.yaml"


def load_month_plan_config(path: Path | None = None) -> dict[str, Any]:
    p = path or month_plan_config_path()
    if not p.is_file():
        return {}
    try:
        import yaml

        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def inferred_from_config(cfg: dict[str, Any] | None) -> list[PlanLine]:
    out: list[PlanLine] = []
    for x in (cfg or {}).get("inferred_recurring") or []:
        if not isinstance(x, dict):
            continue
        try:
            amount = float(x.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        name = str(x.get("name") or "").strip()
        if not name or amount <= 0:
            continue
        out.append(
            PlanLine(
                name=name,
                amount=round(amount, 2),
                kind="inferred",
                category=str(x.get("category") or ""),
            )
        )
    return out


def month_expense_total(
    transactions: Sequence[dict[str, Any]],
    ym: str,
    *,
    economic: bool = True,
) -> float:
    """Sum expenses for YYYY-MM.

    When ``economic`` (default), skips transfers / broker top-ups — those are
    not consumption. Pass ``economic=False`` for a raw ledger total.
    """
    from shared.finance_classification import is_consumption_expense

    total = 0.0
    for t in transactions:
        if str(t.get("occurred_at") or "")[:7] != ym:
            continue
        if economic:
            if not is_consumption_expense(t):
                continue
        elif str(t.get("type") or "") != "expense":
            continue
        try:
            total += float(t.get("amount") or 0)
        except (TypeError, ValueError):
            continue
    return total


@dataclass
class EconomicMonthSnapshot:
    """Month flows with salary-only income and reimbursement offsets."""

    ym: str
    salary_income: float
    consumption_gross: float
    reimbursements: float
    economic_spend: float  # max(0, gross − reimbursements)
    investments: float
    transfers_out: float
    by_category: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_economic_month(
    transactions: Sequence[dict[str, Any]],
    ym: str,
) -> EconomicMonthSnapshot:
    """Salary = earned; non-salary income (not transfers/broker) offsets spend."""
    from shared.finance_classification import (
        is_consumption_expense,
        is_investment_expense,
        is_internal_move_expense,
        is_reimbursement_offset,
        is_salary_income,
        txn_category,
        uncategorized_label,
    )

    salary = 0.0
    gross = 0.0
    offsets = 0.0
    investments = 0.0
    transfers = 0.0
    by_cat: dict[str, float] = {}

    for t in transactions:
        if str(t.get("occurred_at") or "")[:7] != ym:
            continue
        try:
            amt = float(t.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if is_salary_income(t):
            salary += amt
        if is_reimbursement_offset(t):
            offsets += amt
        if is_consumption_expense(t):
            gross += amt
            cat = txn_category(t) or uncategorized_label()
            by_cat[cat] = by_cat.get(cat, 0.0) + amt
        elif is_investment_expense(t) and str(t.get("type") or "") == "expense":
            # investment top-ups (not transfers)
            from shared.finance_classification import INVESTMENT_EXPENSE_CATEGORIES

            if txn_category(t) in INVESTMENT_EXPENSE_CATEGORIES:
                investments += amt
            elif is_internal_move_expense(t):
                transfers += amt
        elif is_internal_move_expense(t):
            transfers += amt

    economic = max(0.0, gross - offsets)
    return EconomicMonthSnapshot(
        ym=ym,
        salary_income=round(salary, 2),
        consumption_gross=round(gross, 2),
        reimbursements=round(offsets, 2),
        economic_spend=round(economic, 2),
        investments=round(investments, 2),
        transfers_out=round(transfers, 2),
        by_category={k: round(v, 2) for k, v in by_cat.items()},
    )


def soft_caps_from_config(cfg: dict[str, Any] | None) -> dict[str, float]:
    raw = (cfg or {}).get("soft_caps_rub") or {}
    out: dict[str, float] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        try:
            amt = float(v)
        except (TypeError, ValueError):
            continue
        name = str(k).strip()
        if name and amt > 0:
            out[name] = amt
    return out


def soft_cap_overages(
    by_category: dict[str, float],
    caps: dict[str, float],
) -> list[dict[str, Any]]:
    """Categories over comfort caps, largest overrun first."""
    rows: list[dict[str, Any]] = []
    for cat, cap in caps.items():
        spent = float(by_category.get(cat) or 0)
        if spent <= cap:
            continue
        rows.append(
            {
                "category": cat,
                "spent": round(spent, 0),
                "cap": round(cap, 0),
                "over": round(spent - cap, 0),
            }
        )
    rows.sort(key=lambda r: -float(r["over"]))
    return rows


def parse_due_date(value: Any) -> Optional[date]:
    """Normalize planned_expenses.due_date to a calendar date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def month_start(today: date) -> date:
    return date(today.year, today.month, 1)


def should_lapse_planned(due: Optional[date], *, today: date) -> bool:
    """True when a dated plan belongs to a past month (leave current month intact).

    Open-ended plans (no due_date) never auto-lapse — mark done/cancelled in the bot.
    """
    if due is None:
        return False
    return due < month_start(today)


def _plan_line_from_row(p: dict[str, Any]) -> Optional[PlanLine]:
    try:
        amount = float(p.get("amount") or 0)
    except (TypeError, ValueError):
        return None
    name = str(p.get("name") or "").strip()
    if not name or amount <= 0:
        return None
    return PlanLine(
        name=name,
        amount=round(amount, 2),
        currency=str(p.get("currency") or "RUB"),
        kind="planned",
        category=str(p.get("category") or ""),
    )


def planned_for_month(
    planned_rows: Sequence[dict[str, Any]],
    ym: str,
) -> list[PlanLine]:
    """Filter planned_expenses active rows whose due_date falls in ym (or null → include)."""
    y, m = _parse_ym(ym)
    out: list[PlanLine] = []
    for p in planned_rows:
        dd = parse_due_date(p.get("due_date"))
        if dd is not None and (dd.year, dd.month) != (y, m):
            continue
        line = _plan_line_from_row(p if isinstance(p, dict) else {})
        if line:
            out.append(line)
    return out


def planned_upcoming(
    planned_rows: Sequence[dict[str, Any]],
    ym: str,
) -> list[tuple[PlanLine, date]]:
    """Active plans with due_date in a future month (after ym)."""
    y, m = _parse_ym(ym)
    out: list[tuple[PlanLine, date]] = []
    for p in planned_rows:
        dd = parse_due_date(p.get("due_date"))
        if dd is None:
            continue
        if (dd.year, dd.month) <= (y, m):
            continue
        line = _plan_line_from_row(p if isinstance(p, dict) else {})
        if line:
            out.append((line, dd))
    out.sort(key=lambda x: x[1])
    return out


def lapse_past_planned_sqlite(
    conn: Any,
    *,
    today: date,
    user_id: Optional[int] = None,
) -> int:
    """Mark active dated plans from past months as expired. Returns rows updated."""
    import sqlite3

    if not hasattr(conn, "execute"):
        raise TypeError("conn must be a sqlite3 connection")
    cutoff = month_start(today).isoformat()
    try:
        if user_id is None:
            cur = conn.execute(
                """
                UPDATE planned_expenses
                SET status = 'expired'
                WHERE status = 'active'
                  AND due_date IS NOT NULL
                  AND date(due_date) < date(?)
                """,
                (cutoff,),
            )
        else:
            cur = conn.execute(
                """
                UPDATE planned_expenses
                SET status = 'expired'
                WHERE status = 'active'
                  AND user_id = ?
                  AND due_date IS NOT NULL
                  AND date(due_date) < date(?)
                """,
                (user_id, cutoff),
            )
        conn.commit()
        return int(cur.rowcount or 0)
    except sqlite3.OperationalError:
        return 0


async def lapse_past_planned_orm(session: Any, *, today: date, user_id: int) -> int:
    """Async ORM twin of lapse_past_planned_sqlite for bot handlers."""
    from sqlalchemy import select

    from bot.models import PlannedExpense

    rows = (
        await session.execute(
            select(PlannedExpense).where(
                PlannedExpense.user_id == user_id,
                PlannedExpense.status == "active",
                PlannedExpense.due_date.is_not(None),
            )
        )
    ).scalars().all()
    n = 0
    for p in rows:
        dd = parse_due_date(p.due_date)
        if should_lapse_planned(dd, today=today):
            p.status = "expired"
            n += 1
    if n:
        await session.commit()
    return n


@dataclass
class BalanceSafety:
    """Cash cushion vs invested capital — runway, not a daily spend budget.

    Broker / portfolio balances are capital. Dividing cash by days left in the
    month is *not* a safe allowance (that would liquidate the emergency fund).
    """

    cash_rub: float
    broker_rub: float
    essentials_monthly: float
    cash_after_dues: float
    runway_months: float
    emergency_target_months: float
    emergency_need: float
    emergency_gap: float
    month_dues: float  # planned one-offs still due this month

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Back-compat alias for older imports / caches
BalanceHeadroom = BalanceSafety


def resolve_savings_buffer(cfg: dict[str, Any] | None, income_expected: float) -> tuple[float, float]:
    """Pay-yourself-first buffer from cash-flow.

    Returns (buffer_rub, savings_rate_pct_used).
    Prefer ``savings_rate_pct`` when set; else absolute ``buffer_savings_rub``.
    """
    cfg = cfg or {}
    income = max(0.0, float(income_expected or 0))
    rate_raw = cfg.get("savings_rate_pct")
    try:
        rate = float(rate_raw) if rate_raw is not None and str(rate_raw).strip() != "" else None
    except (TypeError, ValueError):
        rate = None
    abs_raw = cfg.get("buffer_savings_rub")
    try:
        absolute = float(abs_raw) if abs_raw is not None else 0.0
    except (TypeError, ValueError):
        absolute = 0.0

    if rate is not None and rate > 0 and income > 0:
        buf = round(income * (rate / 100.0), 2)
        return buf, rate
    if absolute > 0 and income > 0:
        return round(absolute, 2), round(absolute / income * 100.0, 1)
    return max(0.0, round(absolute, 2)), float(rate or 0.0)


def compute_balance_safety(
    *,
    cash_rub: float,
    broker_rub: float = 0.0,
    planned: Sequence[PlanLine] | None = None,
    recurring: Sequence[PlanLine] | None = None,
    emergency_target_months: float = 3.0,
    month_spent: float = 0.0,
) -> BalanceSafety:
    """Cash runway in months of essentials — never a ₽/day burn of the cushion."""
    _ = month_spent  # kept for call-site compat / future burn tracking
    planned_sum = sum(float(x.amount) for x in (planned or []))
    essentials = sum(float(x.amount) for x in (recurring or []))
    cash = float(cash_rub or 0)
    # Near-term dues only (this month's one-offs). Do NOT subtract the savings
    # transfer goal from cash here — that goal is a flow into broker, not rent.
    dues = planned_sum
    after = cash - dues
    target_m = max(0.0, float(emergency_target_months or 0))
    need = essentials * target_m
    runway = (after / essentials) if essentials > 0 else 0.0
    gap = max(0.0, need - max(0.0, after))
    return BalanceSafety(
        cash_rub=round(cash, 2),
        broker_rub=round(float(broker_rub or 0), 2),
        essentials_monthly=round(essentials, 2),
        cash_after_dues=round(after, 2),
        runway_months=round(runway, 2),
        emergency_target_months=round(target_m, 2),
        emergency_need=round(need, 2),
        emergency_gap=round(gap, 2),
        month_dues=round(dues, 2),
    )


def compute_balance_headroom(
    *,
    spendable_rub: float,
    broker_rub: float = 0.0,
    planned: Sequence[PlanLine] | None = None,
    recurring: Sequence[PlanLine] | None = None,
    buffer_savings: float = 0.0,
    days_left: int = 1,
    month_spent: float = 0.0,
    emergency_target_months: float = 3.0,
) -> BalanceSafety:
    """Deprecated name — use compute_balance_safety. Ignores buffer/days burn."""
    _ = buffer_savings
    _ = days_left
    return compute_balance_safety(
        cash_rub=spendable_rub,
        broker_rub=broker_rub,
        planned=planned,
        recurring=recurring,
        emergency_target_months=emergency_target_months,
        month_spent=month_spent,
    )


def build_month_plan(
    *,
    ym: str,
    today: date,
    income_expected: float,
    subscriptions: Sequence[PlanLine],
    specifics: Sequence[PlanLine],
    inferred: Sequence[PlanLine] | None = None,
    buffer_savings: float = 0.0,
    savings_rate_pct: float = 0.0,
    flexible_spent: float = 0.0,
) -> MonthPlanSnapshot:
    """Cash-flow plan: income − fixed − pay-yourself-first → daily life budget.

    ``daily_*`` is only from this income pool — never from cash balance / broker.
    """
    start, end = month_bounds(ym)
    dim = (end - start).days + 1
    if today < start:
        elapsed, left = 0, dim
    elif today > end:
        elapsed, left = dim, 0
    else:
        elapsed = (today - start).days + 1
        left = dim - elapsed + 1  # include today in remaining allowance days
        left = max(1, left)

    recurring = list(subscriptions) + list(inferred or [])
    commitment = (
        sum(x.amount for x in recurring)
        + sum(x.amount for x in specifics)
        + float(buffer_savings or 0)
    )
    flexible = float(income_expected) - commitment
    spent = max(0.0, float(flexible_spent or 0))
    remaining_pool = flexible - spent
    daily = remaining_pool / left if left > 0 else 0.0
    # Today's fair share of original pool
    fair_daily = flexible / dim if dim > 0 else 0.0
    burn = (spent / flexible * 100.0) if flexible > 0 else 0.0

    return MonthPlanSnapshot(
        year_month=ym,
        income_expected=round(float(income_expected), 2),
        recurring=list(recurring),
        specifics=list(specifics),
        buffer_savings=round(float(buffer_savings or 0), 2),
        savings_rate_pct=round(float(savings_rate_pct or 0), 1),
        commitment=round(commitment, 2),
        flexible_pool=round(flexible, 2),
        days_in_month=dim,
        days_elapsed=elapsed,
        days_left=left,
        flexible_spent=round(spent, 2),
        daily_allowance=round(fair_daily, 2),
        daily_allowance_remaining=round(daily, 2),
        burn_pct=round(burn, 1),
    )
