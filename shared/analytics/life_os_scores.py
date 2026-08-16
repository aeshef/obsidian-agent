"""Life OS composite scores: Capacity / Output / Drain + regime label.

Scores are 0–100, normalized to the personal rolling window (percentile ranks),
then combined with configurable weights. Regime is a 2×2 of Capacity×Output
with Drain as a modifier flag — not a black-box average.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np


REGIME_FLOW = "flow"
REGIME_CHARGE = "charge"
REGIME_OVERREACH = "overreach"
REGIME_RECOVERY = "recovery"

DEFAULT_WEIGHTS = {
    "capacity": {
        "sleep_hours": 0.35,
        "sleep_debt_inv": 0.30,
        "steps": 0.20,
        "exercise_min": 0.15,
    },
    "output": {
        "tasks_completed": 0.55,
        "goal_mapped_completions": 0.45,
    },
    "drain": {
        "expense_rub": 0.40,
        "flow_debt_delta": 0.35,
        "meeting_hours": 0.25,
    },
}


def _finite(a: np.ndarray) -> np.ndarray:
    return a[np.isfinite(a)]


def _percentile_rank(series: np.ndarray, value: float) -> float:
    """Empirical CDF rank of value in series → 0..100. Empty → 50."""
    clean = _finite(series)
    if clean.size == 0 or not np.isfinite(value):
        return 50.0
    # Mid-rank percentile
    return float(100.0 * (np.sum(clean <= value) / clean.size))


def _inv_percentile_rank(series: np.ndarray, value: float) -> float:
    """Higher is better when lower raw values are better (debt, spend)."""
    return 100.0 - _percentile_rank(series, value)


def _col(rows: Sequence[dict], key: str) -> np.ndarray:
    out = []
    for r in rows:
        v = r.get(key)
        try:
            out.append(float(v) if v is not None else np.nan)
        except (TypeError, ValueError):
            out.append(np.nan)
    return np.asarray(out, dtype=float)


def _weighted_score(parts: dict[str, float], weights: dict[str, float]) -> float:
    num = 0.0
    den = 0.0
    for k, w in weights.items():
        if k not in parts:
            continue
        ww = float(w)
        if ww <= 0:
            continue
        num += parts[k] * ww
        den += ww
    if den <= 0:
        return 50.0
    return float(np.clip(num / den, 0.0, 100.0))


def classify_regime(
    capacity: float,
    output: float,
    drain: float,
    *,
    mid: float = 50.0,
    high_drain: float = 65.0,
) -> dict[str, Any]:
    cap_hi = capacity >= mid
    out_hi = output >= mid
    if cap_hi and out_hi:
        regime = REGIME_FLOW
    elif cap_hi and not out_hi:
        regime = REGIME_CHARGE
    elif not cap_hi and out_hi:
        regime = REGIME_OVERREACH
    else:
        regime = REGIME_RECOVERY
    return {
        "regime": regime,
        "high_drain": bool(drain >= high_drain),
        "capacity": round(capacity, 1),
        "output": round(output, 1),
        "drain": round(drain, 1),
    }


def compute_life_os_daily(
    rows: Sequence[dict[str, Any]],
    *,
    weights: dict[str, dict[str, float]] | None = None,
    sleep_debt_key: str = "sleep_debt",
    goal_mapped_key: str = "goal_mapped_completions",
    meeting_key: str = "meeting_hours",
    flow_debt_delta_key: str = "flow_debt_delta",
    mid: float = 50.0,
    high_drain: float = 65.0,
) -> list[dict[str, Any]]:
    """Build per-day Capacity/Output/Drain scores and regime labels.

    Missing component columns are skipped in the weighted average for that day.
    Percentile ranks use the full window (personal baseline).
    """
    if not rows:
        return []
    w = weights or DEFAULT_WEIGHTS
    n = len(rows)
    dates = [str(r.get("date") or "")[:10] for r in rows]

    sleep = _col(rows, "iphone_sleep_hours")
    debt = _col(rows, sleep_debt_key)
    steps = _col(rows, "steps")
    if not np.isfinite(steps).any():
        steps = _col(rows, "iphone_steps")
    exercise = _col(rows, "iphone_exercise_min")
    tasks = _col(rows, "tasks_completed")
    goals = _col(rows, goal_mapped_key)
    expense = _col(rows, "expense_rub")
    meetings = _col(rows, meeting_key)
    flow_d = _col(rows, flow_debt_delta_key)

    out: list[dict[str, Any]] = []
    for i in range(n):
        cap_parts: dict[str, float] = {}
        if np.isfinite(sleep[i]):
            cap_parts["sleep_hours"] = _percentile_rank(sleep, float(sleep[i]))
        if np.isfinite(debt[i]):
            cap_parts["sleep_debt_inv"] = _inv_percentile_rank(debt, float(debt[i]))
        if np.isfinite(steps[i]):
            cap_parts["steps"] = _percentile_rank(steps, float(steps[i]))
        if np.isfinite(exercise[i]):
            cap_parts["exercise_min"] = _percentile_rank(exercise, float(exercise[i]))

        out_parts: dict[str, float] = {}
        if np.isfinite(tasks[i]):
            out_parts["tasks_completed"] = _percentile_rank(tasks, float(tasks[i]))
        if np.isfinite(goals[i]):
            out_parts["goal_mapped_completions"] = _percentile_rank(goals, float(goals[i]))

        drain_parts: dict[str, float] = {}
        if np.isfinite(expense[i]):
            # High spend → high drain score
            drain_parts["expense_rub"] = _percentile_rank(expense, float(expense[i]))
        if np.isfinite(flow_d[i]):
            drain_parts["flow_debt_delta"] = _percentile_rank(flow_d, float(flow_d[i]))
        if np.isfinite(meetings[i]):
            drain_parts["meeting_hours"] = _percentile_rank(meetings, float(meetings[i]))

        capacity = _weighted_score(cap_parts, w.get("capacity") or {})
        output = _weighted_score(out_parts, w.get("output") or {})
        drain = _weighted_score(drain_parts, w.get("drain") or {})
        regime = classify_regime(capacity, output, drain, mid=mid, high_drain=high_drain)
        row_out: dict[str, Any] = {
            "date": dates[i],
            **regime,
            "components": {
                "capacity": cap_parts,
                "output": out_parts,
                "drain": drain_parts,
            },
        }
        if np.isfinite(debt[i]):
            row_out["sleep_debt"] = round(float(debt[i]), 2)
        out.append(row_out)
    return out
