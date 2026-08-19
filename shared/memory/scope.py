"""Normalize insight domain ids for unified host vs domain adapters."""
from __future__ import annotations

from shared.memory.constants import AGENT_DOMAINS, GLOBAL_DOMAIN

_HOST_ALIASES = frozenset({"", "unified", "general", "host", "current", "domain"})


def resolve_insight_domain(raw: str | None, *, fallback: str = GLOBAL_DOMAIN) -> str:
    """Map unified/empty to global; keep finance|planning|knowledge|global."""
    dom = (raw or "").strip().lower()
    if dom in _HOST_ALIASES:
        return fallback
    if dom in AGENT_DOMAINS or dom == GLOBAL_DOMAIN:
        return dom
    return fallback


def insights_scope_for_host(scope: str, current_domain: str) -> str:
    """On unified, scope=current means all domains (there is no unified insights row)."""
    s = (scope or "current").strip().lower() or "current"
    dom = (current_domain or "").strip().lower()
    if s in ("current", "domain", "") and dom not in AGENT_DOMAINS and dom != GLOBAL_DOMAIN:
        return "all"
    return s
