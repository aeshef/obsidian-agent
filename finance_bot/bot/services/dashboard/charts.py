"""Matplotlib PNG charts for finance dashboard."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from bot.dashboard_templates import dtpl


def plot_lines_png(
    x_labels: list[str],
    series: dict[str, list[float]],
    *,
    title: str,
    y_label: str,
    out_path: Path,
    y_min: float = 0.0,
    y_max: Optional[float] = None,
) -> bool:
    """Draw line chart PNG. Returns False if insufficient data."""
    if not x_labels or not series:
        return False
    n = len(x_labels)
    if n == 0:
        return False
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    x = list(range(n))
    fig, ax = plt.subplots(figsize=(11.5, 4.8))
    colors = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]
    for i, (name, vals) in enumerate(series.items()):
        vals = (vals or [])[:n] + [0] * max(0, n - len(vals or []))
        safe_name = name.replace('"', "'")[:30]
        ax.plot(x, vals, marker="o", markersize=2.6, linewidth=1.4, label=safe_name, color=colors[i % len(colors)])
    ax.set_title(title)
    ax.set_xlabel(dtpl("charts", "period_xlabel"))
    ax.set_ylabel(y_label)
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=8 if n > 20 else 9)
    ax.grid(True, alpha=0.25)
    if y_max is not None:
        ax.set_ylim(bottom=y_min, top=y_max)
    else:
        ax.set_ylim(bottom=y_min)
    ax.yaxis.set_major_locator(MaxNLocator(integer=False))
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9, ncols=2 if len(series) > 4 else 1)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return True


def plot_stacked_bar_categories_png(
    x_labels: list[str],
    series: dict[str, list[float]],
    *,
    title: str,
    y_label: str,
    out_path: Path,
    show_total_labels: bool = True,
    totals_for_labels: Optional[List[float]] = None,
) -> bool:
    """Stacked bar chart: each bar is a day/week, segments are category sums (RUB)."""
    if not x_labels or not series:
        return False
    n = len(x_labels)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    cats = list(series.keys())
    stacks: list[list[float]] = []
    for cat in cats:
        v = series[cat]
        row = [float(x) for x in ((v or [])[:n] + [0.0] * max(0, n - len(v or [])))]
        stacks.append(row)

    colors = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ]
    w = max(11.5, min(24.0, 0.2 * n + 6))
    fig, ax = plt.subplots(figsize=(w, 5.4))
    x_pos = list(range(n))
    bottom = [0.0] * n
    for i, cat in enumerate(cats):
        heights = stacks[i]
        ax.bar(
            x_pos,
            heights,
            bottom=bottom,
            width=0.82,
            label=cat.replace('"', "'")[:28],
            color=colors[i % len(colors)],
        )
        bottom = [bottom[j] + heights[j] for j in range(n)]

    if show_total_labels:
        if totals_for_labels is not None and len(totals_for_labels) == n:
            label_vals = [float(totals_for_labels[j]) for j in range(n)]
        else:
            label_vals = bottom
        for j in range(n):
            total = label_vals[j]
            if total <= 0:
                continue
            lbl = f"{total:,.0f}".replace(",", " ")
            y_text = bottom[j] if totals_for_labels is None else total
            ax.text(j, y_text, lbl, ha="center", va="bottom", fontsize=7, clip_on=False)

    ax.set_title(title)
    ax.set_xlabel(dtpl("charts", "period_xlabel"))
    ax.set_ylabel(y_label)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=8 if n > 20 else 9)
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MaxNLocator(integer=False))
    ax.legend(loc="upper left", framealpha=0.9, fontsize=8, ncols=2 if len(cats) > 5 else 1)
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return True
