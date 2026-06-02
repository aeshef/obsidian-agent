"""Calendar sync + cross-domain routing helpers."""
from __future__ import annotations

from planning_bot.tools.calendar_sync import _extract_txt_timestamp
from shared.agent.cross_domain import cross_domain_score, needs_unified_agent


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


def test_needs_unified_for_finance_and_health():
    q = "Расходы за последние 14 дней и средние шаги за те же дни"
    assert cross_domain_score(q) >= 2
    assert needs_unified_agent(q) is True


def test_planning_only_not_unified():
    q = "Сколько встреч завтра и что в колонке В работе"
    assert needs_unified_agent(q) is False
