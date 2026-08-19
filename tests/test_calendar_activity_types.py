"""Calendar activity types: LLM labels on events + attention weights (no needles)."""
from __future__ import annotations

from datetime import date
from typing import Any

from planning_bot.services.calendar_analytics import (
    activity_signature,
    attention_weight_for,
    classify_activity,
    clear_activity_config_cache,
    compute_week_analytics,
    daily_meeting_hours_series,
    is_calendar_block,
)


def setup_function():
    clear_activity_config_cache()


def _ev(**kwargs: Any) -> dict:
    base = {
        "id": "e1",
        "title": "",
        "tag": None,
        "start": "10:00",
        "end": "11:00",
        "is_allday": False,
        "is_cancelled": False,
    }
    base.update(kwargs)
    if "activity_type" in base and "activity_sig" not in kwargs:
        base["activity_sig"] = activity_signature(base)
    return base


def test_classify_reads_llm_label():
    assert classify_activity(_ev(title="Gym", activity_type="здоровье")) == "здоровье"
    assert classify_activity(_ev(title="Tech screen", activity_type="собесы")) == "собесы"
    assert classify_activity(_ev(title="Quorum", activity_type="работа")) == "работа"


def test_classify_unknown_or_stale_falls_back_to_default():
    assert classify_activity(_ev(title="Anything")) == "прочее"
    assert classify_activity(_ev(title="x", activity_type="not-a-type")) == "прочее"
    stale = _ev(title="A", activity_type="работа", activity_sig="old|")
    assert classify_activity(stale) == "прочее"


def test_block_via_empty_title_or_llm_type():
    assert is_calendar_block(_ev(title="")) is True
    assert is_calendar_block(_ev(title="Focus", activity_type="блок")) is True
    assert is_calendar_block(_ev(title="1:1", activity_type="работа")) is False


def test_attention_uses_type_weight():
    interview = _ev(title="Interview", activity_type="собесы")
    work = _ev(title="Sync", activity_type="работа")
    assert attention_weight_for(interview) == 1.0
    assert attention_weight_for(work) == 0.45


def test_week_has_activity_and_attention():
    ev = [
        {
            "id": "a",
            "date": "2026-06-01",
            "start": "10:00",
            "end": "11:00",
            "title": "Interview",
            "activity_type": "собесы",
            "activity_sig": activity_signature({"title": "Interview", "tag": None}),
            "is_allday": False,
            "is_cancelled": False,
        },
        {
            "id": "b",
            "date": "2026-06-01",
            "start": "12:00",
            "end": "13:00",
            "title": "ML Sync",
            "activity_type": "работа",
            "activity_sig": activity_signature({"title": "ML Sync", "tag": None}),
            "is_allday": False,
            "is_cancelled": False,
        },
    ]
    a = compute_week_analytics(ev, date(2026, 6, 1), horizon_days=1)
    assert a["days"][0]["meeting_minutes"] == 120
    assert "собесы" in a["activity_hours"]
    assert "работа" in a["activity_hours"]
    assert a["totals"]["attention_hours"] < a["totals"]["invite_hours"]
    assert a["signals"]
    assert a["top_pressure"]


def test_daily_series_attention_key():
    ev = [
        {
            "id": "c",
            "date": "2026-06-01",
            "start": "10:00",
            "end": "12:00",
            "title": "Interview",
            "activity_type": "собесы",
            "activity_sig": activity_signature({"title": "Interview", "tag": None}),
            "is_allday": False,
            "is_cancelled": False,
        }
    ]
    s = daily_meeting_hours_series(ev, start=date(2026, 6, 1), end=date(2026, 6, 1))
    assert s["2026-06-01"]["invite_hours"] == 2.0
    assert s["2026-06-01"]["meeting_hours"] == 2.0


def test_ensure_activity_types_calls_llm(monkeypatch):
    from planning_bot.services import calendar_activity_classify as cac

    async def fake_llm(events, *, taxonomy, allowed):
        assert "работа" in allowed or "прочее" in allowed
        assert taxonomy
        return {str(events[0]["id"]): "здоровье"}

    monkeypatch.setattr(cac, "classify_calendar_activities_llm", fake_llm)
    events = [{"id": "z1", "title": "Gym", "tag": None}]
    out, n = cac.ensure_activity_types(events)
    assert n == 1
    assert out[0]["activity_type"] == "здоровье"
    assert out[0]["activity_sig"] == activity_signature(out[0])
    assert classify_activity(out[0]) == "здоровье"


def test_ensure_skips_cached(monkeypatch):
    from planning_bot.services import calendar_activity_classify as cac

    called = {"n": 0}

    async def fake_llm(*_a, **_k):
        called["n"] += 1
        return {}

    monkeypatch.setattr(cac, "classify_calendar_activities_llm", fake_llm)
    ev = _ev(id="cached", title="Gym", activity_type="здоровье")
    _, n = cac.ensure_activity_types([ev])
    assert n == 0
    assert called["n"] == 0


def test_dashboard_render_smoke():
    from planning_bot.core.pdmsg import pdmsg
    from planning_bot.services.calendar_dashboard import render_meeting_focus_dashboard
    from shared.domain_messages import clear_domain_messages_cache

    clear_domain_messages_cache()
    ev = [
        {
            "id": "d1",
            "date": "2026-06-01",
            "start": "10:00",
            "end": "12:00",
            "title": "Interview",
            "activity_type": "собесы",
            "activity_sig": activity_signature({"title": "Interview", "tag": None}),
            "is_allday": False,
            "is_cancelled": False,
        },
        {
            "id": "d2",
            "date": "2026-06-02",
            "start": "14:00",
            "end": "15:00",
            "title": "ML Sync",
            "activity_type": "работа",
            "activity_sig": activity_signature({"title": "ML Sync", "tag": None}),
            "is_allday": False,
            "is_cancelled": False,
        },
    ]
    a = compute_week_analytics(ev, date(2026, 6, 1), horizon_days=2)
    md = render_meeting_focus_dashboard("2026-06-01T12:00:00", a, "ignored llm")
    assert pdmsg("calendar_dash_hero_open") in md
    assert pdmsg("calendar_dash_upcoming_title") in md
    assert pdmsg("calendar_dash_section_rhythms") not in md
    assert "invite" not in md.lower()
    assert "×0.45" not in md
    assert "_sync" not in md
    assert a.get("free_windows") is not None
    assert a.get("upcoming")
    # List rows stay inside the callout (Obsidian), not as naked markdown below it.
    assert "> - **" in md
