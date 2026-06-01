"""Parse dates from machine strings (formats from config + dateutil)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Sequence

from dateutil import parser as date_parser


def parse_datetime(
    raw: str,
    *,
    strptime_formats: Sequence[str] = (),
) -> Optional[datetime]:
    s = (raw or "").strip().strip("{}")
    s = s.replace(chr(0x00A0), " ").replace(chr(0x202F), " ")
    if not s:
        return None
    for fmt in strptime_formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return date_parser.parse(s, dayfirst=True)
    except (ValueError, TypeError, OverflowError):
        return None
