"""Cheap heuristic domain router."""
from __future__ import annotations

from shared.agent.cheap_router import cheap_route_domain, clear_cheap_router_cache


def setup_function():
    clear_cheap_router_cache()


def test_cheap_router_balance():
    assert (
        cheap_route_domain(
            "Какой сейчас баланс?",
            enabled=["finance", "planning", "knowledge"],
        )
        == "finance"
    )


def test_cheap_router_cross_abstains():
    def cross(_t: str) -> bool:
        return True

    assert (
        cheap_route_domain(
            "траты на еду и задачи",
            enabled=["finance", "planning"],
            cross_domain_check=cross,
        )
        is None
    )
