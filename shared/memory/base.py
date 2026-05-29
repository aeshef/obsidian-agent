"""Assemble system prompt from memory layers."""
from __future__ import annotations

from typing import Protocol

from shared.agent.types import AgentContext, AgentMessage


class MemoryLayer(Protocol):
    async def read(self, ctx: AgentContext) -> str: ...

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None: ...


async def build_system_prompt(base: str, ctx: AgentContext, layers: list[MemoryLayer]) -> str:
    parts = [base.strip()]
    for layer in layers:
        block = (await layer.read(ctx)).strip()
        if block:
            parts.append(block)
    return "\n\n".join(parts)
