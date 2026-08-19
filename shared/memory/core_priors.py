"""Compact always-on priors (confirmed insights) for the unified host prompt."""
from __future__ import annotations

from shared.agent.types import AgentContext, AgentMessage
from shared.domain_messages import dmsg
from shared.memory.constants import AGENT_DOMAINS, GLOBAL_DOMAIN
from shared.memory.insight_format import KIND_DURABLE, KIND_PERIODIC, normalize_kind
from shared.memory.insights import get_store


def _core_max_lines() -> int:
    from shared.memory.config import load_memory_config

    raw = (load_memory_config().get("core") or {}).get("max_lines", 8)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 8


def collect_core_prior_lines(user_id: int, *, limit: int | None = None) -> list[str]:
    """Durable first, then periodic; across global + all agent domains."""
    cap = _core_max_lines() if limit is None else max(0, int(limit))
    if cap <= 0:
        return []
    store = get_store()
    durable: list[dict] = []
    periodic: list[dict] = []
    per_domain = max(cap, 4)
    for dom in (GLOBAL_DOMAIN, *AGENT_DOMAINS):
        for row in store.read_confirmed_records(user_id, dom, limit=per_domain):
            item = {**row, "domain": dom}
            if normalize_kind(row.get("kind")) == KIND_PERIODIC:
                periodic.append(item)
            else:
                durable.append(item)

    def _key(row: dict) -> str:
        return str(row.get("confirmed_at") or "")

    durable.sort(key=_key, reverse=True)
    periodic.sort(key=_key, reverse=True)
    picked = (durable + periodic)[:cap]
    lines: list[str] = []
    seen: set[str] = set()
    for row in picked:
        text = (row.get("pattern_text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        lines.append(
            dmsg(
                "memory_layers",
                "core_line",
                domain=row.get("domain") or "?",
                kind=normalize_kind(row.get("kind")) or KIND_DURABLE,
                text=text,
            )
        )
    return lines


class CorePriorsMemory:
    """MemoryLayer: short confirmed priors for every unified turn."""

    async def read(self, ctx: AgentContext) -> str:
        lines = collect_core_prior_lines(ctx.user_id)
        if not lines:
            return ""
        return dmsg("memory_layers", "core_header") + "\n" + "\n".join(lines)

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        pass
