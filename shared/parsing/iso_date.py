"""Calendar day in ISO only — for tool parameters (no relative dates in code)."""
from __future__ import annotations

import re
from datetime import date


def parse_iso_calendar_day(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})", raw[:10])
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None
