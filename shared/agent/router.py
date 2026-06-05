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
        self._roles = cfg.get("roles") or {}
        defaults = cfg.get("defaults") or {}
        self._default_timeout = float(defaults.get("timeout_sec", 120))
        self._default_tool_choice = str(defaults.get("tool_choice", "auto"))

    def model_for(self, role: ModelRole) -> str:
        return self._model_map.get(role.value, self._model_map.get("analyze", "deepseek-chat"))

    def _role_block(self, role: ModelRole) -> dict:
        block = self._roles.get(role.value) or self._roles.get("analyze") or {}
        return block if isinstance(block, dict) else {}

    def role_temperature(self, role: ModelRole, override: float | None = None) -> float:
        if override is not None:
            return override
        try:
            return float(self._role_block(role).get("temperature", 0.2))
        except (TypeError, ValueError):
            return 0.2

    def role_timeout(self, role: ModelRole, override: float | None = None) -> float:
        if override is not None:
            return override
        try:
            return float(self._role_block(role).get("timeout_sec", self._default_timeout))
        except (TypeError, ValueError):
            return self._default_timeout

    def role_tool_choice(self, role: ModelRole, override: str | None = None) -> str:
        if override is not None:
            return override
        raw = self._role_block(role).get("tool_choice", self._default_tool_choice)
        return str(raw) if raw else self._default_tool_choice

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        role: ModelRole = ModelRole.ANALYZE,
        temperature: float | None = None,
        tool_choice: str | None = None,
        timeout: float | None = None,
        on_text_delta: Any | None = None,
    ) -> LLMResponse:
        model = self.model_for(role)
        temperature = self.role_temperature(role, temperature)
        tool_choice = self.role_tool_choice(role, tool_choice)
        timeout = self.role_timeout(role, timeout)
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
        temperature: float | None = None,
        timeout: float | None = None,
    ) -> str:
        text = await asyncio.to_thread(
            self._llm.chat_messages,
            messages,
            model=self.model_for(role),
            temperature=self.role_temperature(role, temperature),
            timeout=self.role_timeout(role, timeout),
        )
        return text or ""
