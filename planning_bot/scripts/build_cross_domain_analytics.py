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
    from planning_bot.services.snapshot_query import latest_per_calendar_day

    snaps = list(latest_per_calendar_day(get_snapshots(iphone_dir, days=None)).values())
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
    cutoff = (datetime.now().date() - timedelta(days=max(1, max_days) - 1)).isoformat()
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
