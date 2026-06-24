"""Layer stack helpers — format insights and profile text for memory tools."""
from __future__ import annotations

from shared.domain_messages import dmsg
from shared.memory.config import domain_profile_path, global_profile_path, profile_header
from shared.memory.constants import GLOBAL_DOMAIN
from shared.memory.insight_format import normalize_kind
from shared.memory.insights import GlobalInsightsMemory, InsightsMemory
from shared.memory.profile import ProfileMemory


def build_memory_layers(domain: str) -> list:
    """Layer 0 (global + domain profile) + layer 5 (global + domain insights).

    Layer 1 (session) and layer 2 (episodic) wired in AgentApp and memory-tools.
    """
    layers: list = []

    gp = global_profile_path()
    if gp.exists():
        layers.append(ProfileMemory(gp, header=profile_header("global")))

    dp = domain_profile_path(domain)
    if dp is not None and dp.exists():
        layers.append(ProfileMemory(dp, header=profile_header(domain)))

    layers.append(GlobalInsightsMemory())
    layers.append(InsightsMemory(domain))
    return layers


def read_profile_text(domain: str) -> str:
    """Profile text for episodic tool (global + domain)."""
    parts: list[str] = []
    gp = global_profile_path()
    if gp.exists():
        try:
            text = gp.read_text(encoding="utf-8").strip()
            if text:
                parts.append(f"{profile_header('global')}\n{text}")
        except OSError:
            pass
    dp = domain_profile_path(domain)
    if dp is not None and dp.exists():
        try:
            text = dp.read_text(encoding="utf-8").strip()
            if text:
                parts.append(f"{profile_header(domain)}\n{text}")
        except OSError:
            pass
    return "\n\n".join(parts) if parts else dmsg("memory_layers", "profile_unset")


def format_insights_text(
    user_id: int,
    *,
    scope: str = "current",
    current_domain: str = "finance",
) -> str:
    from shared.memory.config import insight_limits
    from shared.memory.constants import AGENT_DOMAINS
    from shared.memory.insights import get_store

    g_lim, d_lim = insight_limits()
    store = get_store()
    scope = (scope or "current").strip().lower()

    def _block(title: str, items: list[str]) -> str:
        if not items:
            return ""
        return f"{title}\n" + "\n".join(items)

    def _formatted(domain: str, limit: int) -> list[str]:
        if limit <= 0:
            return []
        return store.format_confirmed_for_prompt(user_id, domain, limit=limit)

    if scope == "all":
        chunks: list[str] = []
        if g_lim:
            chunks.append(
                _block(
                    dmsg("memory_layers", "global_prefix"),
                    _formatted(GLOBAL_DOMAIN, g_lim),
                )
            )
        for dom in AGENT_DOMAINS:
            if d_lim:
                chunks.append(_block(f"[{dom}]:", _formatted(dom, d_lim)))
        body = "\n\n".join(c for c in chunks if c)
        return body or dmsg("memory_layers", "no_confirmed")

    if scope == "global":
        items = _formatted(GLOBAL_DOMAIN, g_lim) if g_lim else []
        return _block(dmsg("memory_layers", "global_observations"), items) or dmsg(
            "memory_layers", "no_global"
        )

    dom = current_domain if scope in ("current", "domain", "") else scope
    if dom not in AGENT_DOMAINS and dom != GLOBAL_DOMAIN:
        return dmsg("memory_layers", "unknown_scope", scope=scope)
    items = _formatted(dom, d_lim) if d_lim else []
    confirmed = _block(dmsg("memory_layers", "observations", dom=dom), items) or dmsg(
        "memory_layers", "no_domain_confirmed", dom=dom
    )
    pending = store.list_pending(user_id, dom if scope in ("current", "domain", "") else None)
    if scope in ("current", "domain", ""):
        pending = [p for p in pending if p.get("domain") == dom]
    if pending:
        lines = [
            dmsg(
                "memory_layers",
                "pending_line",
                domain=p.get("domain", "?"),
                text=p.get("pattern_text", ""),
                count=p.get("confirmations", 1),
                date=(p.get("created_at") or "")[:10] or "?",
                kind=normalize_kind(p.get("kind")),
            )
            for p in pending[:8]
        ]
        confirmed += f"\n\n{dmsg('memory_layers', 'pending_header')}\n" + "\n".join(lines)
    return confirmed
