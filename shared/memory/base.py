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
    from shared.agent_runtime.config import enabled
    if enabled():
        from shared.agent_runtime.context import TaskContextMemory
        from shared.agent.config import agent_config_dir
        from shared.prompts import load_prompt
        parts.append(load_prompt(agent_config_dir(), "architecture_contract", required=True))
        block = await TaskContextMemory().read(ctx)
        if block: parts.append(block)
    return "\n\n".join(parts)
