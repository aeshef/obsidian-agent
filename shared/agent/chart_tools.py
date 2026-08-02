"""Agent tools: list, refresh, and send dashboard chart PNGs from the vault."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from shared.agent.chart_refresh import (
    list_builder_keys,
    match_builder_keys,
    refresh_enabled,
    run_chart_builder,
)
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


def _stale_hours() -> int:
    from shared.agent.platform_config import platform_int

    return max(0, platform_int("agent", "chart_stale_hours", default=48))


def _age_hours(mtime_iso: str) -> float | None:
    if not mtime_iso:
        return None
    try:
        ts = datetime.fromisoformat(mtime_iso.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0)
    except ValueError:
        return None


@tool(category="charts")
async def list_vault_charts(
    ctx: AgentContext,
    query: str = "",
    family: str = "",
    only_existing: bool = True,
) -> str:
    """List existing dashboard chart PNG files in the vault (not generate). query matches key/filename/family; family filters planning/health/finance/kanban/… Includes mtime and stale flag."""
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
    stale_h = _stale_hours()
    body = format_catalog(entries, stale_hours=stale_h)
    stale_n = 0
    if stale_h > 0:
        for e in entries:
            age = _age_hours(e.mtime_iso)
            if e.exists and age is not None and age > stale_h:
                stale_n += 1
    header = dmsg(*_NS, "list_header", count=len(entries))
    if stale_n:
        header += "\n" + dmsg(*_NS, "stale_hint", count=stale_n, hours=stale_h)
    return header + "\n" + body


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


@tool(category="charts")
async def refresh_vault_charts(
    ctx: AgentContext,
    builder: str = "",
    family: str = "",
) -> str:
    """Rebuild dashboard chart PNGs via allowlisted builders (config chart_refresh), then list freshness. Pass builder key or family (finance, planning, kanban, …)."""
    if not refresh_enabled():
        return dmsg(*_NS, "refresh_disabled")
    keys = match_builder_keys(builder=builder, family=family)
    if not keys:
        available = ", ".join(list_builder_keys()) or "-"
        return dmsg(
            *_NS,
            "refresh_unknown",
            builder=builder or "-",
            family=family or "-",
            available=available,
        )
    from shared.agent.platform_config import platform_int

    max_n = max(1, platform_int("chart_refresh", "max_builders_per_call", default=1))
    keys = keys[:max_n]
    vault = vault_root_optional()
    lines: list[str] = []
    ok_n = 0
    for key in keys:
        ok, status = run_chart_builder(key, vault=vault)
        ok_n += int(ok)
        lines.append(status)
    summary = dmsg(*_NS, "refresh_done", ok=ok_n, total=len(keys))
    return summary + "\n" + "\n".join(lines)


def attach_chart_tools(registry) -> None:
    """Register chart tools on a domain registry (idempotent)."""
    for fn in (list_vault_charts, send_vault_charts, refresh_vault_charts):
        if fn.__name__ not in registry.names():
            registry.register(fn)
