from __future__ import annotations

from planning_bot.core.pdmsg import pdmsg
import csv
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from planning_bot.core.config import IPHONE_CONTEXT_DIR
from planning_bot.services.iphone_context_parser import (
    format_for_llm,
    format_week_stats_for_llm,
    get_snapshots,
    week_numeric_aggregates,
)
from planning_bot.services.iphone_health_fields import discover_numeric_keys, discover_text_field_keys
from planning_bot.services.reference_date import reference_today
from planning_bot.services.snapshot_query import (
    captured_at_dt,
    filter_by_calendar_range,
    format_snapshot_provenance,
    latest_per_calendar_day,
    load_days_for_start,
    parse_date_param,
    parse_range_params,
    resolve_snapshot_for_day,
    snap_calendar_day,
)

def _select_series_fields(
    daily: Dict[date, Dict[str, Any]],
    fields: Optional[List[str]],
) -> tuple[List[str], Optional[str]]:
    'Operation implementation.'
    snaps = list(daily.values())
    available = discover_numeric_keys(snaps)
    if not fields:
        return available[:16], None
    requested = [f.strip() for f in fields if f and f.strip()]
    matched = [f for f in requested if any(f in s for s in snaps)]
    if matched:
        return matched, None
    suffix = "…" if len(available) > 10 else ""
    return available[:16], pdmsg(
        "health_columns_not_found",
        requested=requested,
        available=f"{', '.join(available[:10])}{suffix}",
    )


def load_health_snapshots(*, max_days: Optional[int] = None) -> List[Dict[str, Any]]:
    if max_days is None:
        return get_snapshots(IPHONE_CONTEXT_DIR, days=None)
    return get_snapshots(IPHONE_CONTEXT_DIR, days=max_days)


def format_health_snapshot(
    day: str = "",
    *,
    as_of: Optional[date] = None,
) -> str:
    'Operation implementation.'
    ref = as_of or reference_today()
    target = parse_date_param(day, ref=ref)
    snaps = load_health_snapshots(max_days=load_days_for_start(target or ref, floor=30))
    snap, health_day = resolve_snapshot_for_day(snaps, target)
    if not snap:
        if target:
            return pdmsg("auto_6c1a634d85", _p1=target.isoformat())
        return pdmsg("auto_90c14f279f")

    header = format_snapshot_provenance(
        label=pdmsg("auto_9fe8ab9a04"),
        health_day=health_day,
        captured_at=captured_at_dt(snap),
        as_of=ref,
        note=pdmsg("auto_ad0cb79a0a"),
    )
    body = format_for_llm(snap)
    if body.startswith("iPhone"):
        body = body.replace(pdmsg("auto_a82e24634a"), pdmsg("auto_f29cdbd785"), 1)
    return f"{header}\n{body}"


def format_health_series(
    from_date: str = "",
    to_date: str = "",
    fields: Optional[List[str]] = None,
    *,
    default_days: int = 14,
) -> str:
    start, end = parse_range_params(from_date, to_date, default_days=default_days)
    snaps = load_health_snapshots(max_days=load_days_for_start(start))
    daily = latest_per_calendar_day(filter_by_calendar_range(snaps, start, end))
    if not daily:
        return pdmsg("auto_a909b8ae11", _p1=start.isoformat(), _p3=end.isoformat())

    field_list, note = _select_series_fields(daily, fields)

    from shared.query.log_dump import assemble_log_dump, coverage_of
    from shared.query.ts import day_bounds, parse_iso_dt

    days_sorted = sorted(daily.keys())
    table_lines: list[str] = []
    if note:
        table_lines.append(note)
    table_lines.append("date\t" + "\t".join(field_list))
    for d in days_sorted:
        snap = daily[d]
        vals = []
        for f in field_list:
            v = snap.get(f)
            vals.append("" if v is None else str(v))
        table_lines.append(f"{d.isoformat()}\t" + "\t".join(vals))
    text_block = _format_text_fields_table(daily)
    if text_block:
        table_lines.append("")
        table_lines.append(pdmsg("auto_c4e8b1a293"))
        table_lines.append(text_block)
    req_start, req_end = day_bounds(start, end)
    cov = coverage_of(
        requested_start=req_start,
        requested_end=req_end,
        matched_ts=[parse_iso_dt(d.isoformat()) for d in days_sorted],
        shown_ts=[parse_iso_dt(d.isoformat()) for d in days_sorted],
        slice_kind="all",
    )
    return assemble_log_dump(
        title=pdmsg("auto_643e1025d1", _p1=start.isoformat(), _p3=end.isoformat(), _p5=len(daily)),
        coverage=cov,
        extras=table_lines,
    )


def _truncate_field_value(value: Any, *, max_len: int = 200) -> str:
    s = str(value).strip().replace("\t", " ").replace("\n", " | ")
    if len(s) > max_len:
        return s[: max_len - 1].rstrip() + "…"
    return s


def _format_text_fields_table(daily: Dict[date, Dict[str, Any]]) -> str:
    text_keys = discover_text_field_keys(list(daily.values()))
    if not text_keys:
        return ""
    lines = ["date\t" + "\t".join(text_keys)]
    for d in sorted(daily.keys()):
        snap = daily[d]
        vals = [
            _truncate_field_value(snap.get(k)) if snap.get(k) not in (None, "") else ""
            for k in text_keys
        ]
        if any(vals):
            lines.append(f"{d.isoformat()}\t" + "\t".join(vals))
    return "\n".join(lines) if len(lines) > 1 else ""


