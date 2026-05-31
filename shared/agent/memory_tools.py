"""Cross-domain memory tools — episodic layer (layer 2) for all sub-assistants."""
from __future__ import annotations

from typing import Optional

from shared.agent.tools import tool
from shared.agent.types import AgentContext
from shared.domain_messages import dmsg
from shared.memory.constants import AGENT_DOMAINS, GLOBAL_DOMAIN
from shared.memory.layers import format_insights_text, read_profile_text
from shared.memory.session import get_history


@tool(category="memory", always=True)
async def get_user_profile(ctx: AgentContext) -> str:
    """Global and domain markdown user profile."""
    return read_profile_text(ctx.domain)


@tool(category="memory")
async def get_user_insights(ctx: AgentContext, scope: str = "current") -> str:
    """Confirmed observations: current (this domain), global, all, or finance/planning/knowledge."""
    return format_insights_text(ctx.user_id, scope=scope, current_domain=ctx.domain)


@tool(category="memory")
async def get_dialogue_history(
    ctx: AgentContext,
    domain: Optional[str] = None,
    limit: int = 6,
) -> str:
    """Recent dialogue turns in domain (finance, planning, knowledge). For cross-topic context."""
    dom = (domain or ctx.domain).strip().lower()
    if dom not in AGENT_DOMAINS:
        return dmsg(
            "memory_tools",
            "unknown_domain",
            dom=dom,
            allowed=", ".join(AGENT_DOMAINS),
        )
    try:
        lim = max(2, min(int(limit), 20))
    except (TypeError, ValueError):
        lim = 6
    hist = get_history(ctx.user_id, dom)[-lim:]
    if not hist:
        return dmsg("memory_tools", "empty_history", dom=dom)
    lines = [f"{m.role}: {(m.content or '')[:400]}" for m in hist]
    header = dmsg("memory_tools", "history_header", dom=dom, count=len(lines))
    if dom != ctx.domain:
        header += dmsg("memory_tools", "history_from_domain", domain=ctx.domain)
    return header + "\n" + "\n".join(lines)
