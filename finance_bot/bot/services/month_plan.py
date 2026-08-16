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
    live = _config_dir() / "subscriptions.yaml"
    if live.is_file():
        return live
    return _config_dir() / "subscriptions.yaml.example"


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


def month_expense_total(transactions: Sequence[dict[str, Any]], ym: str) -> float:
    total = 0.0
    for t in transactions:
        if str(t.get("type") or "") != "expense":
            continue
        if str(t.get("occurred_at") or "")[:7] != ym:
            continue
        try:
            total += float(t.get("amount") or 0)
        except (TypeError, ValueError):
            continue
    return total


def planned_for_month(
    planned_rows: Sequence[dict[str, Any]],
    ym: str,
) -> list[PlanLine]:
    """Filter planned_expenses active rows whose due_date falls in ym (or null → include)."""
    y, m = _parse_ym(ym)
    out: list[PlanLine] = []
    for p in planned_rows:
        due = p.get("due_date")
        if due:
            if isinstance(due, datetime):
                dd = due.date()
            elif isinstance(due, date):
                dd = due
            else:
                s = str(due)[:10]
                try:
                    dd = datetime.strptime(s, "%Y-%m-%d").date()
                except ValueError:
                    dd = None
            if dd is not None and (dd.year, dd.month) != (y, m):
                continue
        try:
            amount = float(p.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        name = str(p.get("name") or "").strip()
        if not name or amount <= 0:
            continue
        out.append(
            PlanLine(
                name=name,
                amount=round(amount, 2),
                currency=str(p.get("currency") or "RUB"),
                kind="planned",
                category=str(p.get("category") or ""),
            )
        )
    return out


def build_month_plan(
    *,
    ym: str,
    today: date,
    income_expected: float,
    subscriptions: Sequence[PlanLine],
    specifics: Sequence[PlanLine],
    inferred: Sequence[PlanLine] | None = None,
    buffer_savings: float = 0.0,
    flexible_spent: float = 0.0,
) -> MonthPlanSnapshot:
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
