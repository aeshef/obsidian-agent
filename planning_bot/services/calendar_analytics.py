from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple
from planning_bot.core.pdmsg import pdmsg

from functools import lru_cache
from pathlib import Path

from planning_bot.core.config import CATEGORIES
from shared.yaml_config import load_merged_config

_WD = (pdmsg("auto_37a7379e0b"), pdmsg("auto_ef06566baf"), pdmsg("auto_0900d1f798"), pdmsg("auto_3e88f5cb5b"), pdmsg("auto_6da80c2907"), pdmsg("auto_06b0f2a4a5"), pdmsg("auto_8c0f1e0292"))

_CALENDAR_CFG_DIR = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=1)
def _life_rules_config() -> tuple[list[tuple[str, tuple[str, ...]]], str]:
    data = load_merged_config(str(_CALENDAR_CFG_DIR), "calendar_life_sections")
    default = str(data.get("default_section") or pdmsg("auto_d2cb155a7f"))
    rules: list[tuple[str, tuple[str, ...]]] = []
    for item in data.get("rules") or []:
        if not isinstance(item, dict):
            continue
        section = str(item.get("section") or "").strip()
        needles = item.get("needles")
        if section and isinstance(needles, list):
            rules.append((section, tuple(str(n).lower() for n in needles if n)))
    return rules, default


def _life_section(ev: Dict) -> str:
    tag = (ev.get("tag") or "").strip().lower()
    title = (ev.get("title") or "").strip().lower()
    blob = f"{tag} {title}".lower()
    rules, default = _life_rules_config()
    for section, needles in rules:
        if any(n in blob for n in needles):
            return section
    return default


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
    'Operation implementation.'
    end_d = anchor + timedelta(days=horizon_days - 1)
    day_start = anchor
    day_end = end_d

    # (comment)
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
    life_minutes: Counter = Counter()
    evening_events = 0
    late_end_events = 0
    total_timed_minutes = 0

    for i in range(horizon_days):
        d = anchor + timedelta(days=i)
        ds = _day(d)
        day_evs = per_day.get(ds, [])
        timed = [e for e in day_evs if not e.get("is_allday")]
        allday = [e for e in day_evs if e.get("is_allday")]
        mins = sum(_d(e) for e in timed)
        total_timed_minutes += mins

        ev_evening = 0
        ev_late = 0
        for e in timed:
            try:
                sh, sm = map(int, e["start"].split(":"))
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
            tag_minutes[tag] += _d(e)
            sec = _life_section(e)
            if sec not in CATEGORIES and sec != pdmsg("auto_d2cb155a7f"):
                sec = pdmsg("auto_d2cb155a7f")
            life_minutes[sec] += _d(e)

        # (comment)
        frag = 0.0
        if len(timed) >= 3 and mins > 0:
            try:
                slots = sorted(
                    timed,
                    key=lambda e: datetime.strptime(e["start"], "%H:%M"),
                )
                short = 0
                for e in slots:
                    if _d(e) and _d(e) <= 35:
                        short += 1
                frag = round(short / max(1, len(slots)), 2)
            except Exception:
                frag = 0.0

        # (comment)
        merged_span = _max_busy_span_minutes(timed)

        days_out.append(
            {
                "date": ds,
                "weekday": _WD[d.weekday()],
                "weekday_i": d.weekday(),
                "meeting_count": len(timed),
                "allday_count": len(allday),
                "meeting_minutes": mins,
                "meeting_hours_rounded": round(mins / 60, 2),
                "evening_starts_18plus": ev_evening,
                "ends_after_21": ev_late,
                "fragmentation_short_meetings_ratio": frag,
                "max_contiguous_busy_minutes": merged_span,
            }
        )

    heavy = [x for x in days_out if x["meeting_minutes"] >= 300]
    light = [x for x in days_out if 0 < x["meeting_minutes"] < 120]

    totals = {
        "window_meeting_minutes": total_timed_minutes,
        "window_meeting_hours": round(total_timed_minutes / 60, 2),
        "days_with_any_timed_meeting": sum(1 for x in days_out if x["meeting_count"] > 0),
        "heavy_days_ge_5h": len(heavy),
        "light_days_under_2h": len(light),
        "max_single_day_minutes": max((x["meeting_minutes"] for x in days_out), default=0),
        "evening_starts_week": evening_events,
        "ends_after_21_week": late_end_events,
    }

    # (comment)
    tags_hours = {k: round(v / 60, 2) for k, v in tag_minutes.items()}
    tags_sorted = sorted(tags_hours.items(), key=lambda kv: kv[1], reverse=True)

    # (comment)
    life_hours = {k: round(v / 60, 2) for k, v in life_minutes.items() if v > 0}
    life_sorted = sorted(life_hours.items(), key=lambda kv: kv[1], reverse=True)

    # (comment)
    title_counts = Counter(_norm_title_key(e.get("title", "")) for e in in_win if not e.get("is_allday"))
    rhythms = [
        {"title_key": t, "count": c}
        for t, c in title_counts.most_common(12)
        if c >= 2 and t != pdmsg("auto_2cdb199719")
    ]

    busy_days_seq = [1 if x["meeting_minutes"] >= 240 else 0 for x in days_out]
    longest_busy_run = _longest_run(busy_days_seq)

    analytics = {
        "anchor": _day(anchor),
        "horizon_days": horizon_days,
        "days": days_out,
        "totals": totals,
        "tags_hours": tags_hours,
        "tags_top5": tags_sorted[:5],
        "life_hours": life_hours,
        "life_top5": life_sorted[:8],
        "rhythms": rhythms[:8],
        "longest_busy_day_streak_ge_4h": longest_busy_run,
    }
    return analytics


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
    'Operation implementation.'
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
