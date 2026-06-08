"""Auto-mode handler registry."""
from __future__ import annotations

from shared.telegram.host.auto_routing import auto_handler_for
from shared.telegram.host.constants import (
    DOMAIN_FINANCE,
    DOMAIN_GENERAL,
    DOMAIN_KNOWLEDGE,
    DOMAIN_PLANNING,
    DOMAIN_UNIFIED,
)


def test_auto_handler_registry():
    assert auto_handler_for(DOMAIN_FINANCE) is auto_handler_for(DOMAIN_FINANCE)
    assert auto_handler_for(DOMAIN_KNOWLEDGE) is not auto_handler_for(DOMAIN_FINANCE)
    assert auto_handler_for("unknown") is auto_handler_for(DOMAIN_UNIFIED)
    for domain in (DOMAIN_FINANCE, DOMAIN_KNOWLEDGE, DOMAIN_GENERAL, DOMAIN_PLANNING, DOMAIN_UNIFIED):
        assert callable(auto_handler_for(domain))
