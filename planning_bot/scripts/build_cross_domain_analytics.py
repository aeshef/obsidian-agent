#!/usr/bin/env python3
"""Cross-domain daily features: tasks × finance × health."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from planning_bot.core.pdmsg import pdmsg
from shared.analytics.series import rolling_mean
from shared.chart_paths import chart_path, chart_wikilink_png, charts_root, data_path, ensure_parent
from shared.vault_paths_config import dashboards_sub, folder, vault_rel_path


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / folder("tasks")).is_dir() and (p / folder("dashboards")).is_dir():
            return p
    return start.parents[3]


def _task_completions_by_day(vault: Path) -> dict[str, int]:
    agent_root = vault / folder("automation") / vault_rel_path("agent_subdir")
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))
    from planning_bot.core.config import ACTION_LOG_PREFIX
    from planning_bot.services.action_log_parser import collect_events_from_logs, is_completion_event

    logs_dir = vault / folder("dashboards") / dashboards_sub("logs")
    events = collect_events_from_logs(logs_dir, log_glob=f"{ACTION_LOG_PREFIX}*.md")
    c: Counter[str] = Counter()
    for e in events:
        if is_completion_event(e):
            c[e["dt"].date().isoformat()] += 1
    return dict(c)


def _finance_by_day(vault: Path) -> tuple[dict[str, float], dict[str, float]]:
    db = vault / folder("dashboards") / dashboards_sub("data") / "finance.db"
    exp: dict[str, float] = {}
    inc: dict[str, float] = {}
    if not db.is_file():
        return exp, inc
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT date(occurred_at) AS d, type, SUM(amount) AS s
               FROM transactions WHERE user_id=1 GROUP BY d, type"""
        ).fetchall()
    except sqlite3.Error:
        conn.close()
        return exp, inc
    conn.close()
    for r in rows:
        d = str(r["d"])
        if r["type"] == "expense":
            exp[d] = float(r["s"] or 0)
        elif r["type"] == "income":
            inc[d] = float(r["s"] or 0)
    return exp, inc


def _health_by_day(vault: Path) -> dict[str, dict[str, float]]:
    from shared.analytics.series import sanitize_metric

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

    snaps = get_snapshots(iphone_dir, days=None)
    keys = ("steps", "calories_kcal", "kcal_macros")
    out: dict[str, dict[str, float]] = {k: {} for k in keys}
    for s in sorted(snaps, key=lambda x: str(x.get("ts", ""))):
        day = str(s.get("ts", ""))[:10]
        if len(day) < 10:
            continue
        for k in ("steps", "calories_kcal"):
            v = sanitize_metric(k, s.get(k))
            if np.isfinite(v):
                out[k][day] = v
        p, f, c = s.get("proteins_g"), s.get("fats_g"), s.get("carbs_g")
        if any(x is not None for x in (p, f, c)):
            kcal = sanitize_metric("kcal_macros", 4.0 * float(p or 0) + 9.0 * float(f or 0) + 4.0 * float(c or 0))
            if np.isfinite(kcal):
                out["kcal_macros"][day] = kcal
    return out


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 8:
        return float("nan")
    xr = np.argsort(np.argsort(x[m])).astype(float)
    yr = np.argsort(np.argsort(y[m])).astype(float)
    if np.std(xr) < 1e-9 or np.std(yr) < 1e-9:
        return float("nan")
    return float(np.corrcoef(xr, yr)[0, 1])


def _zscore(y: np.ndarray) -> np.ndarray:
    m = np.isfinite(y)
    if m.sum() < 3:
        return np.full_like(y, np.nan)
    mu = float(np.mean(y[m]))
    sd = float(np.std(y[m]))
    if sd < 1e-9:
        return np.full_like(y, np.nan)
    out = np.full_like(y, np.nan)
    out[m] = (y[m] - mu) / sd
    return out


