"""Base currency helpers (BASE_CURRENCY env; default RUB for backward compat)."""
from __future__ import annotations

import os


def base_currency(*, override: str | None = None) -> str:
    raw = (override or os.environ.get("BASE_CURRENCY") or "RUB").strip().upper()
    return raw or "RUB"


def currency_aliases(code: str | None = None) -> frozenset[str]:
    """Codes treated as the same unit (RUB ↔ RUR when base is RUB)."""
    c = base_currency(override=code)
    if c in ("RUB", "RUR"):
        return frozenset({"RUB", "RUR"})
    return frozenset({c})


def is_base_currency(code: str | None) -> bool:
    c = (code or "").strip().upper()
    if not c:
        return False
    return c in currency_aliases()
