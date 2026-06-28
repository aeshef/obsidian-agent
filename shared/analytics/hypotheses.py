"""Sleep lag hypothesis engine — Spearman, partial Spearman, FDR."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy import stats


def spearman_rho_p(x: np.ndarray, y: np.ndarray) -> tuple[float, float, int]:
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 3:
        return float("nan"), float("nan"), n
    rho, p = stats.spearmanr(x[m], y[m])
    return float(rho), float(p), n


def fdr_bh(p_values: Sequence[float]) -> list[float]:
    """Benjamini–Hochberg adjusted p-values."""
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    if n == 0:
        return []
    order = np.argsort(p)
    ranked = np.empty(n, dtype=float)
    prev = 1.0
    for i in range(n - 1, -1, -1):
        idx = order[i]
        val = min(prev, p[idx] * n / (i + 1))
        ranked[idx] = val
        prev = val
    return ranked.tolist()


def partial_spearman(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> tuple[float, float, int]:
    sub = np.column_stack([x, y, z])
    m = np.all(np.isfinite(sub), axis=1)
    n = int(m.sum())
    if n < 8:
        return float("nan"), float("nan"), n
    xs = stats.rankdata(x[m])
    ys = stats.rankdata(y[m])
    zs = stats.rankdata(z[m])
    zc = np.column_stack([np.ones(n), zs])
    rx = xs - zc @ np.linalg.lstsq(zc, xs, rcond=None)[0]
    ry = ys - zc @ np.linalg.lstsq(zc, ys, rcond=None)[0]
    rho, p = stats.spearmanr(rx, ry)
    return float(rho), float(p), n


def _sleep_predictors(
    columns: Sequence[str],
    panel: Mapping[str, np.ndarray],
    min_pairs: int,
    extra: Sequence[str],
) -> list[str]:
    out: list[str] = []
    for col in columns:
        if not col.endswith("_lag1"):
            continue
        if "sleep" not in col.lower() and col not in extra:
            continue
        arr = panel.get(col)
        if arr is None:
            continue
        if int(np.isfinite(arr).sum()) < min_pairs:
            continue
        out.append(col)
    return sorted(out)


def run_sleep_hypotheses(
    panel: Mapping[str, np.ndarray],
    *,
    outcomes: Mapping[str, Mapping[str, str]],
    label_fn: Callable[[str], str],
    min_pairs: int = 8,
    extra_predictors: Sequence[str] = (),
    fdr_alpha: float = 0.05,
) -> list[dict[str, Any]]:
    columns = list(panel.keys())
    predictors = _sleep_predictors(columns, panel, min_pairs, extra_predictors)
    rows: list[dict[str, Any]] = []
    for slp in predictors:
        x = panel[slp]
        for out_col, spec in outcomes.items():
            y = panel.get(out_col)
            if y is None:
                continue
            rho, p, n = spearman_rho_p(x, y)
            if not np.isfinite(rho):
                continue
            label_key = str(spec.get("label_key") or out_col)
            rows.append(
                {
                    "sleep_feature": slp.replace("iphone_", "").replace("_lag1", ""),
                    "outcome": out_col,
                    "outcome_label": label_fn(label_key),
                    "n": n,
                    "spearman_rho": rho,
                    "p_value": p,
                    "abs_rho": abs(rho),
                }
            )
    if not rows:
        return rows
    p_fdr = fdr_bh([r["p_value"] for r in rows])
    for row, adj in zip(rows, p_fdr):
        row["p_fdr"] = adj
        row["significant_fdr"] = adj < fdr_alpha
        row["significant_05"] = row["p_value"] < 0.05
    rows.sort(key=lambda r: r["abs_rho"], reverse=True)
    return rows


def run_partial_weight_hypotheses(
    panel: Mapping[str, np.ndarray],
    *,
    predictors: Sequence[str],
    outcome: str,
    control: str,
    min_pairs: int = 8,
    fdr_alpha: float = 0.05,
) -> list[dict[str, Any]]:
    y = panel.get(outcome)
    z = panel.get(control)
    if y is None or z is None:
        return []
    rows: list[dict[str, Any]] = []
    for slp in predictors:
        x = panel.get(slp)
        if x is None:
            continue
        pr, pp, n = partial_spearman(x, y, z)
        if not np.isfinite(pr):
            continue
        rows.append(
            {
                "sleep_feature": slp.replace("iphone_", "").replace("_lag1", ""),
                "partial_rho": pr,
                "p_value": pp,
                "n": n,
                "abs_rho": abs(pr),
            }
        )
    if not rows:
        return rows
    p_fdr = fdr_bh([r["p_value"] for r in rows])
    for row, adj in zip(rows, p_fdr):
        row["p_fdr"] = adj
        row["significant_fdr"] = adj < fdr_alpha
    rows.sort(key=lambda r: r["abs_rho"], reverse=True)
    return rows
