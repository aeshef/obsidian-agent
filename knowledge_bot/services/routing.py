"""Re-export shared routing (knowledge package entry)."""
from __future__ import annotations

from shared.agent.routing import deploy_mode, resolve_domain
from knowledge_bot.services.note_routing import route_and_fill

__all__ = ["deploy_mode", "resolve_domain", "route_and_fill"]