def format_health_summary(
    from_date: str = "",
    to_date: str = "",
) -> str:
    start, end = parse_range_params(from_date, to_date, default_days=7)
    snaps = load_health_snapshots(max_days=load_days_for_start(start))
    daily = latest_per_calendar_day(filter_by_calendar_range(snaps, start, end))
    window = list(daily.values())
    if not window:
        return pdmsg("auto_a909b8ae11", _p1=start.isoformat(), _p3=end.isoformat())

    agg = week_numeric_aggregates(window)
    header = (
        pdmsg("auto_a6bcf071b8", _p1=start.isoformat(), _p3=end.isoformat(), _p5=len(window))
    )
    stats = format_week_stats_for_llm(window)
    if stats.startswith("Health"):
        stats = stats.replace(pdmsg("auto_b633a94c7f"), pdmsg("auto_d4d8652207"), 1)
    text_block = _format_text_fields_table(daily)
    if text_block:
        stats = f"{stats}\n\n{pdmsg('auto_c4e8b1a293')}\n{text_block}"
    return f"{header}\n{stats}"


def _zscore(value: float, mean: float, stdev: float) -> float:
    if stdev < 1e-9:
        return 0.0
    return (value - mean) / stdev


def format_health_anomalies(*, lookback_days: int = 30, z_threshold: float = 1.8) -> str:
    lookback_days = max(7, min(lookback_days, 365))
    snaps = load_health_snapshots(max_days=lookback_days + 5)
    daily = latest_per_calendar_day(snaps)
    if len(daily) < 5:
        return pdmsg("auto_a32082552e", _p1=len(daily))

    days_sorted = sorted(daily.keys())
    latest_day = days_sorted[-1]
    latest = daily[latest_day]
    history_days = [d for d in days_sorted if d < latest_day][-lookback_days:]

    lines = [
        pdmsg("auto_7981ffecb7", _p1=lookback_days, _p3=z_threshold, _p5=latest_day.isoformat(), _p7=len(daily)),
    ]
    numeric_fields = discover_numeric_keys([daily[d] for d in history_days] + [latest])
    found = 0
    for field in numeric_fields:
        hist = []
        for d in history_days:
            v = daily[d].get(field)
            if v is not None:
                try:
                    hist.append(float(v))
                except (TypeError, ValueError):
                    pass
        if len(hist) < 5:
            continue
        try:
            cur = float(latest.get(field))
        except (TypeError, ValueError):
            continue
        if field not in latest:
            continue
        mean = sum(hist) / len(hist)
        var = sum((x - mean) ** 2 for x in hist) / len(hist)
        stdev = math.sqrt(var)
        z = _zscore(cur, mean, stdev)
        if abs(z) < z_threshold:
            continue
        direction = pdmsg("auto_f1f96ad214") if z > 0 else pdmsg("auto_62c09faad3")
        lines.append(
            pdmsg(
                "health_anomaly_line",
                field=field,
                cur=cur,
                direction=direction,
                z=z,
                mean=mean,
                stdev=stdev,
                n=len(hist),
            )
        )
        found += 1
    if not found:
        lines.append(pdmsg("auto_0279805565"))
    return "\n".join(lines)


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 5 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx < 1e-9 or deny < 1e-9:
        return None
    return num / (denx * deny)


def format_health_correlations(
    from_date: str = "",
    to_date: str = "",
    fields: Optional[List[str]] = None,
    *,
    min_r: float = 0.35,
    top_k: int = 12,
) -> str:
    start, end = parse_range_params(from_date, to_date, default_days=30)
    snaps = load_health_snapshots(max_days=load_days_for_start(start))
    daily = latest_per_calendar_day(filter_by_calendar_range(snaps, start, end))
    if len(daily) < 5:
        return pdmsg("auto_4d06a83211", _p1=len(daily))

    field_list, _ = _select_series_fields(daily, fields)

    rows: List[tuple[float, str, str, float]] = []
    for i, fa in enumerate(field_list):
        for fb in field_list[i + 1 :]:
            xs, ys = [], []
            for snap in daily.values():
                try:
                    xa, xb = snap.get(fa), snap.get(fb)
                    if xa is None or xb is None:
                        continue
                    xs.append(float(xa))
                    ys.append(float(xb))
                except (TypeError, ValueError):
                    continue
            r = _pearson(xs, ys)
            if r is not None and abs(r) >= min_r:
                rows.append((abs(r), fa, fb, r))
    rows.sort(reverse=True)
    rows = rows[:top_k]

    lines = [
        pdmsg("auto_e0255e0574", _p1=start.isoformat(), _p3=end.isoformat(), _p5=len(daily), _p7=min_r),
    ]
    if not rows:
        lines.append(pdmsg("auto_807b370f5c"))
        return "\n".join(lines)
    for _, fa, fb, r in rows:
        lines.append(f"  {fa} ↔ {fb}: r={r:+.3f}")
    return "\n".join(lines)


def export_health_daily_csv(
    output_path: Path,
    *,
    max_days: Optional[int] = None,
) -> tuple[int, Path]:
    'Operation implementation.'
    snaps = load_health_snapshots(max_days=max_days)
    daily = latest_per_calendar_day(snaps)
    if not daily:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8")
        return 0, output_path

    all_keys: set[str] = set()
    for snap in daily.values():
        all_keys.update(k for k in snap if k not in ("ts", "source"))

    columns = ["health_day", "captured_at", *sorted(all_keys)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for d in sorted(daily.keys()):
            snap = daily[d]
            row: Dict[str, Any] = {
                "health_day": d.isoformat(),
                "captured_at": snap.get("ts", ""),
            }
            for k in all_keys:
                v = snap.get(k)
                if v is not None and v != "":
                    row[k] = v
            w.writerow(row)
    return len(daily), output_path
