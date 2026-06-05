"""Memory layers: session history, profile, insights."""
from __future__ import annotations

from shared.memory.base import MemoryLayer, build_system_prompt
from shared.memory.insights import GlobalInsightsMemory, InsightsMemory
from shared.memory.layers import build_memory_layers, format_insights_text, read_profile_text
from shared.memory.profile import ProfileMemory
from shared.memory.session import (
    SessionMemory,
    append_turn,
    clear_all_history,
    clear_history,
    get_history,
    history_as_api,
)

__all__ = [
    "MemoryLayer",
    "ProfileMemory",
    "InsightsMemory",
    "GlobalInsightsMemory",
    "SessionMemory",
    "build_system_prompt",
    "build_memory_layers",
    "format_insights_text",
    "read_profile_text",
    "get_history",
    "append_turn",
    "clear_history",
    "clear_all_history",
    "history_as_api",
]
