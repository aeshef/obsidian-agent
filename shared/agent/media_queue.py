"""Queue vault-relative media onto AgentContext for Telegram delivery."""
from __future__ import annotations

from shared.agent.types import AgentContext, KB_MEDIA_EXTRAS_KEY


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
    """Append (vault_rel, caption) pairs; return how many are queued after merge."""
    if not items:
        return len(list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or []))
    cur = list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or [])
    ctx.extras[KB_MEDIA_EXTRAS_KEY] = merge_media_files(cur, items, max_total=max_total)
    return len(ctx.extras[KB_MEDIA_EXTRAS_KEY])
