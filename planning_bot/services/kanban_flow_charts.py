"""Matplotlib charts for kanban flow metrics."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np

from shared.analytics.series import rolling_mean
from shared.chart_paths import ensure_parent
from shared.goals.task_segment import ALL_SEGMENTS

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(name: str) -> str:
    s = _EMOJI_RE.sub("", name or "").strip()
    return s or (name or "").strip()


def _mpl():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _short_col(name: str, max_len: int = 18) -> str:
    s = _strip_emoji(name)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def chart_arrivals_departures(
    daily: Sequence[dict],
    png_path: Path,
    *,
    title: str,
    label_arrivals: str,
    label_departures: str,
    label_debt: str,
    label_x: str,
    rolling_label: str,
    window: int = 7,
) -> bool:
    if len(daily) < 2:
        return False
    plt = _mpl()
    dates = [str(r.get("date", "")) for r in daily]
    x = np.arange(len(dates))
    arr = np.array([int(r.get("arrivals", 0) or 0) for r in daily], dtype=float)
    dep = np.array([int(r.get("departures", 0) or 0) for r in daily], dtype=float)
    debt = np.array([int(r.get("flow_debt", 0) or 0) for r in daily], dtype=float)
    dep_ma = rolling_mean(dep, window)

    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.bar(x - 0.2, arr, width=0.4, label=label_arrivals, color="#5c6bc0", alpha=0.85)
    ax1.bar(x + 0.2, dep, width=0.4, label=label_departures, color="#66bb6a", alpha=0.85)
    ax1.plot(x, dep_ma, color="#2e7d32", linewidth=2, label=rolling_label)
    ax1.set_ylabel(label_arrivals + " / " + label_departures)
    ax1.set_xlabel(label_x)
    ax1.legend(loc="upper left", fontsize=8)

    ax2 = ax1.twinx()
    ax2.plot(x, debt, color="#ef6c00", linewidth=1.5, linestyle="--", label=label_debt)
    ax2.set_ylabel(label_debt, color="#ef6c00")
    ax2.tick_params(axis="y", labelcolor="#ef6c00")

    ax1.set_title(title, fontsize=11)
    step = max(1, len(dates) // 12)
    ax1.set_xticks(x[::step])
    ax1.set_xticklabels([dates[i][5:] for i in range(0, len(dates), step)], rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_cfd(
    column_history: Sequence[dict],
    columns: Sequence[str],
    png_path: Path,
    *,
    title: str,
    label_x: str,
    label_y: str,
) -> bool:
    if len(column_history) < 2 or not columns:
        return False
    plt = _mpl()
    dates = [str(s.get("date", "")) for s in column_history]
    x = np.arange(len(dates))
    n = len(dates)
    bottom = np.zeros(n)
    palette = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
    ]
    fig, ax = plt.subplots(figsize=(12, 6))
    for i, col in enumerate(columns):
        series = np.array(
            [int((s.get("by_column") or {}).get(col, 0) or 0) for s in column_history],
            dtype=float,
        )
        ax.fill_between(
            x,
            bottom,
            bottom + series,
            label=_short_col(col),
            color=palette[i % len(palette)],
            alpha=0.75,
            linewidth=0,
        )
        bottom = bottom + series
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(label_x)
    ax.set_ylabel(label_y)
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8)
    step = max(1, len(dates) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([dates[i][5:] for i in range(0, len(dates), step)], rotation=45, ha="right", fontsize=7)
    fig.tight_layout(rect=(0, 0, 0.82, 1))
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_lead_cycle_weekly(
    weekly: Sequence[dict],
    png_path: Path,
    *,
    title: str,
    label_lead: str,
    label_cycle: str,
    label_x: str,
) -> bool:
    rows = [r for r in weekly if r.get("lead_p50") is not None or r.get("cycle_p50") is not None]
    if len(rows) < 2:
        return False
    plt = _mpl()
    weeks = [str(r.get("week", "")) for r in rows]
    x = np.arange(len(weeks))
    lead = np.array([r.get("lead_p50") if r.get("lead_p50") is not None else np.nan for r in rows])
    cycle = np.array([r.get("cycle_p50") if r.get("cycle_p50") is not None else np.nan for r in rows])
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(x, lead, "o-", color="#1565c0", label=label_lead, linewidth=2)
    ax.plot(x, cycle, "s-", color="#c62828", label=label_cycle, linewidth=2)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(label_x)
    ax.set_ylabel("days")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    step = max(1, len(weeks) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([weeks[i] for i in range(0, len(weeks), step)], rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_aging_buckets(
    buckets: dict,
    png_path: Path,
    *,
    title: str,
    labels: Dict[str, str],
) -> bool:
    keys = ["0_7", "8_14", "15_30", "31_plus"]
    vals = [int(buckets.get(k, 0) or 0) for k in keys]
    if sum(vals) == 0:
        return False
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ["#a5d6a7", "#fff59d", "#ffcc80", "#ef9a9a"]
    ax.bar([labels.get(k, k) for k in keys], vals, color=colors, edgecolor="white")
    ax.set_title(title, fontsize=11)
    ax.set_ylabel(labels.get("y_open", "open"))
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_transitions_heatmap(
    transitions: Dict[str, int],
    png_path: Path,
    *,
    title: str,
    min_count: int = 2,
) -> bool:
    pairs: List[tuple[str, str, int]] = []
    for k, v in transitions.items():
        if v < min_count:
            continue
        parts = k.split("\t", 1)
        if len(parts) != 2:
            continue
        pairs.append((parts[0], parts[1], int(v)))
    if len(pairs) < 2:
        return False
    from_cols = sorted({_short_col(a) for a, _, _ in pairs})
    to_cols = sorted({_short_col(b) for _, b, _ in pairs})
    mat = np.zeros((len(from_cols), len(to_cols)))
    fi = {c: i for i, c in enumerate(from_cols)}
    ti = {c: i for i, c in enumerate(to_cols)}
    for a, b, v in pairs:
        mat[fi[_short_col(a)], ti[_short_col(b)]] += v
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(max(8, len(to_cols) * 0.9), max(6, len(from_cols) * 0.7)))
    im = ax.imshow(mat, cmap="Blues", aspect="auto")
    ax.set_xticks(np.arange(len(to_cols)))
    ax.set_yticks(np.arange(len(from_cols)))
    ax.set_xticklabels(to_cols, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(from_cols, fontsize=7)
    ax.set_title(title, fontsize=11)
    fig.colorbar(im, ax=ax, fraction=0.03)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def _rolling_mean_sparse(y: np.ndarray, window: int) -> np.ndarray:
    """Centered mean over finite points only; needs ≥1 point in window."""
    out = np.full_like(y, np.nan, dtype=float)
    n = len(y)
    half = max(0, window // 2)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = y[lo:hi]
        chunk = chunk[np.isfinite(chunk)]
        if len(chunk) >= 1:
            out[i] = float(np.mean(chunk))
    return out


def _interp_continuous(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Linear bridge across NaN gaps (no forward-fill spikes)."""
    mask = np.isfinite(y)
    if not mask.any():
        return y
    if mask.sum() == 1:
        return np.full_like(y, y[mask][0])
    return np.interp(x.astype(float), x[mask].astype(float), y[mask])


