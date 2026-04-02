"""Domain routing in multi-bot (fixed AGENT_DOMAIN). Single-bot — LLM only."""
from __future__ import annotations

import logging
import os

from shared.agent.types import Domain

log = logging.getLogger("shared.agent.routing")


def deploy_mode() -> str:
    """Default single (unified_bot); legacy multi-bot sets DEPLOY_MODE=multi."""
    return (os.environ.get("DEPLOY_MODE") or "single").strip().lower()


def resolve_domain(text: str, *, enabled: list[Domain] | None = None) -> Domain:
    """Multi-bot: domain from AGENT_DOMAIN. Single-bot: keyword routing forbidden."""
    if deploy_mode() == "single":
        raise RuntimeError(
            "resolve_domain() is not used in single-bot mode; domain is chosen by classify_host_domain_llm()"
        )
    fixed = (os.environ.get("AGENT_DOMAIN") or "").strip().lower()
    if fixed:
        try:
            return Domain(fixed)
        except ValueError as e:
            raise ValueError(f"unknown AGENT_DOMAIN={fixed!r}") from e
    if enabled:
        return enabled[0]
    raise RuntimeError("AGENT_DOMAIN not set and no enabled domains")
