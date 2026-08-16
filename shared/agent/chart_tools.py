"""Agent tools: list, refresh, and send dashboard chart PNGs from the vault."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from shared.agent.chart_refresh import (
    list_builder_keys,
    match_builder_keys,
    refresh_enabled,
    run_chart_builder,
)
from shared.agent.media_queue import queue_chart_media
from shared.agent.tools import tool
from shared.agent.types import AgentContext
from shared.charts_catalog import ChartEntry, catalog_charts, format_catalog
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
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0)


def _query_tokens(query: str) -> list[str]:
    return [t for t in re.split(r"[^\w]+", (query or "").lower()) if len(t) >= 3]


def _token_hit(haystack: str, token: str) -> bool:
    if not token or not haystack:
        return False
    if token in haystack:
        return True
    # Soft morphology: stem prefix (len>=5) matches declined forms in chart titles.
    return len(token) >= 5 and token[:5] in haystack


def score_chart_match(entry: ChartEntry, query: str) -> int:
    """Higher is better. Used to pick the chart the user actually named."""
    tokens = _query_tokens(query)
    if not tokens:
        return 0
    stem = Path(entry.rel_path).stem.lower().replace(" ", "_")
    key = (entry.key or "").lower()
    rel = (entry.rel_path or "").lower()
    fam = (entry.family or "").lower()
    score = 0
    for tok in tokens:
        if _token_hit(stem, tok):
            score += 3
        if _token_hit(key, tok):
            score += 2
        if _token_hit(rel, tok):
            score += 1
        if _token_hit(fam, tok):
            score += 1
    return score


def rank_charts_for_query(entries: list[ChartEntry], query: str) -> list[ChartEntry]:
    q = (query or "").strip()
    if not q:
        return list(entries)
    return sorted(
        entries,
        key=lambda e: (-score_chart_match(e, q), e.family, e.key),
    )


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
    entries = rank_charts_for_query(entries, query)
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


def _recent_chart_keys(ctx: AgentContext) -> list[str]:
    try:
        from shared.memory.working_set import get_working_set

        ws = get_working_set(ctx.user_id, ctx.domain)
        keys: list[str] = []
        for ent in reversed(list(ws.entities.keys())):
            if ent.startswith("chart:"):
                keys.append(ent.split(":", 1)[1])
        return keys
    except Exception:
        return []


def _remember_charts(ctx: AgentContext, entries: list[ChartEntry]) -> None:
    try:
        from shared.memory.working_set import pin_entity

        for e in entries:
            pin_entity(ctx.user_id, ctx.domain, "chart", e.key)
    except Exception:
        pass


@tool(category="charts")
async def send_vault_charts(
    ctx: AgentContext,
    query: str = "",
    family: str = "",
    limit: int = 0,
) -> str:
    """Send existing vault dashboard chart PNGs as Telegram photos. For a named chart use a specific query and limit=1. Do not call search_knowledge_base for dashboard charts — those are vault Analytics PNGs, not knowledge notes."""
    vault = vault_root_optional()
    if vault is None:
        return dmsg(*_NS, "vault_missing")
    # Prefer explicit tool arg; else rank by the user utterance.
    tool_q = (query or "").strip()
    q = tool_q or (ctx.question or "").strip()
    recent_keys = _recent_chart_keys(ctx)
    try:
        lim = int(limit) if limit else (1 if tool_q or recent_keys else _max_send())
    except (TypeError, ValueError):
        lim = 1 if tool_q or recent_keys else _max_send()
    lim = max(1, min(lim, _max_send()))

    entries = [
        e
        for e in catalog_charts(vault, query="", family=family, only_existing=True)
    ]
    if q:
        ranked = rank_charts_for_query(entries, q)
        positive = [e for e in ranked if score_chart_match(e, q) > 0]
        if positive:
            entries = positive
            if not limit:
                lim = 1
        elif tool_q:
            entries = rank_charts_for_query(
                [
                    e
                    for e in catalog_charts(
                        vault, query=tool_q, family=family, only_existing=True
                    )
                ],
                tool_q,
            )
    if recent_keys and (not tool_q or not any(score_chart_match(e, q) > 0 for e in entries)):
        by_key = {e.key: e for e in catalog_charts(vault, only_existing=True)}
        recalled = [by_key[k] for k in recent_keys if k in by_key]
        if recalled:
            entries = recalled
            if not limit:
                lim = 1

    if not entries:
        return dmsg(*_NS, "none_found", query=tool_q or q or "-", family=family or "-")

    picked = entries[:lim]
    items: list[tuple[str, str]] = []
    for e in picked:
        caption = dmsg(*_NS, "caption", key=e.key, family=e.family)
        items.append((e.rel_path, caption))
    queued = queue_chart_media(ctx, items, max_total=_max_send())
    _remember_charts(ctx, picked)
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
