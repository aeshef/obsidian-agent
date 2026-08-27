"""Budget caps: single-day policy, quantile recommend, clip stats."""
from __future__ import annotations

from datetime import date

from shared.agent.budget_caps import recommend_cap, resolve_activity_limit
from shared.agent.loop_context import clip_tool_result
from shared.agent.trace import AgentRunTrace


def test_single_day_auto_full_window():
    assert (
        resolve_activity_limit(
            requested=-1,
            from_date=date(2026, 1, 15),
            to_date=date(2026, 1, 15),
        )
        == 0
    )


def test_explicit_positive_limit():
    got = resolve_activity_limit(
        requested=50,
        from_date=date(2026, 1, 15),
        to_date=date(2026, 1, 15),
    )
    assert got == 50


def test_recommend_cap_quantile():
    got = recommend_cap(
        [1000, 2000, 4000, 8000, 16000, 16000],
        q=1.0,
        headroom=1.2,
        floor=1000,
        ceiling=100000,
    )
    assert 19000 <= got <= 19400


def test_clip_tool_result_stats():
    text, stats = clip_tool_result("x" * 100)
    assert stats["raw_chars"] == 100
    assert stats["llm_chars"] <= 100
    assert "clipped" in stats


def test_trace_records_clip_and_cascade():
    tr = AgentRunTrace(user_id=1, domain="unified", question_chars=3)
    tr.note_tool_clip(tool="get_action_log", stats={"raw_chars": 100, "llm_chars": 40, "clipped": True, "cap": 40})
    tr.note_cascade("verify")
    tr.note_verify(ok=False, rewrote=False)
    assert tr.tool_clips and tr.cascade_escalate_reasons == ["verify"]
    assert tr.verify_ok is False
