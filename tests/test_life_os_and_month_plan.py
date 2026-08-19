"""Unit tests for sleep debt, life OS scores, month plan."""
from datetime import date

from shared.analytics.sleep_debt import compute_sleep_debt_series
from shared.analytics.life_os_scores import compute_life_os_daily, classify_regime, REGIME_FLOW, REGIME_OVERREACH
from finance_bot.bot.services.month_plan import (
    PlanLine,
    build_month_plan,
    planned_for_month,
)


def test_sleep_debt_accumulates_and_decays():
    rows = [
        {"date": "2026-08-01", "iphone_sleep_hours": 8.0},
        {"date": "2026-08-02", "iphone_sleep_hours": 6.0},
        {"date": "2026-08-03", "iphone_sleep_hours": 6.0},
        {"date": "2026-08-04", "iphone_sleep_hours": 8.0},
    ]
    s = compute_sleep_debt_series(rows, target_hours=8.0, decay=0.9)
    assert s[0]["debt"] == 0.0
    assert s[1]["debt"] == 2.0
    assert s[2]["debt"] > s[1]["debt"]
    assert s[3]["debt"] < s[2]["debt"]
    assert not s[1]["missing"]


def test_sleep_debt_freezes_on_missing_days():
    rows = [
        {"date": "2026-08-01", "iphone_sleep_hours": 6.0},
        {"date": "2026-08-02", "iphone_sleep_hours": None},
        {"date": "2026-08-03", "iphone_sleep_hours": None},
        {"date": "2026-08-04", "iphone_sleep_hours": 6.0},
    ]
    s = compute_sleep_debt_series(rows, target_hours=8.0, decay=0.5)
    assert s[0]["debt"] == 2.0
    assert s[1]["missing"] is True
    assert s[1]["debt"] == s[0]["debt"]  # freeze, no decay
    assert s[2]["debt"] == s[1]["debt"]
    assert s[3]["debt"] > s[2]["debt"]


def test_deadline_blitz_uses_task_id_not_timeline_key():
    from datetime import datetime
    from planning_bot.services.kanban_flow_metrics import deadline_blitz_stats

    timelines = {
        "id:abcd1234": {
            "task_id": "abcd1234",
            "done_at": datetime(2026, 8, 10, 12, 0, 0),
        },
        "id:dead0000": {
            "task_id": "dead0000",
            "done_at": datetime(2026, 8, 12, 12, 0, 0),
        },
    }
    board = [
        {"task_id": "abcd1234", "deadline": "2026-08-10"},
        {"task_id": "dead0000", "deadline": "2026-08-10"},
    ]
    out = deadline_blitz_stats(timelines, board)
    assert out["counts"]["on_day"] == 1
    assert out["counts"]["late"] == 1
    assert out["counts"]["no_deadline"] == 0


def test_classify_regime_quadrants():
    assert classify_regime(70, 70, 40)["regime"] == REGIME_FLOW
    assert classify_regime(30, 70, 40)["regime"] == REGIME_OVERREACH
    assert classify_regime(70, 70, 80)["high_drain"] is True


def test_life_os_daily_runs():
    rows = [
        {
            "date": f"2026-08-{d:02d}",
            "iphone_sleep_hours": 7 + (d % 3) * 0.5,
            "sleep_debt": max(0, 3 - d * 0.2),
            "steps": 3000 + d * 200,
            "iphone_exercise_min": d,
            "tasks_completed": d % 5,
            "expense_rub": 500 + d * 10,
        }
        for d in range(1, 15)
    ]
    out = compute_life_os_daily(rows)
    assert len(out) == 14
    assert "capacity" in out[-1]
    assert out[-1]["regime"] in ("flow", "charge", "overreach", "recovery")


def test_month_plan_daily_allowance():
    snap = build_month_plan(
        ym="2026-08",
        today=date(2026, 8, 16),
        income_expected=100_000,
        subscriptions=[PlanLine("Sub", 5000, kind="subscription")],
        specifics=[PlanLine("Gift", 10000, kind="planned")],
        buffer_savings=5000,
        flexible_spent=20_000,
    )
    assert snap.commitment == 20_000
    assert snap.flexible_pool == 80_000
    assert snap.flexible_spent == 20_000
    assert snap.daily_allowance_remaining > 0
    assert snap.burn_pct == 25.0


def test_planned_for_month_filters():
    rows = [
        {"name": "A", "amount": 1, "due_date": "2026-08-01", "currency": "RUB"},
        {"name": "B", "amount": 2, "due_date": "2026-07-01", "currency": "RUB"},
        {"name": "C", "amount": 3, "due_date": None, "currency": "RUB"},
    ]
    got = planned_for_month(rows, "2026-08")
    names = {g.name for g in got}
    assert names == {"A", "C"}


def test_should_lapse_past_month_only():
    from finance_bot.bot.services.month_plan import (
        planned_upcoming,
        should_lapse_planned,
    )

    today = date(2026, 8, 16)
    assert should_lapse_planned(date(2026, 7, 1), today=today) is True
    assert should_lapse_planned(date(2026, 8, 1), today=today) is False
    assert should_lapse_planned(None, today=today) is False
    up = planned_upcoming(
        [
            {"name": "Soon", "amount": 10, "due_date": "2026-09-15", "currency": "RUB"},
            {"name": "Now", "amount": 5, "due_date": "2026-08-20", "currency": "RUB"},
        ],
        "2026-08",
    )
    assert [x[0].name for x in up] == ["Soon"]
