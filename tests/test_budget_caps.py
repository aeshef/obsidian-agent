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
    tr.note_memory_sizes(session_messages=4, working_set_items=3, core_priors_lines=2)
    assert tr.tool_clips and tr.cascade_escalate_reasons == ["verify"]
    assert tr.verify_ok is False
    assert tr.session_messages == 4


def test_unique_summary_omits_noise_moves():
    from planning_bot.services.activity_log_query import format_activity_events_block

    done = {
        "type": "task_completed",
        "timestamp": "2026-01-15 10:00:00",
        "data": {"title": "Ship docs", "task_id": "a1"},
    }
    noise = {
        "type": "task_moved",
        "timestamp": "2026-01-15 11:00:00",
        "data": {"title": "Noise A", "from": "WIP", "to": "Backlog", "task_id": "n1"},
    }
    entries = [done, noise]
    out = format_activity_events_block(
        entries,
        entries,
        n_raw=2,
        type_counts={"task_completed": 1, "task_moved": 1},
        filtered_type=None,
        period_start=date(2026, 1, 15),
        period_end=date(2026, 1, 15),
        summary="unique",
    )
    assert "Ship docs" in out
    assert "Noise A" not in out
    assert "уникальн" in out.casefold() or "Unique" in out
