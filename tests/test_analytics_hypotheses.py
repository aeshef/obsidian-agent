"""Tests for sleep hypothesis engine."""
from __future__ import annotations

import numpy as np

from shared.analytics.hypotheses import fdr_bh, run_sleep_hypotheses, spearman_rho_p


def test_spearman_perfect_monotone():
    x = np.arange(20, dtype=float)
    y = x * 2 + 1
    rho, p, n = spearman_rho_p(x, y)
    assert n == 20
    assert rho > 0.99
    assert p < 0.001


def test_fdr_bh_orders():
    adj = fdr_bh([0.01, 0.04, 0.5])
    assert adj[0] <= adj[1] <= adj[2]


def test_run_sleep_hypotheses_finds_sleep_lag():
    n = 30
    sleep = np.linspace(6, 8, n)
    tasks = sleep * 2 + np.random.default_rng(0).normal(0, 0.1, n)
    panel = {
        "iphone_sleep_hours_lag1": np.concatenate([[np.nan], sleep[:-1]]),
        "tasks_completed": tasks,
    }
    outcomes = {"tasks_completed": {"label_key": "analytics_outcome_tasks"}}
    rows = run_sleep_hypotheses(
        panel,
        outcomes=outcomes,
        label_fn=lambda k: k,
        min_pairs=8,
        fdr_alpha=0.05,
    )
    assert rows
    assert rows[0]["sleep_feature"] == "sleep_hours"
    assert rows[0]["abs_rho"] > 0.5
