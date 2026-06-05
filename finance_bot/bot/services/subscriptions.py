from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List
import yaml

from shared.domain_messages import dmsg

ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = ROOT / "config"


def _subscriptions_path() -> Path:
    p = _CONFIG_DIR / "subscriptions.yaml"
    if p.exists():
        return p
    example = _CONFIG_DIR / "subscriptions.yaml.example"
    if example.exists():
        return example
    return p


@dataclass
class Subscription:
    name: str
    amount: float
    currency: str
    period: str  # monthly|yearly
    next_charge: date


def load_subscriptions() -> List[Subscription]:
    path = _subscriptions_path()
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(dmsg("finance", "subscriptions_file_invalid", type=type(raw)))
    items: List[Subscription] = []
    for r in raw:
        items.append(
            Subscription(
                name=str(r.get("name")),
                amount=float(r.get("amount")),
                currency=str(r.get("currency", "RUB")),
                period=str(r.get("period", "monthly")),
                next_charge=datetime.fromisoformat(str(r.get("next_charge"))).date(),
            )
        )
    return items


def format_subscription_line(s: Subscription) -> str:
    return f"{s.name}: {s.amount:.2f} {s.currency} — {s.next_charge.isoformat()} ({s.period})"


def is_due_within(s: Subscription, days: int) -> bool:
    today = datetime.now().date()
    return today <= s.next_charge <= (today + timedelta(days=days))
