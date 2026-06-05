"""Agent routing config (tool_choice policy)."""
from __future__ import annotations

from shared.agent.config import tools_first_iter_domains


def test_tools_first_iter_domains_default():
    domains = tools_first_iter_domains()
    assert "finance" in domains
    assert "planning" in domains
    assert "unified" in domains
