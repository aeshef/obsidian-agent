"""finance_bot LLM — async facade over shared.llm (config from llm_config.yaml + .env)."""
from __future__ import annotations

import asyncio
import os
from typing import Any

from bot.config import get_settings
from bot.config_loader import get_llm_config
from bot.llm_params import llm_max_tokens, llm_temperature, llm_timeout
from shared.constants import deepseek_base_url, deepseek_model
from shared.llm import LLMClient as _SharedLLMClient


class LLMClient(_SharedLLMClient):
    def __init__(self) -> None:
        settings = get_settings()
        llm_cfg = get_llm_config()
        super().__init__(
            api_key=(
                settings.DEEPSEEK_API_KEY
                or settings.DEEPSEEK_API_TOKEN
                or os.environ.get("DEEPSEEK_API_KEY")
                or os.environ.get("DEEPSEEK_API_TOKEN")
            ),
            base_url=deepseek_base_url(
                override=getattr(settings, "DEEPSEEK_BASE_URL", None) or llm_cfg.get("base_url")
            ),
            model=deepseek_model(
                override=getattr(settings, "DEEPSEEK_MODEL", None) or llm_cfg.get("default_model")
            ),
        )

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        kwargs.setdefault("temperature", llm_temperature("text"))
        kwargs.setdefault("timeout", llm_timeout("text"))
        return await asyncio.to_thread(self.chat_messages, messages, **kwargs)

    async def chat_json(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("temperature", llm_temperature("json"))
        kwargs.setdefault("timeout", llm_timeout("json"))
        mt = llm_max_tokens("nlu")
        if mt is not None:
            kwargs.setdefault("max_tokens", mt)
        return await asyncio.to_thread(self.chat_json_messages, messages, **kwargs)
