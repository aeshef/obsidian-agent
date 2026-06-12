"""Time-series helpers for dashboard charts (sparse / invalid values)."""
from __future__ import annotations

import numpy as np

# Treat as missing — not zero on chart.
_INVALID_RULES: dict[str, tuple[float, float | None]] = {
    "resting_hr_bpm": (25.0, 220.0),
    "hrv_ms": (1.0, None),
    "weight_kg": (35.0, 250.0),
    "steps": (1.0, None),
    "calories_kcal": (1.0, None),
    "active_calories_kcal": (1.0, None),
    "kcal_macros": (1.0, None),
}


def sanitize_metric(key: str, value: object) -> float:
    if value is None:
        return float("nan")
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float("nan")
    if not np.isfinite(v):
        return float("nan")
    rule = _INVALID_RULES.get(key)
    if rule:
        lo, hi = rule
        if v < lo:
            return float("nan")
        if hi is not None and v > hi:
            return float("nan")
    return v


def rolling_mean(y: np.ndarray, window: int) -> np.ndarray:
    """Centered rolling mean; NaN where fewer than half the window has data."""
    out = np.full_like(y, np.nan, dtype=float)
    n = len(y)
    if n == 0 or window < 1:
        return out
    half = max(1, window // 2)
    min_pts = max(2, window // 2)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = y[lo:hi]
        chunk = chunk[np.isfinite(chunk)]
        if len(chunk) >= min_pts:
            out[i] = float(np.mean(chunk))
    return out


def ols_trend_masked(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Linear trend only over finite y; NaN elsewhere (no edge extrapolation)."""
    out = np.full_like(y, np.nan, dtype=float)
    mask = np.isfinite(y)
    if mask.sum() < 3:
        return out
    idx = np.where(mask)[0].astype(float)
    coef = np.polyfit(idx, y[mask], 1)
    out[mask] = np.polyval(coef, idx)
    return out
