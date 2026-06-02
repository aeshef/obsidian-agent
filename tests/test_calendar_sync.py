"""Calendar sync structural parsing (append-only export blocks)."""
from __future__ import annotations

from planning_bot.tools.calendar_sync import _extract_txt_timestamp


def test_extract_txt_timestamp_uses_last_export_block():
    txt = """---
23 Apr 2026 at 17:52
---
24.04.2026 10:45 - 11:00 Meet
---
2 Jun 2026 at 03:19
---
03.06.2026 10:45 - 11:00 Летучка
"""
    assert _extract_txt_timestamp(txt) == "2026-06-02T03:19:00"
