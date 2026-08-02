"""Cheap heuristic domain router — skip LLM for high-confidence single-domain phrases."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from functools import lru_cache

from shared.agent.config import load_routing_config

log = logging.getLogger("shared.agent.cheap_router")

# Fallbacks when routing.yaml omits cheap_router patterns.
_DEFAULTS: dict[str, tuple[str, ...]] = {
    "finance": (
        r"\bбаланс\b",
        r"\bсколько\s+потрат",
        r"\bтрат[аы]?\b",
        r"\bрасход",
        r"\bподписк",
        r"\bдолг",
        r"\bbalance\b",
        r"\bspending\b",
    ),
    "planning": (
        r"\bканбан\b",
        r"\bзадач",
        r"\bкалендар",
        r"\bрутин",
        r"\bkanban\b",
        r"\btasks?\b",
        r"\bcalendar\b",
    ),
    "knowledge": (
        r"\bв\s+базе\b",
        r"\bнайди\s+заметк",
        r"\bknowledge\b",
        r"\bnote\b",
        r"\bvault\b",
    ),
}


@lru_cache(maxsize=1)
def _domain_patterns() -> dict[str, re.Pattern[str]]:
    host = load_routing_config().get("host") or {}
    block = host.get("cheap_router") or {}
    out: dict[str, re.Pattern[str]] = {}
    for domain, defaults in _DEFAULTS.items():
        raw = block.get(f"{domain}_patterns") or block.get(domain) or list(defaults)
        if isinstance(raw, str):
            parts = [raw]
        else:
            parts = [str(p) for p in raw if str(p).strip()]
        if not parts:
            continue
        out[domain] = re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)
    return out


def clear_cheap_router_cache() -> None:
    _domain_patterns.cache_clear()


def cheap_route_domain(
    text: str,
    *,
    enabled: Iterable[str],
    cross_domain_check: Callable[[str], bool] | None = None,
) -> str | None:
    """Return a single enabled domain when heuristics are unambiguous, else None.

    Never returns ``unified`` — cross-domain escalation stays with the LLM + safety net.
    """
    t = (text or "").strip()
    if not t:
        return None
    enabled_set = {d for d in enabled if d in ("finance", "planning", "knowledge")}
    if len(enabled_set) < 2:
        return None
    if cross_domain_check is not None and cross_domain_check(t):
        return None

    hits = [d for d, pat in _domain_patterns().items() if d in enabled_set and pat.search(t)]
    if len(hits) != 1:
        return None
    log.info("cheap_router: %s text=%.50s", hits[0], t)
    return hits[0]
