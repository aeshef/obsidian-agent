"""Build master daily panel with lag features from cross-domain + iPhone snapshots."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from shared.analytics.sleep_parse import parse_sleep_detail, sleep_ratios
from shared.analytics.series import sanitize_metric
from shared.analytics.vault_analytics_config import vault_analytics_config
from shared.vault_paths_config import dashboards_sub, folder, vault_rel_path


def _discover_agent_root(vault: Path) -> Path:
    return vault / folder("automation") / vault_rel_path("agent_subdir")


def _iphone_snapshots(vault: Path) -> list[dict]:
    iphone_dir = (
        vault
        / folder("dashboards")
        / dashboards_sub("data")
        / vault_rel_path("actions_iphone")
    )
    agent_root = _discover_agent_root(vault)
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))
    from planning_bot.services.iphone_context_parser import get_snapshots

    return get_snapshots(iphone_dir, days=None)


def _daily_iphone_metrics(vault: Path) -> dict[str, dict[str, float]]:
    cfg = vault_analytics_config()
    metric_keys = [str(k) for k in (cfg.get("iphone_metrics") or [])]
    snaps = _iphone_snapshots(vault)
    by_day: dict[str, dict[str, float]] = {}
    for s in sorted(snaps, key=lambda x: str(x.get("ts", ""))):
        day = str(s.get("ts", ""))[:10]
        if len(day) < 10:
            continue
        row = by_day.setdefault(day, {})
        for k in metric_keys:
            v = sanitize_metric(k, s.get(k))
            if np.isfinite(v):
                row[f"iphone_{k}"] = float(v)
        sleep = parse_sleep_detail(s.get("sleep_detail"))
        for sk, sv in sleep.items():
            row[sk] = float(sv)
        for rk, rv in sleep_ratios(row).items():
            row[rk] = float(rv)
        p, f, c = s.get("proteins_g"), s.get("fats_g"), s.get("carbs_g")
        if any(x is not None for x in (p, f, c)):
            kcal = sanitize_metric(
                "kcal_macros",
                4.0 * float(p or 0) + 9.0 * float(f or 0) + 4.0 * float(c or 0),
            )
            if np.isfinite(kcal):
                row["iphone_kcal_from_macros"] = float(kcal)
    return by_day


def _load_cross_rows(vault: Path) -> list[dict[str, Any]]:
    from shared.chart_paths import data_path

    path = data_path(vault, "cross_daily_features_json")
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    rows = doc.get("rows") or []
    return [r for r in rows if isinstance(r, dict)]


def _recent_rows(rows: list[dict[str, Any]], window_days: int) -> list[dict[str, Any]]:
    if not rows:
        return rows
    cutoff = (datetime.now().date() - timedelta(days=window_days)).isoformat()
    return [r for r in rows if str(r.get("date", "")) >= cutoff]


def _add_lags(rows: list[dict[str, Any]], keys: list[str]) -> None:
    for i, row in enumerate(rows):
        for k in keys:
            if i == 0:
                row[f"{k}_lag1"] = None
                continue
            prev = rows[i - 1].get(k)
            row[f"{k}_lag1"] = prev


def _add_weight_next(rows: list[dict[str, Any]]) -> None:
    for i, row in enumerate(rows):
        w = row.get("iphone_weight_kg")
        if w is None:
            continue
        row["iphone_weight_delta"] = None
        if i > 0:
            prev = rows[i - 1].get("iphone_weight_kg")
            if prev is not None:
                row["iphone_weight_delta"] = float(w) - float(prev)
        if i + 1 < len(rows):
            nxt = rows[i + 1].get("iphone_weight_kg")
            if nxt is not None:
                row["iphone_weight_kg_next"] = float(nxt)
                row["iphone_weight_delta_next"] = float(nxt) - float(w)


def build_master_panel(vault: Path) -> tuple[list[dict[str, Any]], list[str]]:
    cfg = vault_analytics_config()
    window = int((cfg.get("panel") or {}).get("window_days") or 120)
    cross = _recent_rows(_load_cross_rows(vault), window)
    iphone = _daily_iphone_metrics(vault)
    if not cross and not iphone:
        return [], []

    days = sorted(set(str(r.get("date", "")) for r in cross) | set(iphone.keys()))
    cross_by_day = {str(r["date"]): r for r in cross if r.get("date")}
    rows: list[dict[str, Any]] = []
    for d in days:
        base = dict(cross_by_day.get(d) or {})
        base.setdefault("date", d)
        for k, v in (iphone.get(d) or {}).items():
            base[k] = v
        if base.get("steps") is None and base.get("iphone_steps") is not None:
            base["steps"] = base["iphone_steps"]
        rows.append(base)

    lag_keys: set[str] = set()
    for row in rows:
        for k, v in list(row.items()):
            if k == "date" or v is None:
                continue
            if isinstance(v, (int, float)) and np.isfinite(float(v)):
                lag_keys.add(k)
    lag_list = sorted(lag_keys)
    _add_lags(rows, lag_list)
    _add_weight_next(rows)
    all_cols = sorted({k for row in rows for k in row.keys() if k != "date"})
    return rows, all_cols


def panel_to_arrays(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for col in columns:
        vals = []
        for row in rows:
            v = row.get(col)
            if v is None:
                vals.append(np.nan)
            else:
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    vals.append(np.nan)
        out[col] = np.asarray(vals, dtype=float)
    return out


def write_panel_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["date"] + [c for c in columns if c != "date"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k) for k in fieldnames})
