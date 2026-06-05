"""Model routing by role (config-driven)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from shared.agent.config import load_models_config
from shared.agent.types import ModelRole
from shared.llm import LLMClient, LLMResponse

log = logging.getLogger("shared.agent.router")


class ModelRouter:
    def __init__(self, llm: LLMClient, model_map: dict[str, str] | None = None) -> None:
        cfg = load_models_config()
        self._llm = llm
        self._model_map = model_map or cfg.get("model_map") or {}

    def model_for(self, role: ModelRole) -> str:
        return self._model_map.get(role.value, self._model_map.get("analyze", "deepseek-chat"))

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        role: ModelRole = ModelRole.ANALYZE,
        temperature: float = 0.2,
        tool_choice: str = "auto",
        timeout: float = 120.0,
        on_text_delta: Any | None = None,
    ) -> LLMResponse:
        model = self.model_for(role)
        if on_text_delta is not None:
            return await asyncio.to_thread(
                self._llm.chat_with_tools_stream,
                messages,
                tools,
                model=model,
                temperature=temperature,
                tool_choice=tool_choice,
                timeout=timeout,
                on_text_delta=on_text_delta,
            )
        return await asyncio.to_thread(
            self._llm.chat_with_tools,
            messages,
            tools,
            model=model,
            temperature=temperature,
            tool_choice=tool_choice,
            timeout=timeout,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        role: ModelRole = ModelRole.CHAT,
        temperature: float = 0.7,
        timeout: float = 90.0,
    ) -> str:
        text = await asyncio.to_thread(
            self._llm.chat_messages,
            messages,
            model=self.model_for(role),
            temperature=temperature,
            timeout=timeout,
        )
        return text or ""
