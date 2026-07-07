#!/usr/bin/env python3
"""Health metrics: rolling trends, linear regression, correlation heatmap."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

from planning_bot.core.pdmsg import pdmsg
from shared.analytics.series import ols_trend_masked, rolling_mean, sanitize_metric

from shared.chart_paths import chart_path, chart_wikilink_png, charts_root, ensure_parent
from shared.vault_paths_config import dashboards_sub, folder, vault_file, vault_rel_path


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / folder("tasks")).is_dir() and (p / folder("dashboards")).is_dir():
            return p
    return start.parents[3]


def _snapshots(vault: Path) -> list[dict]:
    iphone_dir = (
        vault
        / folder("dashboards")
        / dashboards_sub("data")
        / vault_rel_path("actions_iphone")
    )
    agent_root = vault / folder("automation") / vault_rel_path("agent_subdir")
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))
    from planning_bot.services.iphone_context_parser import get_snapshots

    return get_snapshots(iphone_dir, days=None)


def _daily_last_numeric(snaps: list[dict], key: str) -> dict[str, float]:
    from shared.analytics.series import sanitize_metric

    out: dict[str, float] = {}
    for s in sorted(snaps, key=lambda x: str(x.get("ts", ""))):
        day = str(s.get("ts", ""))[:10]
        if len(day) < 10:
            continue
        v = sanitize_metric(key, s.get(key))
        if np.isfinite(v):
            out[day] = v
    return out


def _kcal_day(snaps: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in sorted(snaps, key=lambda x: str(x.get("ts", ""))):
        day = str(s.get("ts", ""))[:10]
        if len(day) < 10:
            continue
        p, f, c = s.get("proteins_g"), s.get("fats_g"), s.get("carbs_g")
        if p is None and f is None and c is None:
            continue
        kcal = 4.0 * float(p or 0) + 9.0 * float(f or 0) + 4.0 * float(c or 0)
        if kcal > 0:
            out[day] = kcal
    return out


def _build_frame(snaps: list[dict]) -> tuple[list[str], dict[str, list[float]]]:
    keys = [
        "steps",
        "weight_kg",
        "resting_hr_bpm",
        "hrv_ms",
        "calories_kcal",
        "active_calories_kcal",
        "kcal_macros",
    ]
    series = {k: _daily_last_numeric(snaps, k) for k in keys if k != "kcal_macros"}
    series["kcal_macros"] = _kcal_day(snaps)
    days = sorted(set().union(*(s.keys() for s in series.values())))
    cols: dict[str, list[float]] = {}
    for k in keys:
        src = series.get(k) or {}
        cols[k] = [float("nan") if d not in src else src[d] for d in days]
    return days, cols


def _write_md(path: Path, title: str, body: str, ts: str) -> None:
    ensure_parent(path)
    path.write_text(
        f"# {title}\n\n{pdmsg('chart_updated_at', ts=ts)}\n\n{body}\n",
        encoding="utf-8",
    )


def main() -> int:
    os.environ.pop("PYTHONPATH", None)
    from shared.domain_messages import clear_domain_messages_cache
    from shared.locale import agent_locale

    clear_domain_messages_cache()
    agent_locale()
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=str)
    args = ap.parse_args()
    vault = Path(args.vault).resolve() if args.vault else _discover_vault(Path(__file__).resolve())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    snaps = _snapshots(vault)
    days, cols = _build_frame(snaps)
    trends_png = chart_path(vault, "chart_health_trends_png")
    corr_png = chart_path(vault, "chart_health_correlations_png")
    trends_md = chart_path(vault, "chart_health_trends_md")
    corr_md = chart_path(vault, "chart_health_correlations_md")

    if len(days) < 3:
        _write_md(
            trends_md,
            pdmsg("health_trends_title"),
            pdmsg("health_insufficient_days"),
            ts,
        )
        _write_md(
            corr_md,
            pdmsg("health_corr_title"),
            pdmsg("health_insufficient_corr"),
            ts,
        )
        print("SKIP: not enough health days")
        return 0

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("WARN: matplotlib/numpy missing", file=sys.stderr)
        return 1

    charts_root(vault).mkdir(parents=True, exist_ok=True)
    x = np.arange(len(days))

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    panels = [
        ("steps", pdmsg("health_panel_steps"), axes[0, 0]),
        ("kcal_macros", pdmsg("health_panel_kcal"), axes[0, 1]),
        ("weight_kg", pdmsg("health_panel_weight"), axes[1, 0]),
        ("resting_hr_bpm", pdmsg("health_panel_hr"), axes[1, 1]),
    ]
    trend_lines: list[str] = []
    for key, label, ax in panels:
        y = np.array(cols.get(key) or [float("nan")] * len(days), dtype=float)
        mask = np.isfinite(y)
        if mask.any():
            ax.plot(x[mask], y[mask], marker="o", markersize=3, linewidth=1.5, label=label)
        if mask.sum() >= 3:
            win = min(7, int(mask.sum()))
            roll = rolling_mean(y, win)
            roll_mask = np.isfinite(roll)
            if roll_mask.any():
                ax.plot(x[roll_mask], roll[roll_mask], linestyle="--", linewidth=1.2, alpha=0.8, label=f"MA{win}")
            trend = ols_trend_masked(x, y)
            trend_mask = np.isfinite(trend)
            if trend_mask.any():
                ax.plot(
                    x[trend_mask],
                    trend[trend_mask],
                    color="crimson",
                    linewidth=1.0,
                    alpha=0.7,
                    label=pdmsg("health_chart_trend_label"),
                )
                idx = np.where(mask)[0]
                coef = np.polyfit(idx.astype(float), y[mask], 1)
                trend_lines.append(
                    pdmsg(
                        "health_trend_coef_fmt",
                        label=label,
                        coef=coef[0],
                        days=int(mask.sum()),
                    )
                )
        ax.set_title(label, fontsize=10)
        if mask.any():
            pad = (y[mask].max() - y[mask].min()) * 0.08 or 1.0
            ax.set_ylim(y[mask].min() - pad, y[mask].max() + pad)
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=7, loc="upper left")
    tick_step = max(1, len(days) // 12)
    for ax in axes.flat:
        ax.set_xticks(x[::tick_step])
        ax.set_xticklabels([days[i][5:] for i in range(0, len(days), tick_step)], rotation=45, ha="right", fontsize=7)
    fig.suptitle(pdmsg("health_suptitle_trends"), fontsize=12)
    fig.tight_layout()
    ensure_parent(trends_png)
    fig.savefig(trends_png, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    names = [k for k, vals in cols.items() if sum(np.isfinite(np.array(vals, dtype=float))) >= 5]
    if len(names) >= 2:
        mat = []
        for i, a in enumerate(names):
            row = []
            va = np.array(cols[a], dtype=float)
            for b in names:
                vb = np.array(cols[b], dtype=float)
                m = np.isfinite(va) & np.isfinite(vb)
                if m.sum() < 5:
                    row.append(float("nan"))
                else:
                    row.append(float(np.corrcoef(va[m], vb[m])[0, 1]))
            mat.append(row)
        fig2, ax2 = plt.subplots(figsize=(8, 6))
        im = ax2.imshow(mat, vmin=-1, vmax=1, cmap="RdBu_r")
        ax2.set_xticks(range(len(names)))
        ax2.set_yticks(range(len(names)))
        ax2.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
        ax2.set_yticklabels(names, fontsize=8)
        for i in range(len(names)):
            for j in range(len(names)):
                v = mat[i][j]
                if np.isfinite(v):
                    ax2.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7)
        fig2.colorbar(im, ax=ax2, fraction=0.046)
        ax2.set_title(pdmsg("health_corr_chart_title"))
        fig2.tight_layout()
        ensure_parent(corr_png)
        fig2.savefig(corr_png, dpi=144, bbox_inches="tight", facecolor="white")
        plt.close(fig2)
        corr_body = "\n".join(
            f"| {a} | {b} | {mat[i][j]:+.2f} |"
            for i, a in enumerate(names)
            for j, b in enumerate(names)
            if i < j and np.isfinite(mat[i][j])
        )
        _write_md(
            corr_md,
            pdmsg("health_corr_title"),
            chart_wikilink_png("chart_health_correlations_png")
            + "\n\n| A | B | r |\n|---|---|---:|\n"
            + corr_body,
            ts,
        )
    else:
        _write_md(
            corr_md,
            pdmsg("health_corr_title"),
            pdmsg("health_insufficient_overlap"),
            ts,
        )

    _write_md(
        trends_md,
        pdmsg("health_trends_title"),
        chart_wikilink_png("chart_health_trends_png")
        + f"\n\n{pdmsg('health_trend_section')}\n"
        + "\n".join(trend_lines),
        ts,
    )
    print(f"OK: {trends_png}, {corr_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