def _recent(rows: list[dict], max_days: int = 120) -> list[dict]:
    if not rows:
        return rows
    cutoff = (datetime.now().date() - timedelta(days=max_days)).isoformat()
    return [r for r in rows if str(r.get("date", "")) >= cutoff]


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

    tasks = _task_completions_by_day(vault)
    exp, inc = _finance_by_day(vault)
    health = _health_by_day(vault)
    all_days = sorted(set(tasks) | set(exp) | set(inc) | set(health["steps"]) | set(health["kcal_macros"]))

    rows = []
    for d in all_days:
        rows.append(
            {
                "date": d,
                "tasks_completed": int(tasks.get(d, 0)),
                "expense_rub": float(exp.get(d, 0)),
                "income_rub": float(inc.get(d, 0)),
                "steps": health["steps"].get(d),
                "kcal": health["kcal_macros"].get(d) or health["calories_kcal"].get(d),
            }
        )
    rows = _recent(rows, 120)

    features_path = data_path(vault, "cross_daily_features_json")
    ensure_parent(features_path)
    features_path.write_text(json.dumps({"updated": ts, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    if len(rows) < 14:
        print("SKIP: not enough cross-domain days")
        return 0

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("WARN: matplotlib missing", file=sys.stderr)
        return 1

    labels = {
        "tasks_completed": pdmsg("cross_label_tasks"),
        "expense_rub": pdmsg("cross_label_expense"),
        "steps": pdmsg("cross_label_steps"),
        "kcal": pdmsg("cross_label_kcal"),
    }
    keys = list(labels.keys())
    cols = {
        "tasks_completed": np.array([float(r["tasks_completed"]) for r in rows], dtype=float),
        "expense_rub": np.array([float(r["expense_rub"]) for r in rows], dtype=float),
        "steps": np.array([float(r["steps"]) if r["steps"] is not None else np.nan for r in rows], dtype=float),
        "kcal": np.array([float(r["kcal"]) if r["kcal"] is not None else np.nan for r in rows], dtype=float),
    }
    names = [labels[k] for k in keys]
    mat = []
    for a in keys:
        row = []
        va = cols[a]
        for b in keys:
            row.append(_spearman(va, cols[b]))
        mat.append(row)

    charts_root(vault).mkdir(parents=True, exist_ok=True)
    corr_png = chart_path(vault, "chart_cross_correlations_png")
    corr_md = chart_path(vault, "chart_cross_correlations_md")
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    masked = np.array(mat, dtype=float)
    im = ax.imshow(masked, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(names)))
    ax.set_yticks(range(len(names)))
    ax.set_xticklabels(names, rotation=25, ha="right", fontsize=9)
    ax.set_yticklabels(names, fontsize=9)
    for i in range(len(names)):
        for j in range(len(names)):
            v = masked[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8, color="#222")
    fig.colorbar(im, ax=ax, fraction=0.046)
    ax.set_title(pdmsg("cross_title_correlations"), fontsize=11)
    fig.tight_layout()
    ensure_parent(corr_png)
    fig.savefig(corr_png, dpi=144, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    dates = [str(r["date"]) for r in rows]
    x = np.arange(len(dates))

    def _dual_series(x_key: str, y_key: str, png_key: str, md_key: str, title_key: str) -> None:
        xv = cols[x_key].copy()
        yv = cols[y_key].copy()
        # ignore all-zero finance days for alignment
        if x_key == "expense_rub":
            xv[xv <= 0] = np.nan
        if y_key == "expense_rub":
            yv[yv <= 0] = np.nan
        m = np.isfinite(xv) & np.isfinite(yv)
        if m.sum() < 10:
            return
        rho = _spearman(xv, yv)
        zx = _zscore(xv)
        zy = _zscore(yv)
        rx = rolling_mean(zx, 7)
        ry = rolling_mean(zy, 7)

        fig2, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5.5), gridspec_kw={"height_ratios": [2, 1]})
        ax1.plot(x, rx, color="#1976d2", linewidth=1.8, label=labels[x_key])
        ax1.plot(x, ry, color="#c62828", linewidth=1.8, label=labels[y_key])
        ax1.axhline(0, color="#999", linewidth=0.8, linestyle=":")
        ax1.set_ylabel("z-score (7d MA)")
        ax1.set_title(f"{pdmsg(title_key)} · ρ={rho:.2f}" if np.isfinite(rho) else pdmsg(title_key))
        ax1.legend(fontsize=8, loc="upper left")
        ax1.grid(True, alpha=0.25)
        step = max(1, len(dates) // 10)
        ax1.set_xticks(x[::step])
        ax1.set_xticklabels([dates[i][5:] for i in range(0, len(dates), step)], rotation=45, ha="right", fontsize=7)

        ax2.scatter(xv[m], yv[m], alpha=0.55, s=22, c="#455a64", edgecolors="white", linewidths=0.3)
        ax2.set_xlabel(labels[x_key])
        ax2.set_ylabel(labels[y_key])
        ax2.grid(True, alpha=0.25)
        fig2.tight_layout()
        p = chart_path(vault, png_key)
        ensure_parent(p)
        fig2.savefig(p, dpi=144, bbox_inches="tight", facecolor="white")
        plt.close(fig2)
        chart_path(vault, md_key).write_text(
            f"# {pdmsg(title_key)}\n\n{pdmsg('chart_updated_at', ts=ts)}"
            + (f" · Spearman ρ={rho:.2f}" if np.isfinite(rho) else "")
            + f"\n\n{chart_wikilink_png(png_key)}\n",
            encoding="utf-8",
        )

    _dual_series(
        "tasks_completed",
        "steps",
        "chart_cross_tasks_steps_png",
        "chart_cross_tasks_steps_md",
        "cross_title_tasks_steps",
    )
    _dual_series(
        "tasks_completed",
        "expense_rub",
        "chart_cross_tasks_spending_png",
        "chart_cross_tasks_spending_md",
        "cross_title_tasks_spending",
    )

    corr_md.write_text(
        f"# {pdmsg('cross_title_correlations')}\n\n{pdmsg('chart_updated_at', ts=ts)}\n\n"
        f"{chart_wikilink_png('chart_cross_correlations_png')}\n\n"
        f"{pdmsg('cross_corr_data_line', path=vault_rel_path('cross_daily_features_json'))}\n",
        encoding="utf-8",
    )
    print(f"OK: {features_path}, {corr_png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
