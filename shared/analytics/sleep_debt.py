"""Sleep debt series from daily sleep hours (Sahha-style accumulator).

Missing / unparsed sleep days do NOT change the debt (freeze) — gaps must not
quietly heal or inflate the metric.
"""
from __future__ import annotations

from typing import Any, Sequence


def compute_sleep_debt_series(
    rows: Sequence[dict[str, Any]],
    *,
    sleep_key: str = "iphone_sleep_hours",
    target_hours: float = 8.0,
    decay: float = 0.9,
    date_key: str = "date",
) -> list[dict[str, Any]]:
    """Return [{date, sleep_hours, debt, surplus, missing}].

    When sleep is known:
      debt_t = max(0, decay * debt_{t-1} + (target - sleep_t))
    When sleep is missing/invalid:
      debt_t = debt_{t-1} (freeze; no decay, no shortfall)
    """
    target = float(target_hours)
    dcy = min(1.0, max(0.0, float(decay)))
    debt = 0.0
    out: list[dict[str, Any]] = []
    for r in rows:
        day = str(r.get(date_key) or "")[:10]
        raw = r.get(sleep_key)
        sleep_h: float | None
        try:
            sleep_h = float(raw) if raw is not None else None
            if sleep_h is not None and not (0.0 <= sleep_h <= 24.0):
                sleep_h = None
        except (TypeError, ValueError):
            sleep_h = None

        if sleep_h is None:
            surplus = 0.0
            missing = True
            # freeze — do not decay or add gap
        else:
            gap = target - sleep_h
            debt = max(0.0, dcy * debt + gap)
            surplus = max(0.0, sleep_h - target)
            missing = False

        out.append(
            {
                "date": day,
                "sleep_hours": sleep_h,
                "debt": round(debt, 3),
                "surplus": round(surplus, 3),
                "target_hours": target,
                "missing": missing,
            }
        )
    return out


def sleep_debt_today(series: Sequence[dict[str, Any]]) -> float | None:
    if not series:
        return None
    # Prefer last day with known sleep; else last frozen value
    for row in reversed(series):
        if row.get("missing"):
            continue
        try:
            return float(row.get("debt"))
        except (TypeError, ValueError):
            continue
    last = series[-1]
    try:
        return float(last.get("debt"))
    except (TypeError, ValueError):
        return None