def chart_goal_segment_completions(
    series: Sequence[dict],
    png_path: Path,
    *,
    title: str,
    segment_labels: Dict[str, str],
    label_x: str,
    label_y: str,
    ratio_label: str,
    ratio_window: int = 7,
) -> bool:
    if len(series) < 2:
        return False
    plt = _mpl()
    dates = [str(r.get("date", "")) for r in series]
    x = np.arange(len(dates))
    width = 0.82
    bottom = np.zeros(len(dates))
    colors = {
        "goal_mapped": "#1565c0",
        "unmapped": "#9e9e9e",
        "daily_routine": "#ff8f00",
    }
    fig, ax = plt.subplots(figsize=(12, 5))
    for seg in ALL_SEGMENTS:
        y = np.array([int(r.get(seg, 0) or 0) for r in series], dtype=float)
        ax.bar(
            x,
            y,
            width,
            bottom=bottom,
            label=segment_labels.get(seg, seg),
            color=colors.get(seg, "#888"),
            edgecolor="white",
            linewidth=0.4,
        )
        bottom = bottom + y

    goal = np.array([int(r.get("goal_mapped", 0) or 0) for r in series], dtype=float)
    daily = np.array([int(r.get("daily_routine", 0) or 0) for r in series], dtype=float)
    n = len(dates)
    ratio_day = np.full(n, np.nan, dtype=float)
    with_daily = daily > 0
    ratio_day[with_daily] = goal[with_daily] / daily[with_daily]
    ratio_line = _interp_continuous(x, _rolling_mean_sparse(ratio_day, ratio_window))

    ax2 = ax.twinx()
    ax2.axhline(1.0, color="#c62828", alpha=0.25, linestyle=":", linewidth=1)
    ax2.plot(x, ratio_line, color="#c62828", linewidth=2.2, label=ratio_label)
    ax2.set_ylabel(ratio_label, color="#c62828")
    ax2.tick_params(axis="y", labelcolor="#c62828")

    ax.set_title(title, fontsize=11)
    ax.set_xlabel(label_x)
    ax.set_ylabel(label_y)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
    step = max(1, len(dates) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([dates[i][5:] for i in range(0, len(dates), step)], rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def chart_wip_goal_segments(
    column_history: Sequence[dict],
    png_path: Path,
    *,
    title: str,
    segment_labels: Dict[str, str],
    label_x: str,
    label_y: str,
) -> bool:
    if len(column_history) < 2:
        return False
    plt = _mpl()
    dates = [str(s.get("date", "")) for s in column_history]
    x = np.arange(len(dates))
    fig, ax = plt.subplots(figsize=(12, 5))
    colors = {
        "goal_mapped": "#1565c0",
        "unmapped": "#9e9e9e",
        "daily_routine": "#ff8f00",
    }
    for seg in ALL_SEGMENTS:
        y = np.array(
            [int((s.get("by_goal_segment") or {}).get(seg, 0) or 0) for s in column_history],
            dtype=float,
        )
        ax.plot(x, y, "o-", label=segment_labels.get(seg, seg), color=colors.get(seg, "#888"), linewidth=1.8, markersize=3)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(label_x)
    ax.set_ylabel(label_y)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.25)
    step = max(1, len(dates) // 12)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([dates[i][5:] for i in range(0, len(dates), step)], rotation=45, ha="right", fontsize=7)
    fig.tight_layout()
    ensure_parent(png_path)
    fig.savefig(png_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True
