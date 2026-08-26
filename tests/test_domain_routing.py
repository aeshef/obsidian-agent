"""Config-driven domain dispatch order."""
from __future__ import annotations

from unified_bot.host.domain_routing import (
    auto_menu_match_enabled,
    clear_domain_routing_cache,
    domain_routing_order,
)


def test_domain_routing_default_order():
    clear_domain_routing_cache()
    assert domain_routing_order() == ("finance", "planning", "knowledge")


def test_auto_menu_match_enabled_defaults_true():
    clear_domain_routing_cache()
    for domain in ("finance", "planning", "knowledge"):
        assert auto_menu_match_enabled(domain) is True
