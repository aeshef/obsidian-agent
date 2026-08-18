"""Agent loop progress callbacks (no tool output leakage to UI)."""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from shared.agent.platform_config import platform_int


def answer_draft_enabled() -> bool:
    """Stream answer via Telegram sendMessageDraft (else edit_message)."""
    if os.environ.get("AGENT_ANSWER_DRAFT", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    if os.environ.get("AGENT_ANSWER_DRAFT", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return platform_int("agent_progress", "answer_draft", default=1) != 0


def answer_stream_enabled() -> bool:
    if os.environ.get("AGENT_ANSWER_STREAM", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    if os.environ.get("AGENT_ANSWER_STREAM", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return platform_int("agent_progress", "answer_stream", default=1) != 0


def agent_progress_enabled() -> bool:
    if os.environ.get("AGENT_PROGRESS", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    if os.environ.get("AGENT_PROGRESS", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return platform_int("agent_progress", "enabled", default=1) != 0


@runtime_checkable
class AgentProgress(Protocol):
    async def on_tools_selected(self, tool_names: list[str]) -> None: ...

    async def on_tool_iteration(self, step: int, tool_names: list[str]) -> None: ...

    async def on_answer_delta(self, text: str) -> None: ...

    async def on_complete(self) -> None: ...

    def answer_delivered_in_chat(self) -> bool: ...


class NullAgentProgress:
    async def on_tools_selected(self, tool_names: list[str]) -> None:
        return

    async def on_tool_iteration(self, step: int, tool_names: list[str]) -> None:
        return

    async def on_loop_model(self, model: str, role: str) -> None:
        return

    async def on_answer_delta(self, text: str) -> None:
        return

    async def on_complete(self) -> None:
        return

    def answer_delivered_in_chat(self) -> bool:
        return False
