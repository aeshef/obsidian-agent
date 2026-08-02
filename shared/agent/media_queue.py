"""Queue vault-relative media onto AgentContext for Telegram delivery.

Charts and knowledge-note media use separate queues so a chart request never
accidentally ships random note images from search_knowledge_base.
"""
from __future__ import annotations

from shared.agent.types import (
    AgentContext,
    CHART_MEDIA_EXTRAS_KEY,
    KB_MEDIA_EXTRAS_KEY,
)


def merge_media_files(
    existing: list[tuple[str, str]],
    new_items: list[tuple[str, str]],
    *,
    max_total: int,
) -> list[tuple[str, str]]:
    seen = {a for a, _ in existing}
    out = list(existing)
    for rel, title in new_items:
        if not rel or rel in seen:
            continue
        seen.add(rel)
        out.append((rel, title))
        if len(out) >= max_total:
            break
    return out


def queue_vault_media(
    ctx: AgentContext,
    items: list[tuple[str, str]],
    *,
    max_total: int = 6,
) -> int:
    """Append knowledge-style media (vault_rel, caption); return queued count."""
    if not items:
        return len(list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or []))
    cur = list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or [])
    ctx.extras[KB_MEDIA_EXTRAS_KEY] = merge_media_files(cur, items, max_total=max_total)
    return len(ctx.extras[KB_MEDIA_EXTRAS_KEY])


def queue_chart_media(
    ctx: AgentContext,
    items: list[tuple[str, str]],
    *,
    max_total: int = 4,
) -> int:
    """Queue dashboard chart PNGs on a dedicated channel (does not merge with KB)."""
    if not items:
        return len(list(ctx.extras.get(CHART_MEDIA_EXTRAS_KEY) or []))
    cur = list(ctx.extras.get(CHART_MEDIA_EXTRAS_KEY) or [])
    ctx.extras[CHART_MEDIA_EXTRAS_KEY] = merge_media_files(
        cur, items, max_total=max_total
    )
    return len(ctx.extras[CHART_MEDIA_EXTRAS_KEY])


def collect_outbound_media(ctx: AgentContext) -> list[tuple[str, str]]:
    """Prefer chart media when present — never mix with KB note attachments."""
    charts = list(ctx.extras.get(CHART_MEDIA_EXTRAS_KEY) or [])
    if charts:
        return charts
    return list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or [])
