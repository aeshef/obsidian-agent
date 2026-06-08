"""Config-driven domain dispatch order (config/ui_capabilities.yaml → domain_routing)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.telegram.host.constants import (
    DOMAIN_FINANCE,
    DOMAIN_KNOWLEDGE,
    DOMAIN_PLANNING,
)
from shared.yaml_config import load_merged_config

_REPO_CONFIG = Path(__file__).resolve().parents[3] / "config"

_KNOWN_DOMAINS = (DOMAIN_FINANCE, DOMAIN_PLANNING, DOMAIN_KNOWLEDGE)


@lru_cache(maxsize=1)
def _routing_block() -> dict:
    raw = load_merged_config(str(_REPO_CONFIG), "ui_capabilities")
    section = raw.get("domain_routing")
    return section if isinstance(section, dict) else {}


def domain_routing_order() -> tuple[str, ...]:
    """Pinned-domain text dispatch order (finance → planning → knowledge by default)."""
    order = _routing_block().get("order")
    if not isinstance(order, list):
        return _KNOWN_DOMAINS
    out: list[str] = []
    for item in order:
        if isinstance(item, str):
            d = item.strip()
            if d in _KNOWN_DOMAINS and d not in out:
                out.append(d)
    return tuple(out) if out else _KNOWN_DOMAINS


def auto_menu_match_enabled(domain: str) -> bool:
    """When ui_mode=auto, match reply-menu labels for this domain."""
    block = _routing_block().get("auto_menu_match")
    if not isinstance(block, dict):
        return True
    val = block.get(domain)
    return bool(val) if val is not None else True


def clear_domain_routing_cache() -> None:
    _routing_block.cache_clear()
