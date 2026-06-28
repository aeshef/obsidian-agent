"""Matplotlib charts from master daily panel."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from shared.analytics.series import rolling_mean
from shared.chart_paths import ensure_parent


def _mpl():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _dates(rows: Sequence[dict]) -> list[str]:
    return [str(r.get("date", "")) for r in rows]


def _col(rows: Sequence[dict], key: str) -> np.ndarray:
    out = []
    for r in rows:
        v = r.get(key)
        if v is None:
            out.append(np.nan)
        else:
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                out.append(np.nan)
    return np.asarray(out, dtype=float)


def _spearman_matrix(keys: list[str], cols: dict[str, np.ndarray], min_pairs: int) -> tuple[list[str], np.ndarray]:
    from shared.analytics.hypotheses import spearman_rho_p

    n = len(keys)
    mat = np.full((n, n), np.nan)
    for i, a in enumerate(keys):
        for j, b in enumerate(keys):
            if j < i:
                continue
            rho, _, cnt = spearman_rho_p(cols[a], cols[b])
            if cnt >= min_pairs and np.isfinite(rho):
                mat[i, j] = mat[j, i] = rho
            elif i == j:
                mat[i, j] = 1.0
    return keys, mat


def chart_weight_trend(rows: Sequence[dict], png_path: Path, *, title: str) -> bool:
    y = _col(rows, "iphone_weight_kg")
    if int(np.isfinite(y).sum()) < 5:
        return False
    plt = _mpl()
    dates = _dates(rows)
    x = np.arange(len(dates))
    roll = rolling_mean(y, 7)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(x, y, "o", color="#90a4ae", markersize=4, alpha=0.6, label="daily")
    ax.plot(x, roll, color="#1565c0", linewidth=2, label="7d MA")
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("kg")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    step = max(1, len(dates) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([dates[i][5:] for i in range(0, len(dates), step)], rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_sleep_hours(rows: Sequence[dict], png_path: Path, *, title: str) -> bool:
    y = _col(rows, "iphone_sleep_hours")
    if int(np.isfinite(y).sum()) < 5:
        return False
    plt = _mpl()
    dates = _dates(rows)
    x = np.arange(len(dates))
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(x, y, color="#5c6bc0", alpha=0.75, width=0.85)
    ax.axhline(float(np.nanmean(y)), color="#ef5350", linestyle="--", linewidth=1, label=f"mean={np.nanmean(y):.1f}h")
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("hours")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25, axis="y")
    step = max(1, len(dates) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([dates[i][5:] for i in range(0, len(dates), step)], rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_sleep_stages(rows: Sequence[dict], png_path: Path, *, title: str) -> bool:
    stage_keys = (
        "iphone_sleep_deep_min",
        "iphone_sleep_rem_min",
        "iphone_sleep_core_min",
        "iphone_sleep_awake_min",
    )
    cols = {k: _col(rows, k) for k in stage_keys}
    if sum(int(np.isfinite(c).sum()) for c in cols.values()) < 5:
        return False
    plt = _mpl()
    dates = _dates(rows)
    x = np.arange(len(dates))
    fig, ax = plt.subplots(figsize=(10, 4.5))
    bottom = np.zeros(len(dates))
    colors = ("#283593", "#7e57c2", "#9575cd", "#b0bec5")
    labels = ("Deep", "REM", "Core", "Awake")
    for key, color, label in zip(stage_keys, colors, labels):
        vals = np.where(np.isfinite(cols[key]), cols[key], 0.0)
        ax.bar(x, vals, bottom=bottom, color=color, alpha=0.85, width=0.85, label=label)
        bottom = bottom + vals
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("minutes")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.25, axis="y")
    step = max(1, len(dates) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([dates[i][5:] for i in range(0, len(dates), step)], rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_sleep_weight_scatter(rows: Sequence[dict], png_path: Path, *, title: str, min_pairs: int = 8) -> bool:
    x = _col(rows, "iphone_sleep_hours_lag1")
    y = _col(rows, "iphone_weight_delta_next")
    m = np.isfinite(x) & np.isfinite(y)
    if int(m.sum()) < min_pairs:
        return False
    from shared.analytics.hypotheses import spearman_rho_p

    rho, p, n = spearman_rho_p(x, y)
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.scatter(x[m], y[m], alpha=0.6, s=36, c="#455a64", edgecolors="white", linewidths=0.4)
    ax.axhline(0, color="#999", linewidth=0.8, linestyle=":")
    ax.set_xlabel("sleep hours (D−1)")
    ax.set_ylabel("Δ weight next day (kg)")
    subtitle = f"ρ={rho:.2f}, p={p:.3f}, n={n}" if np.isfinite(rho) else ""
    ax.set_title(f"{title}\n{subtitle}" if subtitle else title, fontsize=10)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_panel_correlations(
    rows: Sequence[dict],
    png_path: Path,
    *,
    keys: Sequence[str],
    labels: Sequence[str],
    title: str,
    min_pairs: int,
) -> bool:
    cols = {k: _col(rows, k) for k in keys}
    valid_keys = [k for k in keys if int(np.isfinite(cols[k]).sum()) >= min_pairs]
    if len(valid_keys) < 3:
        return False
    label_map = dict(zip(keys, labels))
    names = [label_map.get(k, k) for k in valid_keys]
    sub_cols = {k: cols[k] for k in valid_keys}
    _, mat = _spearman_matrix(valid_keys, sub_cols, min_pairs)
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(max(6, len(names) * 0.75), max(5, len(names) * 0.65)))
    im = ax.imshow(mat, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(names)))
    ax.set_yticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_yticklabels(names, fontsize=8)
    for i in range(len(names)):
        for j in range(len(names)):
            v = mat[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7, color="#222")
    fig.colorbar(im, ax=ax, fraction=0.046)
    ax.set_title(title, fontsize=11)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_dual_zscore(
    rows: Sequence[dict],
    x_key: str,
    y_key: str,
    png_path: Path,
    *,
    x_label: str,
    y_label: str,
    title: str,
    min_pairs: int = 10,
) -> bool:
    xv = _col(rows, x_key)
    yv = _col(rows, y_key)
    m = np.isfinite(xv) & np.isfinite(yv)
    if int(m.sum()) < min_pairs:
        return False

    def _z(a: np.ndarray) -> np.ndarray:
        fin = np.isfinite(a)
        mu = float(np.mean(a[fin]))
        sd = float(np.std(a[fin]))
        out = np.full_like(a, np.nan)
        if sd > 1e-9:
            out[fin] = (a[fin] - mu) / sd
        return out

    from shared.analytics.hypotheses import spearman_rho_p

    rho, _, _ = spearman_rho_p(xv, yv)
    zx = rolling_mean(_z(xv), 7)
    zy = rolling_mean(_z(yv), 7)
    dates = _dates(rows)
    x = np.arange(len(dates))
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(x, zx, color="#1976d2", linewidth=1.8, label=x_label)
    ax.plot(x, zy, color="#c62828", linewidth=1.8, label=y_label)
    ax.axhline(0, color="#999", linewidth=0.8, linestyle=":")
    ax.set_ylabel("z-score (7d MA)")
    ax.set_title(f"{title} · ρ={rho:.2f}" if np.isfinite(rho) else title, fontsize=10)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.25)
    step = max(1, len(dates) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([dates[i][5:] for i in range(0, len(dates), step)], rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def panel_coverage(rows: Sequence[dict], metrics: Sequence[tuple[str, str]]) -> list[tuple[str, int, int]]:
    n = len(rows)
    out: list[tuple[str, int, int]] = []
    for key, label in metrics:
        cnt = int(np.isfinite(_col(rows, key)).sum())
        out.append((label, cnt, n))
    return out
