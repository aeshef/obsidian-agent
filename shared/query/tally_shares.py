"""Categorical shares over timestamped logs (any domain). Not a scenario tool.

Parses TSV/CSV/pipe tables with a timestamp column plus a category column,
then counts and duration-weights consecutive rows (capped gaps so overnight
holes are not attributed to the last value).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Iterable

_HEADER_TS = frozenset({"ts", "timestamp", "time", "datetime", "date", "at"})
_HEADER_CAT = (
    "app",
    "application",
    "name",
    "type",
    "event",
    "event_type",
    "title",
    "category",
    "value",
    "label",
    "focus",
)


@dataclass
class ShareRow:
    value: str
    count: int
    count_share: float
    hours: float
    hour_share: float
    days: int


@dataclass
class TallyResult:
    column: str
    events: int
    first: datetime | None
    last: datetime | None
    median_gap_sec: float | None
    mode: str
    rows: list[ShareRow] = field(default_factory=list)
    daily_hours: dict[str, dict[str, float]] = field(default_factory=dict)


def parse_ts(raw: str) -> datetime | None:
    s = (raw or "").strip().strip("`")
    if not s:
        return None
    s = s.replace(" ", "T", 1)
    for cand in (s[:26], s[:19], s[:16], s[:10]):
        try:
            return datetime.fromisoformat(cand)
        except ValueError:
            continue
    return None


def _split_row(line: str) -> list[str]:
    raw = (line or "").rstrip()
    if "\t" in raw:
        return [c.strip() for c in raw.split("\t")]
    if "|" in raw:
        return [c.strip() for c in raw.split("|") if c.strip() != ""]
    if ";" in raw and raw.count(";") >= 1:
        return [c.strip() for c in raw.split(";")]
    if "," in raw and raw.count(",") >= 1:
        return [c.strip() for c in raw.split(",")]
    return [c for c in raw.split() if c]


def _is_header_cell(cell: str) -> bool:
    t = (cell or "").strip().strip("`").casefold()
    return t in _HEADER_TS or t in {c.casefold() for c in _HEADER_CAT}


def _pick_ts_idx(cells: list[str], header: list[str] | None) -> int | None:
    if header:
        for i, h in enumerate(header):
            if h.casefold().strip("`") in _HEADER_TS:
                return i
    for i, c in enumerate(cells):
        if parse_ts(c) is not None:
            return i
    return None


def _pick_cat_idx(
    cells: list[str],
    header: list[str] | None,
    ts_idx: int,
    column: str,
) -> int | None:
    want = (column or "").strip().casefold()
    if header and want:
        for i, h in enumerate(header):
            if h.casefold().strip("`") == want:
                return i
    if header:
        names = [h.casefold().strip("`") for h in header]
        for cand in _HEADER_CAT:
            if cand in names:
                i = names.index(cand)
                if i != ts_idx:
                    return i
    for i, c in enumerate(cells):
        if i == ts_idx:
            continue
        if not (c or "").strip():
            continue
        if parse_ts(c) is not None:
            continue
        try:
            float((c or "").replace(",", ".").replace("%", ""))
            continue
        except ValueError:
            return i
    return None


def parse_timestamped_categories(
    text: str,
    *,
    column: str = "",
) -> tuple[list[tuple[datetime, str]], str]:
    """Return (ts, category) events and the category column label used."""
    events: list[tuple[datetime, str]] = []
    header: list[str] | None = None
    used = (column or "").strip() or "value"
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("…"):
            continue
        if line.startswith("-") and set(line) <= set("- |=:+"):
            continue
        cells = _split_row(line)
        if len(cells) < 2:
            continue
        if header is None and all(_is_header_cell(c) or not parse_ts(c) for c in cells):
            if any(c.casefold().strip("`") in _HEADER_TS for c in cells) or any(
                c.casefold().strip("`") in _HEADER_CAT for c in cells
            ):
                header = cells
                continue
        ts_idx = _pick_ts_idx(cells, header)
        if ts_idx is None:
            continue
        cat_idx = _pick_cat_idx(cells, header, ts_idx, column)
        if cat_idx is None or cat_idx >= len(cells):
            continue
        ts = parse_ts(cells[ts_idx])
        cat = (cells[cat_idx] or "").strip()
        if ts is None or not cat:
            continue
        if header and not (column or "").strip():
            used = header[cat_idx].strip("`") or used
        events.append((ts, cat))
    events.sort(key=lambda x: x[0])
    return events, used


def _aware_gap(a: datetime, b: datetime) -> float:
    if a.tzinfo is not None and b.tzinfo is None:
        b = b.replace(tzinfo=a.tzinfo)
    elif a.tzinfo is None and b.tzinfo is not None:
        a = a.replace(tzinfo=b.tzinfo)
    return (b - a).total_seconds()


def tally_events(
    events: Iterable[tuple[datetime, str]],
    *,
    column: str = "value",
    max_gap_sec: float = 0.0,
    default_gap_sec: float = 0.0,
) -> TallyResult:
    rows = [(ts, str(val).strip()) for ts, val in events if str(val).strip()]
    if not rows:
        return TallyResult(column=column or "value", events=0, first=None, last=None, median_gap_sec=None, mode="count")
    rows.sort(key=lambda x: x[0])
    gaps: list[float] = []
    for i in range(len(rows) - 1):
        g = _aware_gap(rows[i][0], rows[i + 1][0])
        if g > 0:
            gaps.append(g)
    med = float(median(gaps)) if gaps else None
    cap = float(max_gap_sec) if max_gap_sec and max_gap_sec > 0 else (
        min(max((med or 300.0) * 2.0, 120.0), 1800.0)
    )
    fallback = float(default_gap_sec) if default_gap_sec and default_gap_sec > 0 else (med or 300.0)
    has_clock = any((ts.hour, ts.minute, ts.second) != (0, 0, 0) for ts, _ in rows)
    # Date-only / one-row-per-day series → count mode, no fake multi-hour spans.
    date_only = (not has_clock) or (
        med is not None and med >= 20 * 3600 and len({ts.date() for ts, _ in rows}) >= max(3, len(rows) // 2)
    )
    mode = "count" if date_only else "duration"

    counts: dict[str, int] = defaultdict(int)
    seconds: dict[str, float] = defaultdict(float)
    days_seen: dict[str, set] = defaultdict(set)
    daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for i, (ts, val) in enumerate(rows):
        counts[val] += 1
        days_seen[val].add(ts.date())
        if mode == "count":
            daily[ts.date().isoformat()][val] += 1.0
            continue
        if i + 1 < len(rows):
            gap = min(max(_aware_gap(ts, rows[i + 1][0]), 0.0), cap)
        else:
            gap = min(fallback, cap)
        seconds[val] += gap
        daily[ts.date().isoformat()][val] += gap / 3600.0

    n = len(rows)
    total_sec = sum(seconds.values()) or 1.0
    share_rows = [
        ShareRow(
            value=val,
            count=counts[val],
            count_share=counts[val] / n,
            hours=seconds[val] / 3600.0,
            hour_share=(seconds[val] / total_sec) if mode == "duration" else counts[val] / n,
            days=len(days_seen[val]),
        )
        for val in counts
    ]
    share_rows.sort(key=lambda r: (r.hour_share, r.count), reverse=True)
    return TallyResult(
        column=column or "value",
        events=n,
        first=rows[0][0],
        last=rows[-1][0],
        median_gap_sec=med,
        mode=mode,
        rows=share_rows,
        daily_hours={d: dict(v) for d, v in sorted(daily.items())},
    )


def _fmt_pct(x: float) -> str:
    return f"{100.0 * x:.1f}%"


def _fmt_hours(x: float) -> str:
    if abs(x - round(x)) < 0.05:
        return f"{x:.0f}"
    return f"{x:.2f}"


def format_tally(
    result: TallyResult,
    *,
    top_n: int = 12,
    by_day: bool = False,
    top_daily: int = 6,
    other_label: str = "other",
) -> str:
    if result.events <= 0 or not result.rows:
        return ""
    n = max(1, int(top_n or 12))
    head = result.rows[:n]
    rest = result.rows[n:]
    lines = [
        f"value\tcount\tcount_share\thours\thour_share\tdays",
    ]
    for row in head:
        hours = _fmt_hours(row.hours) if result.mode == "duration" else "-"
        hshare = _fmt_pct(row.hour_share) if result.mode == "duration" else _fmt_pct(row.count_share)
        lines.append(
            f"{row.value}\t{row.count}\t{_fmt_pct(row.count_share)}\t{hours}\t{hshare}\t{row.days}"
        )
    if rest:
        oc = sum(r.count for r in rest)
        oh = sum(r.hours for r in rest)
        od = sum(r.days for r in rest)
        lines.append(
            f"{other_label}\t{oc}\t{_fmt_pct(oc / result.events)}\t"
            f"{_fmt_hours(oh) if result.mode == 'duration' else '-'}\t"
            f"{_fmt_pct(oh / max(sum(r.hours for r in result.rows), 1e-9)) if result.mode == 'duration' else _fmt_pct(oc / result.events)}\t"
            f"{od}"
        )
    if by_day and result.daily_hours:
        top_vals = [r.value for r in head[: max(1, int(top_daily or 6))]]
        lines.append("")
        lines.append("date\t" + "\t".join(top_vals + [other_label]))
        for day, mapping in result.daily_hours.items():
            cells = []
            used = 0.0
            for val in top_vals:
                v = float(mapping.get(val) or 0.0)
                used += v
                cells.append(_fmt_hours(v) if result.mode == "duration" else f"{v:.0f}")
            other = sum(mapping.values()) - used
            cells.append(_fmt_hours(other) if result.mode == "duration" else f"{other:.0f}")
            lines.append(day + "\t" + "\t".join(cells))
    return "\n".join(lines)


def iso_compact(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.date().isoformat()
    return dt.isoformat(timespec="minutes")
