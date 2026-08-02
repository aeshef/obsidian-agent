"""Agent tools: list and send dashboard chart PNGs from the vault."""
from __future__ import annotations

from pathlib import Path

from shared.agent.media_queue import queue_vault_media
from shared.agent.tools import tool
from shared.agent.types import AgentContext
from shared.charts_catalog import catalog_charts, format_catalog
from shared.domain_messages import dmsg
from shared.paths import vault_root_optional

_NS = ("chart_tools",)


def _max_send() -> int:
    from shared.agent.platform_config import platform_int

    return max(1, platform_int("agent", "max_charts_per_send", default=4))


@tool(category="charts")
async def list_vault_charts(
    ctx: AgentContext,
    query: str = "",
    family: str = "",
    only_existing: bool = True,
) -> str:
    """List existing dashboard chart PNG files in the vault (not generate). query matches key/filename/family; family filters planning/health/finance/kanban/…"""
    vault = vault_root_optional()
    if vault is None:
        return dmsg(*_NS, "vault_missing")
    entries = catalog_charts(
        vault,
        query=query,
        family=family,
        only_existing=bool(only_existing),
    )
    if not entries:
        return dmsg(*_NS, "none_found", query=query or "-", family=family or "-")
    body = format_catalog(entries)
    return dmsg(*_NS, "list_header", count=len(entries)) + "\n" + body


@tool(category="charts")
async def send_vault_charts(
    ctx: AgentContext,
    query: str = "",
    family: str = "",
    limit: int = 0,
) -> str:
    """Send existing vault dashboard chart PNGs as Telegram photos. Use when the user asks for graphs/charts/pictures. Prefer a specific query; omit query to send a small existing set for family."""
    vault = vault_root_optional()
    if vault is None:
        return dmsg(*_NS, "vault_missing")
    try:
        lim = int(limit) if limit else _max_send()
    except (TypeError, ValueError):
        lim = _max_send()
    lim = max(1, min(lim, _max_send()))

    entries = [
        e
        for e in catalog_charts(
            vault, query=query, family=family, only_existing=True
        )
    ]
    if not entries:
        return dmsg(*_NS, "none_found", query=query or "-", family=family or "-")

    picked = entries[:lim]
    items: list[tuple[str, str]] = []
    for e in picked:
        caption = dmsg(*_NS, "caption", key=e.key, family=e.family)
        items.append((e.rel_path, caption))
    queued = queue_vault_media(ctx, items, max_total=_max_send())
    names = ", ".join(Path(e.rel_path).name for e in picked)
    return dmsg(
        *_NS,
        "send_ok",
        count=len(picked),
        queued=queued,
        names=names,
    )


def attach_chart_tools(registry) -> None:
    """Register chart tools on a domain registry (idempotent)."""
    for fn in (list_vault_charts, send_vault_charts):
        if fn.__name__ not in registry.names():
            registry.register(fn)
