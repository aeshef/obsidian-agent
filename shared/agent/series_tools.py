"""General series alignment tool (compose outputs from other tools)."""
from __future__ import annotations

from shared.agent.tools import tool
from shared.agent.types import AgentContext
from shared.domain_messages import dmsg
from shared.query.align_series import align_two_texts

_NS = ("series_tools",)


@tool(category="analytics")
async def align_day_series(
    ctx: AgentContext,
    series_a: str,
    series_b: str,
    label_a: str = "a",
    label_b: str = "b",
    fill_zero: bool = False,
    limit: int = 60,
) -> str:
    """Align two day→value series on shared ISO dates. Pass tool output tables or lines ``YYYY-MM-DD|value``. General join helper — not a domain scenario."""
    if not (series_a or "").strip() or not (series_b or "").strip():
        return dmsg(*_NS, "empty_input")
    try:
        lim = max(1, min(int(limit or 60), 120))
    except (TypeError, ValueError):
        lim = 60
    _series, body = align_two_texts(
        series_a,
        series_b,
        label_a=(label_a or "a").strip() or "a",
        label_b=(label_b or "b").strip() or "b",
        fill_zero=bool(fill_zero),
        limit=lim,
    )
    if not body.strip():
        return dmsg(*_NS, "no_points")
    return dmsg(*_NS, "header") + "\n" + body


def attach_series_tools(registry) -> None:
    if align_day_series.__name__ not in registry.names():
        registry.register(align_day_series)
