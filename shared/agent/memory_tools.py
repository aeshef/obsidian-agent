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
    lines = [
        f"{m.role} [{m.ts or 'time_unknown'}]: {(m.content or '')[:400]}"
        for m in hist
    ]
    header = dmsg("memory_tools", "history_header", dom=dom, count=len(lines))
    if dom != ctx.domain:
        header += dmsg("memory_tools", "history_from_domain", domain=ctx.domain)
    return header + "\n" + "\n".join(lines)


@tool(category="memory")
async def capture_observation(
    ctx: AgentContext,
    text: str,
    kind: str = "durable",
    domain: str = "",
) -> str:
    """Remember a short observation for later (pending insight). kind=durable|periodic. domain defaults to current."""
    from shared.memory.insights import get_store

    body = (text or "").strip()
    if not body:
        return dmsg("memory_tools", "capture_empty")
    if len(body) > 500:
        body = body[:500]
    dom = (domain or ctx.domain or "finance").strip().lower()
    if dom not in AGENT_DOMAINS and dom != GLOBAL_DOMAIN:
        dom = ctx.domain
    k = (kind or "durable").strip().lower()
    if k not in ("durable", "periodic"):
        k = "durable"
    store = get_store()
    pushable = store.record_candidates(
        ctx.user_id,
        dom,
        [{"text": body, "kind": k}],
        evidence="agent_capture",
    )
    pending = store.list_pending(ctx.user_id, dom)
    match = next((p for p in pending if (p.get("pattern_text") or "") == body), None)
    pid = match.get("id") if match else (pushable[0][0] if pushable else None)
    # Explicit user capture via tool = confirm immediately (unlike background synth).
    if pid and not pushable:
        store.confirm(int(pid))
        return dmsg("memory_tools", "capture_ready", id=pid, domain=dom, text=body)
    if pushable:
        # Threshold already reached — confirm now so it sticks without a second UI step.
        store.confirm(int(pushable[0][0]))
        return dmsg(
            "memory_tools",
            "capture_ready",
            id=pushable[0][0],
            domain=dom,
            text=body,
        )
    return dmsg(
        "memory_tools",
        "capture_pending",
        id=pid or "-",
        domain=dom,
        text=body,
        count=(match or {}).get("confirmations", 1),
    )


@tool(category="memory")
async def list_pending_observations(ctx: AgentContext, domain: str = "") -> str:
    """List pending memory observations awaiting confirm/reject."""
    from shared.memory.insights import get_store

    dom = (domain or "").strip().lower() or None
    if dom and dom not in AGENT_DOMAINS and dom != GLOBAL_DOMAIN:
        return dmsg(
            "memory_tools",
            "unknown_domain",
            dom=dom,
            allowed=", ".join(AGENT_DOMAINS),
        )
    rows = get_store().list_pending(ctx.user_id, dom)
    if not rows:
        return dmsg("memory_tools", "pending_empty")
    lines = [dmsg("memory_tools", "pending_header", count=len(rows))]
    for r in rows[:20]:
        lines.append(
            dmsg(
                "memory_tools",
                "pending_item",
                id=r.get("id"),
                domain=r.get("domain"),
                kind=r.get("kind") or "durable",
                count=r.get("confirmations") or 1,
                text=(r.get("pattern_text") or "")[:200],
            )
        )
    return "\n".join(lines)


@tool(category="memory")
async def confirm_observation(ctx: AgentContext, pending_id: int) -> str:
    """Confirm a pending observation by id (from list_pending_observations)."""
    from shared.memory.insights import get_store

    try:
        pid = int(pending_id)
    except (TypeError, ValueError):
        return dmsg("memory_tools", "bad_pending_id")
    ok = get_store().confirm(pid)
    return dmsg("memory_tools", "confirm_ok" if ok else "confirm_fail", id=pid)


@tool(category="memory")
async def reject_observation(ctx: AgentContext, pending_id: int) -> str:
    """Reject a pending observation by id."""
    from shared.memory.insights import get_store

    try:
        pid = int(pending_id)
    except (TypeError, ValueError):
        return dmsg("memory_tools", "bad_pending_id")
    ok = get_store().reject(pid)
    return dmsg("memory_tools", "reject_ok" if ok else "reject_fail", id=pid)


@tool(category="memory")
async def list_working_set(ctx: AgentContext) -> str:
    """Show short-lived follow-up context (categories, dates, notes, pinned entities)."""
    from shared.memory.working_set import get_working_set

    text = get_working_set(ctx.user_id, ctx.domain).format()
    return text or dmsg("memory_tools", "working_set_empty")


@tool(category="memory")
async def pin_working_set(
    ctx: AgentContext,
    value: str,
    kind: str = "entities",
) -> str:
    """Pin a follow-up entity. kind=categories|dates|notes|entities, or a free prefix (chart, task, …)."""
    from shared.memory.working_set import pin_entity

    body = (value or "").strip()
    if not body:
        return dmsg("memory_tools", "working_set_pin_empty")
    ws = pin_entity(ctx.user_id, ctx.domain, kind or "entities", body)
    return dmsg("memory_tools", "working_set_pin_ok", kind=kind or "entities", value=body) + (
        "\n" + ws.format() if ws.format() else ""
    )


@tool(category="memory")
async def clear_working_set_items(
    ctx: AgentContext,
    kind: str = "",
    value: str = "",
) -> str:
    """Clear working-set items. Omit kind to clear all for this domain; kind alone clears that bucket; kind+value clears one item."""
    from shared.memory.working_set import clear_entities

    clear_entities(ctx.user_id, ctx.domain, kind=kind or "", value=value or "")
    return dmsg(
        "memory_tools",
        "working_set_cleared",
        kind=kind or "*",
        value=value or "*",
    )


@tool(category="memory")
async def propose_profile_append(ctx: AgentContext, text: str) -> str:
    """Propose a short bullet for user_profile.md (Agent notes). Does NOT write until confirm_profile_append."""
    from shared.memory.profile_append import propose

    pid, body = propose(ctx.user_id, text)
    if pid is None:
        return dmsg("memory_tools", "profile_append_empty")
    return dmsg("memory_tools", "profile_append_pending", id=pid, text=body)


@tool(category="memory")
async def confirm_profile_append(ctx: AgentContext, pending_id: int) -> str:
    """Confirm a pending profile append by id (from propose_profile_append)."""
    from shared.memory.profile_append import confirm

    try:
        pid = int(pending_id)
    except (TypeError, ValueError):
        return dmsg("memory_tools", "profile_append_bad_id")
    ok, name = confirm(ctx.user_id, pid)
    return dmsg(
        "memory_tools",
        "profile_append_ok" if ok else "profile_append_fail",
        id=pid,
        path=name or "-",
    )


@tool(category="memory")
async def reject_profile_append(ctx: AgentContext, pending_id: int) -> str:
    """Reject a pending profile append by id."""
    from shared.memory.profile_append import reject

    try:
        pid = int(pending_id)
    except (TypeError, ValueError):
        return dmsg("memory_tools", "profile_append_bad_id")
    ok = reject(ctx.user_id, pid)
    return dmsg(
        "memory_tools",
        "profile_append_rejected" if ok else "profile_append_fail",
        id=pid,
    )

