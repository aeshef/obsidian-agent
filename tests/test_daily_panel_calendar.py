from planning_bot.services.daily_panel import _add_lags, _add_weight_next


def test_lag1_requires_previous_calendar_day():
    rows = [
        {"date": "2026-09-01", "x": 10},
        {"date": "2026-09-04", "x": 40},
    ]
    _add_lags(rows, ["x"])
    assert rows[0]["x_lag1"] is None
    assert rows[1]["x_lag1"] is None


def test_weight_delta_does_not_jump_across_missing_dates():
    rows = [
        {"date": "2026-09-01", "iphone_weight_kg": 70},
        {"date": "2026-09-03", "iphone_weight_kg": 71},
    ]
    _add_weight_next(rows)
    assert rows[0].get("iphone_weight_kg_next") is None
    assert rows[1]["iphone_weight_delta"] is None
