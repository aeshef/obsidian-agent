"""Shared contract for timestamped log dumps (any source).

Every dump that may clip rows must lead with coverage + category shares over
the FULL match. A truncated head/tail is not the start/end of the source.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from shared.domain_messages import dmsg
from shared.query.tally_shares import format_tally, iso_compact, tally_events
from shared.query.ts import dt_gt, dt_lt, parse_iso_dt

_NS = ("log_dump",)


@dataclass
class DumpCoverage:
    requested_start: datetime | None
    requested_end: datetime | None
    n_matched: int
    match_first: datetime | None
    match_last: datetime | None
    n_shown: int
    shown_first: datetime | None
    shown_last: datetime | None
    slice_kind: str = "all"  # all | tail | head


def first_last(ts_list: Sequence[datetime | None]) -> tuple[datetime | None, datetime | None]:
    present = [t for t in ts_list if t is not None]
    if not present:
        return None, None
    return present[0], present[-1]


def coverage_of(
    *,
    requested_start: datetime | None,
    requested_end: datetime | None,
    matched_ts: Sequence[datetime | None],
    shown_ts: Sequence[datetime | None],
    slice_kind: str,
    n_matched: int | None = None,
) -> DumpCoverage:
    mf, ml = first_last(matched_ts)
    sf, sl = first_last(shown_ts)
    n = n_matched if n_matched is not None else len(matched_ts)
    shown_n = len(shown_ts)
    kind = slice_kind if shown_n < n else "all"
    return DumpCoverage(
        requested_start=requested_start,
        requested_end=requested_end,
        n_matched=n,
        match_first=mf,
        match_last=ml,
        n_shown=shown_n,
        shown_first=sf,
        shown_last=sl,
        slice_kind=kind,
    )


def format_coverage(cov: DumpCoverage) -> list[str]:
    start = iso_compact(cov.requested_start) or "-"
    end = iso_compact(cov.requested_end) or "-"
    lines = [
        dmsg(
            *_NS,
            "coverage",
            start=start,
            end=end,
            n=cov.n_matched,
            match_first=iso_compact(cov.match_first) or "-",
            match_last=iso_compact(cov.match_last) or "-",
            shown=cov.n_shown,
            shown_first=iso_compact(cov.shown_first) or "-",
            shown_last=iso_compact(cov.shown_last) or "-",
        )
    ]
    if (
        cov.requested_start is not None
        and cov.match_first is not None
        and dt_gt(cov.match_first, cov.requested_start)
    ):
        lines.append(
            dmsg(
                *_NS,
                "incomplete_start",
                first=iso_compact(cov.match_first),
                requested_start=iso_compact(cov.requested_start),
            )
        )
    if (
        cov.slice_kind == "head"
        and cov.shown_last is not None
        and cov.match_last is not None
        and dt_lt(cov.shown_last, cov.match_last)
    ):
        lines.append(
            dmsg(
                *_NS,
                "incomplete_end",
                last=iso_compact(cov.shown_last),
                requested_end=iso_compact(cov.match_last),
            )
        )
    if cov.slice_kind in ("head", "tail") and cov.n_shown < cov.n_matched:
        lines.append(
            dmsg(
                *_NS,
                "slice_note",
                shown=cov.n_shown,
                total=cov.n_matched,
                kind=cov.slice_kind,
            )
        )
    return [ln for ln in lines if ln]


def events_from_pairs(rows: Iterable[tuple[object, object]]) -> list[tuple[datetime, str]]:
    out: list[tuple[datetime, str]] = []
    for ts, cat in rows:
        dt = ts if isinstance(ts, datetime) else parse_iso_dt(ts)
        label = str(cat or "").strip()
        if dt is None or not label:
            continue
        out.append((dt, label))
    return out


def format_event_shares(
    events: Sequence[tuple[datetime, str]],
    *,
    column: str = "value",
    by_day: bool = False,
    top_n: int = 12,
    top_daily: int = 6,
) -> str:
    if len(events) < 2:
        return ""
    result = tally_events(events, column=column or "value")
    table = format_tally(
        result,
        top_n=top_n,
        by_day=by_day,
        top_daily=top_daily,
        other_label=dmsg(*_NS, "other", default="other"),
    )
    if not table.strip():
        return ""
    header = dmsg(
        *_NS,
        "shares_header",
        column=result.column,
        n=result.events,
        mode=result.mode,
    )
    return header + "\n" + table if header else table


def assemble_log_dump(
    *,
    title: str = "",
    coverage: DumpCoverage | None = None,
    extras: Sequence[str] = (),
    shares: str = "",
    columns: str = "",
    rows: Sequence[str] = (),
) -> str:
    """Coverage and shares first so tool_result_max_chars cannot drop them."""
    parts: list[str] = []
    if (title or "").strip():
        parts.append(title.strip())
    if coverage is not None:
        parts.extend(format_coverage(coverage))
    for extra in extras:
        if (extra or "").strip():
            parts.append(extra.strip())
    if (shares or "").strip():
        parts.append(shares.strip())
    if (columns or "").strip():
        parts.append(columns.strip())
    parts.extend(r for r in rows if r is not None)
    return "\n".join(parts)
