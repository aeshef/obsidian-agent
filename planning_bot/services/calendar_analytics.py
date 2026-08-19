from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from planning_bot.core.pdmsg import pdmsg
from shared.yaml_config import load_merged_config

_WD = (
    pdmsg("auto_37a7379e0b"),
    pdmsg("auto_ef06566baf"),
    pdmsg("auto_0900d1f798"),
    pdmsg("auto_3e88f5cb5b"),
    pdmsg("auto_6da80c2907"),
    pdmsg("auto_06b0f2a4a5"),
    pdmsg("auto_8c0f1e0292"),
)

_CALENDAR_CFG_DIR = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=1)
def _activity_config() -> dict[str, Any]:
    return load_merged_config(str(_CALENDAR_CFG_DIR), "calendar_activity_types")


def clear_activity_config_cache() -> None:
    _activity_config.cache_clear()


def chart_colors_for_activity() -> dict[str, str]:
    return _chart_colors()


def work_attention_weight() -> float:
    return float(_attention_weights().get(_work_type(), 0.45))


def _default_type() -> str:
    return str(_activity_config().get("default_type") or "other")


def _work_type() -> str:
    return str(_activity_config().get("work_type") or "work")


def _flight_type() -> str:
    return str(_activity_config().get("flight_type") or "travel")


def _block_type() -> str:
    return str(_activity_config().get("block_type") or "block")


def allowed_activity_types() -> set[str]:
    """Type ids from weights + descriptions (+ stable aliases)."""
    types = set(_attention_weights()) | set(_type_descriptions())
    types.update({_default_type(), _work_type(), _flight_type(), _block_type()})
    return {t for t in types if t}


def activity_type_descriptions() -> dict[str, str]:
    return dict(_type_descriptions())


def activity_signature(ev: Dict) -> str:
    title = (ev.get("title") or "").strip().lower()
    tag = (ev.get("tag") or "").strip().lower()
    return f"{title}|{tag}"


def _chart_colors() -> dict[str, str]:
    raw = _activity_config().get("chart_colors") or {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _attention_weights() -> dict[str, float]:
    raw = _activity_config().get("attention_weights") or {}
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def _type_descriptions() -> dict[str, str]:
    raw = _activity_config().get("type_descriptions") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v).strip() for k, v in raw.items() if str(k).strip() and str(v).strip()}


def is_calendar_block(ev: Dict) -> bool:
    """True when LLM (or empty title) marked the slot as a non-meeting block."""
    if not (ev.get("title") or "").strip():
        return True
    return classify_activity(ev) == _block_type()


def classify_activity(ev: Dict) -> str:
    """Read LLM-assigned activity_type from the event; no keyword fallback.

    Sync writes ``activity_type`` via ``ensure_activity_types``. Until then
    (or if the label is unknown) returns ``default_type``.
    """
    allowed = allowed_activity_types()
    raw = str(ev.get("activity_type") or "").strip()
    if raw and raw in allowed:
        sig = ev.get("activity_sig")
        if sig is None or sig == activity_signature(ev):
            return raw
    return _default_type()


def attention_weight_for(ev: Dict, activity_type: Optional[str] = None) -> float:
    weights = _attention_weights()
    typ = activity_type or classify_activity(ev)
    if typ == _block_type() or is_calendar_block(ev):
        return float(weights.get(_block_type(), 0.1))
    if typ in weights:
        return float(weights[typ])
    return float(weights.get(_default_type(), 0.35))


