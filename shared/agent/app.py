"""AgentApp — unified agent entry point for all domains.

Enables single-bot mode: process registers one or more DomainAdapter instances;
`AgentApp.answer(domain, ...)` assembles context, memory, tools and runs agent loop.
In three-bot mode each process registers one adapter; in single-bot — all three,
domain chosen by L1.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from shared.agent.core import run_agent
from shared.agent.router import ModelRouter
from shared.agent.tools import ToolRegistry
from shared.agent.progress import AgentProgress, NullAgentProgress
from shared.agent.types import AgentAnswer, AgentContext, KB_MEDIA_EXTRAS_KEY, ModelRole
from shared.llm import LLMClient
from shared.memory.base import MemoryLayer, build_system_prompt
from shared.memory.session import append_turn, history_as_api

log = logging.getLogger("shared.agent.app")


class DomainAdapter:
    """Domain contract for AgentApp. Domain bots inherit and override methods."""

    domain: str = "general"
    role: ModelRole = ModelRole.ANALYZE

    def build_registry(self) -> ToolRegistry:
        raise NotImplementedError

    async def base_prompt(self, ctx: AgentContext) -> str:
        """Domain system prompt (memory blocks added by AgentApp)."""
        return ""

    def memory_layers(self, ctx: AgentContext) -> list[MemoryLayer]:
        return []

    async def prepare_extras(self, user_id: int) -> dict:
        """Services/identifiers tools read from ctx.extras."""
        return {}

    async def try_fast_answer(self, ctx: AgentContext) -> AgentAnswer | None:
        """Fast path without tool-select (override in domain adapter)."""
        return None


class AgentApp:
    @staticmethod
    def _no_answer_text() -> str:
        from shared.i18n import msg

        return msg("agent", "no_answer")

    def __init__(self, llm: LLMClient, adapters: list[DomainAdapter]) -> None:
        self._llm = llm
        self._router = ModelRouter(llm)
        self._adapters: dict[str, DomainAdapter] = {a.domain: a for a in adapters}
        self._registries: dict[str, ToolRegistry] = {}

    def domains(self) -> list[str]:
        return list(self._adapters.keys())

    def has_domain(self, domain: str) -> bool:
        return domain in self._adapters

    def _registry(self, domain: str) -> ToolRegistry:
        if domain not in self._registries:
            self._registries[domain] = self._adapters[domain].build_registry()
        return self._registries[domain]

    def merged_registry(self) -> ToolRegistry:
        """All tools from registered domains (for unified host)."""
        if "_merged" not in self._registries:
            merged = ToolRegistry()
            for dom in self.domains():
                reg = self._registry(dom)
                for name in reg.names():
                    if name in merged.names():
                        # memory-tools are identical across domains (attach_memory_tools)
                        if merged.get(name).handler is reg.get(name).handler:
                            continue
                        raise ValueError(f"duplicate tool name across domains: {name}")
                    merged._tools[name] = reg._tools[name]
            self._registries["_merged"] = merged
        return self._registries["_merged"]

    async def answer(
        self,
        domain: str,
        user_id: int,
        question: str,
        *,
        agent_progress: AgentProgress | None = None,
    ) -> AgentAnswer:
        adapter = self._adapters.get(domain)
        if adapter is None:
            raise KeyError(f"domain not registered: {domain}")

        extras = await adapter.prepare_extras(user_id)
        extras.setdefault("telegram_id", user_id)
        extras.setdefault(KB_MEDIA_EXTRAS_KEY, [])
        if agent_progress is not None:
            extras["agent_progress"] = agent_progress

        ctx = AgentContext(
            user_id=user_id,
            domain=domain,
            question=question,
            system_prompt="",
            history=history_as_api(user_id, domain),
            extras=extras,
        )
        ctx.system_prompt = await build_system_prompt(
            await adapter.base_prompt(ctx), ctx, adapter.memory_layers(ctx)
        )

        fast = await adapter.try_fast_answer(ctx)
        if fast is not None:
            if fast.text:
                append_turn(user_id, domain, "user", question)
                append_turn(user_id, domain, "assistant", fast.text)
            return fast

        answer_text = await run_agent(
            ctx,
            self._registry(domain),
            self._router,
            role=adapter.role,
            agent_progress=agent_progress or NullAgentProgress(),
        )
        media = list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or [])
        if answer_text:
            append_turn(user_id, domain, "user", question)
            append_turn(user_id, domain, "assistant", answer_text)
        return AgentAnswer(
            text=answer_text or self._no_answer_text(),
            media_files=media,
        )

    async def answer_unified(
        self,
        user_id: int,
        question: str,
        *,
        agent_progress: AgentProgress | None = None,
    ) -> AgentAnswer:
        """Single agent loop with all domain tools (host / cross-domain)."""
        extras: dict = {"telegram_id": user_id}
        for dom in ("finance", "planning", "knowledge"):
            adapter = self._adapters.get(dom)
            if adapter:
                extras.update(await adapter.prepare_extras(user_id))
        extras.setdefault(KB_MEDIA_EXTRAS_KEY, [])
        if agent_progress is not None:
            extras["agent_progress"] = agent_progress

        ctx = AgentContext(
            user_id=user_id,
            domain="unified",
            question=question,
            system_prompt="",
            history=history_as_api(user_id, "unified"),
            extras=extras,
        )
        ctx.system_prompt = await self._unified_system_prompt(ctx)
        registry = self.merged_registry()

        answer_text = await run_agent(
            ctx,
            registry,
            self._router,
            role=ModelRole.ANALYZE,
            agent_progress=agent_progress or NullAgentProgress(),
        )
        media = list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or [])
        if answer_text:
            append_turn(user_id, "unified", "user", question)
            append_turn(user_id, "unified", "assistant", answer_text)
        return AgentAnswer(text=answer_text or self._no_answer_text(), media_files=media)

    async def _unified_system_prompt(self, ctx: AgentContext) -> str:
        from shared.agent.platform_config import agent_config_dir
        from shared.i18n import msgf
        from shared.prompts import load_prompt
        from shared.tz import now_in_tz

        base = load_prompt(agent_config_dir(), "host_query", subdir="prompts", required=True)
        now = now_in_tz()
        date_hint = msgf("agent", "date_hint", date=now.strftime("%Y-%m-%d (%A)"))
        followup = msgf("agent", "host_followup_hint")
        layers: list[MemoryLayer] = []
        for adapter in self._adapters.values():
            layers.extend(adapter.memory_layers(ctx))
        return await build_system_prompt(
            f"{base}\n\n{date_hint}\n\n{followup}", ctx, layers
        )


def build_app(llm: LLMClient, *adapters: DomainAdapter) -> AgentApp:
    return AgentApp(llm, list(adapters))
