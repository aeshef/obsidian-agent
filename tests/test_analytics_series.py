"""Tests for sparse health metric handling."""
from __future__ import annotations

import numpy as np

from shared.analytics.series import ols_trend_masked, rolling_mean, sanitize_metric


def test_zero_resting_hr_is_missing():
    assert np.isnan(sanitize_metric("resting_hr_bpm", 0))


def test_rolling_mean_skips_nan_edges():
    y = np.array([np.nan, np.nan, 10.0, 12.0, 11.0, np.nan, np.nan])
    roll = rolling_mean(y, 3)
    assert np.isnan(roll[0])
    assert np.isfinite(roll[3])


def test_ols_trend_no_extrapolation():
    x = np.arange(10, dtype=float)
    y = np.array([np.nan] * 4 + [70.0, 71.0, 72.0, 73.0, 74.0, np.nan])
    trend = ols_trend_masked(x, y)
    assert np.isnan(trend[0])
    assert np.isfinite(trend[5])
    assert np.isnan(trend[-1])
