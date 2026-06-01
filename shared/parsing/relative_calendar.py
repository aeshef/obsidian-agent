"""Relative dates from text — scripts/legacy only, not for agent tools."""
from __future__ import annotations

import re
import warnings
from datetime import date, timedelta

from shared.domain_messages import dmsg


def resolve_calendar_day_from_text(text: str, *, today: date) -> date | None:
    """ISO YYYY-MM-DD or relative phrases. Do not call from agent loop."""
    warnings.warn(
        "resolve_calendar_day_from_text: legacy/scripts only; agent must pass day=YYYY-MM-DD",
        DeprecationWarning,
        stacklevel=2,
    )
    raw = text or ""
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", raw)
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    low = raw.lower()
    days_ago = dmsg("relative_calendar", "days_ago")
    if days_ago:
        rel = re.search(days_ago, low)
        if rel:
            return today - timedelta(days=int(rel.group(1)))
    yesterday = dmsg("relative_calendar", "yesterday")
    if yesterday and re.search(yesterday, low):
        return today - timedelta(days=1)
    day_before = dmsg("relative_calendar", "day_before_yesterday")
    if day_before and re.search(day_before, low):
        return today - timedelta(days=2)
    return None
