"""Episodic layer: on-demand history and profile via tools (not in system prompt)."""
from __future__ import annotations

from shared.agent.tools import ToolRegistry

MEMORY_TOOL_NAMES = (
    "get_user_profile",
    "get_user_insights",
    "get_dialogue_history",
)


def attach_memory_tools(registry: ToolRegistry) -> ToolRegistry:
    """Attach shared memory-tools to domain registry."""
    from shared.agent import memory_tools

    for fn in (
        memory_tools.get_user_profile,
        memory_tools.get_user_insights,
        memory_tools.get_dialogue_history,
    ):
        if fn.__name__ not in registry.names():
            registry.register(fn)
    return registry