def _d(ev: Dict) -> int:
    if ev.get("is_allday") or ev.get("is_cancelled"):
        return 0
    try:
        t0 = datetime.strptime(ev["start"], "%H:%M")
        t1 = datetime.strptime(ev["end"], "%H:%M")
        m = max(0, (t1 - t0).total_seconds() // 60)
        return int(m) if 0 < m <= 16 * 60 else 0
    except (ValueError, KeyError):
        return 0


def _day(dt: date) -> str:
    return dt.strftime("%Y-%m-%d")


def _parse_day(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _norm_title_key(title: str) -> str:
    t = (title or "").strip().lower()
    t = re.sub(r"[\s:：，,;；|]+", " ", t)
    t = re.sub(pdmsg("auto_67451380c2"), "", t, flags=re.IGNORECASE)
    return t[:48].strip() or pdmsg("auto_2cdb199719")


def compute_week_analytics(events: List[Dict], anchor: date, horizon_days: int = 8) -> Dict[str, Any]:
    day_start = anchor
    day_end = anchor + timedelta(days=horizon_days - 1)

    in_win = []
    for ev in events:
        if ev.get("is_cancelled"):
            continue
        try:
            d = _parse_day(ev["date"])
        except ValueError:
            continue
        if day_start <= d <= day_end:
            in_win.append(ev)

    per_day: Dict[str, List[Dict]] = defaultdict(list)
    for ev in in_win:
        per_day[ev["date"]].append(ev)

    days_out: List[Dict[str, Any]] = []
    tag_minutes: Counter = Counter()
    activity_minutes: Counter = Counter()
    evening_events = 0
    late_end_events = 0
    total_timed_minutes = 0
    total_attention_minutes = 0
    untagged_minutes = 0
    pressure_candidates: List[Dict[str, Any]] = []
    unclassified_candidates: List[Dict[str, Any]] = []

    for i in range(horizon_days):
        d = anchor + timedelta(days=i)
        ds = _day(d)
        day_evs = per_day.get(ds, [])
        timed = [e for e in day_evs if not e.get("is_allday")]
        allday = [e for e in day_evs if e.get("is_allday")]
        mins = sum(_d(e) for e in timed)
        total_timed_minutes += mins

        day_attention = 0
        ev_evening = 0
        ev_late = 0
        day_activity: Counter = Counter()
        meeting_like = 0

        for e in timed:
            m = _d(e)
            if not m:
                continue
            typ = classify_activity(e)
            block = is_calendar_block(e)
            w = attention_weight_for(e, typ)
            attn = int(round(m * w))
            day_attention += attn
            total_attention_minutes += attn
            activity_minutes[typ] += m
            day_activity[typ] += m
            if not block:
                meeting_like += 1
                pressure_candidates.append(
                    {
                        "date": ds,
                        "weekday": _WD[d.weekday()],
                        "title": (e.get("title") or "").strip() or "—",
                        "tag": e.get("tag"),
                        "activity": typ,
                        "minutes": m,
                        "hours": round(m / 60, 2),
                        "attention_hours": round(attn / 60, 2),
                        "start": e.get("start"),
                        "end": e.get("end"),
                    }
                )
                if typ == _default_type():
                    unclassified_candidates.append(
                        {
                            "title": (e.get("title") or "").strip() or "—",
                            "tag": e.get("tag"),
                            "hours": round(m / 60, 2),
                            "minutes": m,
                        }
                    )
            try:
                sh, _sm = map(int, e["start"].split(":"))
                eh, em = map(int, e["end"].split(":"))
            except (ValueError, KeyError):
                continue
            if sh >= 18:
                evening_events += 1
                ev_evening += 1
            if eh > 21 or (eh == 21 and em > 0):
                late_end_events += 1
                ev_late += 1
            tag = e.get("tag") or pdmsg("auto_20fca4691c")
            tag_minutes[tag] += m
            if not (e.get("tag") or "").strip():
                untagged_minutes += m

        frag = 0.0
        non_block = [e for e in timed if not is_calendar_block(e) and _d(e)]
        if len(non_block) >= 3 and mins > 0:
            try:
                slots = sorted(non_block, key=lambda e: datetime.strptime(e["start"], "%H:%M"))
                short = sum(1 for e in slots if _d(e) <= 35)
                frag = round(short / max(1, len(slots)), 2)
            except Exception:
                frag = 0.0

        merged_span = _max_busy_span_minutes(timed)
        days_out.append(
            {
                "date": ds,
                "weekday": _WD[d.weekday()],
                "weekday_i": d.weekday(),
                "meeting_count": meeting_like,
                "timed_slot_count": len(timed),
                "allday_count": len(allday),
                "meeting_minutes": mins,
                "meeting_hours_rounded": round(mins / 60, 2),
                "invite_hours": round(mins / 60, 2),
                "attention_minutes": day_attention,
                "attention_hours": round(day_attention / 60, 2),
                "activity_minutes": {k: int(v) for k, v in day_activity.items() if v},
                "evening_starts_18plus": ev_evening,
                "ends_after_21": ev_late,
                "fragmentation_short_meetings_ratio": frag,
                "max_contiguous_busy_minutes": merged_span,
            }
        )

    heavy = [x for x in days_out if x["meeting_minutes"] >= 300]
    light = [x for x in days_out if 0 < x["meeting_minutes"] < 120]
    peak = max(days_out, key=lambda x: x["meeting_minutes"], default=None)

    totals = {
        "window_meeting_minutes": total_timed_minutes,
        "window_meeting_hours": round(total_timed_minutes / 60, 2),
        "invite_hours": round(total_timed_minutes / 60, 2),
        "attention_minutes": total_attention_minutes,
        "attention_hours": round(total_attention_minutes / 60, 2),
        "untagged_hours": round(untagged_minutes / 60, 2),
        "days_with_any_timed_meeting": sum(1 for x in days_out if x["timed_slot_count"] > 0),
        "heavy_days_ge_5h": len(heavy),
        "light_days_under_2h": len(light),
        "max_single_day_minutes": max((x["meeting_minutes"] for x in days_out), default=0),
        "evening_starts_week": evening_events,
        "ends_after_21_week": late_end_events,
        "peak_day": (peak or {}).get("date"),
        "peak_day_hours": (peak or {}).get("meeting_hours_rounded", 0),
    }

    tags_hours = {k: round(v / 60, 2) for k, v in tag_minutes.items()}
    tags_sorted = sorted(tags_hours.items(), key=lambda kv: kv[1], reverse=True)
    activity_hours = {k: round(v / 60, 2) for k, v in activity_minutes.items() if v > 0}
    activity_sorted = sorted(activity_hours.items(), key=lambda kv: kv[1], reverse=True)
    life_hours = dict(activity_hours)
    life_sorted = list(activity_sorted)

    title_counts = Counter(
        _norm_title_key(e.get("title", ""))
        for e in in_win
        if not e.get("is_allday") and not is_calendar_block(e)
    )
    rhythms = [
        {"title_key": t, "count": c}
        for t, c in title_counts.most_common(12)
        if c >= 2 and t != pdmsg("auto_2cdb199719")
    ]
    busy_days_seq = [1 if x["meeting_minutes"] >= 240 else 0 for x in days_out]
    longest_busy_run = _longest_run(busy_days_seq)
    top_pressure = sorted(pressure_candidates, key=lambda x: -x["minutes"])[:5]
    unclassified_top = sorted(unclassified_candidates, key=lambda x: -x["minutes"])[:8]
    work_h = activity_hours.get(_work_type(), 0)
    work_w = float(_attention_weights().get(_work_type(), 0.45))
    signals = _build_signals(
        totals=totals,
        activity_sorted=activity_sorted,
        work_hours=work_h,
        work_weight=work_w,
        untagged_hours=totals["untagged_hours"],
        evening=evening_events,
        peak=peak,
    )
    upcoming = _upcoming_slots(per_day, anchor, days=2)
    free_windows = _free_windows(per_day, anchor, horizon_days=horizon_days)
    day_markers = _day_markers(per_day, anchor, horizon_days=horizon_days)
    heavy_days = [
        {
            "date": x["date"],
            "weekday": x["weekday"],
            "hours": x["meeting_hours_rounded"],
            "count": x["meeting_count"],
        }
        for x in days_out
        if float(x.get("meeting_hours_rounded") or 0) >= 3.0
    ]
    typed_share = 0.0
    if activity_minutes:
        typed = sum(v for k, v in activity_minutes.items() if k != _default_type())
        typed_share = round(typed / max(1, sum(activity_minutes.values())), 2)

    return {
        "anchor": _day(anchor),
        "horizon_days": horizon_days,
        "days": days_out,
        "totals": totals,
        "tags_hours": tags_hours,
        "tags_top5": tags_sorted[:5],
        "activity_hours": activity_hours,
        "activity_top": activity_sorted[:8],
        "life_hours": life_hours,
        "life_top5": life_sorted[:8],
        "rhythms": rhythms[:8],
        "top_pressure": top_pressure,
        "unclassified_top": unclassified_top,
        "signals": signals,
        "longest_busy_day_streak_ge_4h": longest_busy_run,
        "upcoming": upcoming,
        "free_windows": free_windows,
        "day_markers": day_markers,
        "heavy_days": heavy_days,
        "typed_share": typed_share,
    }


def _build_signals(
    *,
    totals: Dict[str, Any],
    activity_sorted: List[Tuple[str, float]],
    work_hours: float,
    work_weight: float,
    untagged_hours: float,
    evening: int,
    peak: Optional[Dict[str, Any]],
) -> List[str]:
    out: List[str] = []
    if peak and peak.get("meeting_minutes", 0) > 0:
        out.append(
            pdmsg(
                "calendar_signal_peak",
                weekday=peak.get("weekday"),
                date=str(peak.get("date") or "")[5:],
                hours=peak.get("meeting_hours_rounded"),
            )
        )
    if activity_sorted:
        top_t, top_h = activity_sorted[0]
        out.append(pdmsg("calendar_signal_top_type", type=top_t, hours=top_h))
    if work_hours > 0:
        out.append(
            pdmsg(
                "calendar_signal_work",
                invite=work_hours,
                attention=round(work_hours * work_weight, 1),
                weight=work_weight,
            )
        )
    if evening:
        out.append(pdmsg("calendar_signal_evening", count=evening))
    if untagged_hours >= 1:
        out.append(pdmsg("calendar_signal_untagged", hours=untagged_hours))
    attn = totals.get("attention_hours") or 0
    inv = totals.get("invite_hours") or 0
    if inv > 0:
        out.append(pdmsg("calendar_signal_attention_ratio", attention=attn, invite=inv))
    return out[:5]


def daily_meeting_hours_series(
    events: List[Dict],
    *,
    start: date,
    end: date,
) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for ev in events:
        if ev.get("is_cancelled") or ev.get("is_allday"):
            continue
        try:
            d = _parse_day(ev["date"])
        except ValueError:
            continue
        if d < start or d > end:
            continue
        m = _d(ev)
        if not m:
            continue
        typ = classify_activity(ev)
        attn = m * attention_weight_for(ev, typ)
        ds = _day(d)
        bucket = out.setdefault(ds, {"invite_hours": 0.0, "attention_hours": 0.0})
        bucket["invite_hours"] += m / 60.0
        bucket["attention_hours"] += attn / 60.0
    for _ds, bucket in out.items():
        bucket["invite_hours"] = round(bucket["invite_hours"], 2)
        bucket["attention_hours"] = round(bucket["attention_hours"], 2)
        bucket["meeting_hours"] = bucket["attention_hours"]
    return out


def _hm(minutes: int) -> str:
    h, m = divmod(max(0, int(minutes)), 60)
    return f"{h:02d}:{m:02d}"


def _upcoming_slots(
    per_day: Dict[str, List[Dict]],
    anchor: date,
    *,
    days: int = 2,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(days):
        d = anchor + timedelta(days=i)
        ds = _day(d)
        for e in sorted(per_day.get(ds, []), key=lambda x: str(x.get("start") or "")):
            if e.get("is_allday") or e.get("is_cancelled") or is_calendar_block(e):
                continue
            if not _d(e):
                continue
            out.append(
                {
                    "date": ds,
                    "weekday": _WD[d.weekday()],
                    "start": e.get("start"),
                    "end": e.get("end"),
                    "title": (e.get("title") or "").strip() or "—",
                    "activity": classify_activity(e),
                    "hours": round(_d(e) / 60, 2),
                    "is_today": i == 0,
                }
            )
    return out


def _day_markers(
    per_day: Dict[str, List[Dict]],
    anchor: date,
    *,
    horizon_days: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(horizon_days):
        d = anchor + timedelta(days=i)
        ds = _day(d)
        for e in per_day.get(ds, []):
            if e.get("is_cancelled"):
                continue
            if not e.get("is_allday") and not is_calendar_block(e):
                continue
            title = (e.get("title") or "").strip()
            if not title:
                continue
            out.append(
                {
                    "date": ds,
                    "weekday": _WD[d.weekday()],
                    "title": title[:70],
                    "allday": bool(e.get("is_allday")),
                }
            )
    return out[:12]


def _free_windows(
    per_day: Dict[str, List[Dict]],
    anchor: date,
    *,
    horizon_days: int,
    day_start_min: int = 9 * 60,
    day_end_min: int = 18 * 60,
    min_gap_min: int = 90,
) -> List[Dict[str, Any]]:
    """Contiguous free gaps in the working day (default 09:00-18:00, >=90 min)."""
    out: List[Dict[str, Any]] = []
    for i in range(min(horizon_days, 7)):
        d = anchor + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        ds = _day(d)
        intervals: List[Tuple[int, int]] = []
        for e in per_day.get(ds, []):
            if e.get("is_allday") or e.get("is_cancelled") or is_calendar_block(e):
                continue
            if not _d(e):
                continue
            try:
                t0 = datetime.strptime(e["start"], "%H:%M")
                t1 = datetime.strptime(e["end"], "%H:%M")
                a = max(day_start_min, t0.hour * 60 + t0.minute)
                b = min(day_end_min, t1.hour * 60 + t1.minute)
                if b > a:
                    intervals.append((a, b))
            except (ValueError, KeyError):
                continue
        intervals.sort()
        merged: List[Tuple[int, int]] = []
        for a, b in intervals:
            if not merged or a > merged[-1][1]:
                merged.append((a, b))
            else:
                la, lb = merged[-1]
                merged[-1] = (la, max(lb, b))
        cursor = day_start_min
        gaps: List[Tuple[int, int]] = []
        for a, b in merged:
            if a > cursor and a - cursor >= min_gap_min:
                gaps.append((cursor, a))
            cursor = max(cursor, b)
        if day_end_min - cursor >= min_gap_min:
            gaps.append((cursor, day_end_min))
        for a, b in gaps[:3]:
            out.append(
                {
                    "date": ds,
                    "weekday": _WD[d.weekday()],
                    "start": _hm(a),
                    "end": _hm(b),
                    "hours": round((b - a) / 60, 1),
                }
            )
    return out[:10]


def _longest_run(bits: List[int]) -> int:
    best = cur = 0
    for b in bits:
        if b:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _max_busy_span_minutes(timed: List[Dict]) -> int:
    if not timed:
        return 0
    intervals: List[Tuple[int, int]] = []
    for e in timed:
        try:
            t0 = datetime.strptime(e["start"], "%H:%M")
            t1 = datetime.strptime(e["end"], "%H:%M")
            a = t0.hour * 60 + t0.minute
            b = t1.hour * 60 + t1.minute
            if b > a:
                intervals.append((a, b))
        except (ValueError, KeyError):
            continue
    if not intervals:
        return 0
    intervals.sort()
    merged: List[Tuple[int, int]] = []
    for a, b in intervals:
        if not merged or a > merged[-1][1]:
            merged.append((a, b))
        else:
            la, lb = merged[-1]
            merged[-1] = (la, max(lb, b))
    return max(b - a for a, b in merged)


def analytics_stable_hash(analytics: Dict[str, Any]) -> str:
    payload = json.dumps(analytics, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def write_analytics_json(path: Path, analytics: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(analytics, f, ensure_ascii=False, indent=2)
