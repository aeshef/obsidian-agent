"""General series alignment + categorical share tools (compose prior tool dumps)."""
from __future__ import annotations

from shared.agent.loop_context import pick_join_series, pick_tally_source
from shared.agent.tools import tool
from shared.agent.types import LOOP_TOOL_RESULTS_KEY, AgentContext
from shared.domain_messages import dmsg
from shared.query.align_series import align_two_texts
from shared.query.tally_shares import (
    format_tally,
    iso_compact,
    parse_timestamped_categories,
    tally_events,
)

_NS = ("series_tools",)


@tool(category="analytics")
async def align_day_series(
    ctx: AgentContext,
    series_a: str = "",
    series_b: str = "",
    label_a: str = "a",
    label_b: str = "b",
    fill_zero: bool = False,
    limit: int = 60,
) -> str:
    """Align two day→value series on shared ISO dates. Prefer empty series_a/series_b to join the latest tool tables already in this loop. Optional paste of YYYY-MM-DD|value lines. General join helper — not a domain scenario."""
    a = (series_a or "").strip()
    b = (series_b or "").strip()
    la = (label_a or "a").strip() or "a"
    lb = (label_b or "b").strip() or "b"
    if not a or not b:
        picked = pick_join_series(ctx.extras.get(LOOP_TOOL_RESULTS_KEY))
        if not picked:
            return dmsg(*_NS, "empty_input")
        a, b, auto_a, auto_b = picked
        if not (label_a or "").strip():
            la = auto_a
        if not (label_b or "").strip():
            lb = auto_b
        if la == "a":
            la = auto_a
        if lb == "b":
            lb = auto_b
    try:
        lim = max(1, min(int(limit or 60), 120))
    except (TypeError, ValueError):
        lim = 60
    _series, body = align_two_texts(
        a,
        b,
        label_a=la,
        label_b=lb,
        fill_zero=bool(fill_zero),
        limit=lim,
    )
    if not body.strip():
        return dmsg(*_NS, "no_points")
    return dmsg(*_NS, "header") + "\n" + body


@tool(category="analytics")
async def tally_event_shares(
    ctx: AgentContext,
    series: str = "",
    column: str = "",
    by_day: bool = False,
    top_n: int = 12,
) -> str:
    """Shares of a category column over a timestamped log. Prefer empty series to read the latest log dump already in this loop (do not paste thousands of rows). Works for any ts+label table — app, event type, title, etc. Duration-weighted when timestamps have a clock; date-only rows are counted per day. Not a domain scenario."""
    blob = (series or "").strip()
    source = ""
    if not blob:
        picked = pick_tally_source(ctx.extras.get(LOOP_TOOL_RESULTS_KEY))
        if not picked:
            return dmsg(*_NS, "tally_empty")
        source, blob = picked
    events, used = parse_timestamped_categories(blob, column=column)
    if len(events) < 2:
        return dmsg(*_NS, "tally_empty")
    try:
        n = max(3, min(int(top_n or 12), 40))
    except (TypeError, ValueError):
        n = 12
    result = tally_events(events, column=used)
    body = format_tally(
        result,
        top_n=n,
        by_day=bool(by_day),
        other_label=dmsg(*_NS, "tally_other", default="other"),
    )
    if not body.strip():
        return dmsg(*_NS, "tally_empty")
    gap = ""
    if result.median_gap_sec is not None:
        gap = f"{result.median_gap_sec / 60.0:.1f}m"
    lines = [
        dmsg(
            *_NS,
            "tally_header",
            column=result.column,
            mode=result.mode,
            source=source or "series",
        ),
        dmsg(
            *_NS,
            "tally_coverage",
            n=result.events,
            first=iso_compact(result.first),
            last=iso_compact(result.last),
            gap=gap or "-",
        ),
        body,
    ]
    return "\n".join(lines)


def attach_series_tools(registry) -> None:
    if align_day_series.__name__ not in registry.names():
        registry.register(align_day_series)
    if tally_event_shares.__name__ not in registry.names():
        registry.register(tally_event_shares)
