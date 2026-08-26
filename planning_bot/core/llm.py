"""Planning LLM facade — transport via shared.llm; domain helpers in llm_domain.

Deprecated surface: new code should use ``shared.llm.LLMClient`` directly.
``DeepSeekClient`` remains for legacy planning handlers (parse_task, weekly review).
See docs/ARCHITECTURE.md § Planning LLM facade.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from shared.constants import deepseek_base_url
from shared.llm import LLMClient as _SharedLLMClient

from .config import DEEPSEEK_API_TOKEN, DEEPSEEK_API_URL, DEEPSEEK_MODEL
from .llm_domain import PlanningLLMDomainMixin
from .llm_params import planning_chat_timeout_sec, planning_llm_temperature

logger = logging.getLogger(__name__)


class APITimeoutError(Exception):
    """Raised when the LLM API times out."""

    pass


class DeepSeekClient(PlanningLLMDomainMixin):
    """Legacy name — prefer ``PlanningLLMClient`` / ``shared.llm.LLMClient`` in new code."""

    def __init__(self):
        if not DEEPSEEK_API_TOKEN:
            raise ValueError("DEEPSEEK_API_TOKEN is not set")
        self.api_token = DEEPSEEK_API_TOKEN
        self.api_url = DEEPSEEK_API_URL
        self.model = DEEPSEEK_MODEL
        self._transport = _SharedLLMClient(
            api_key=DEEPSEEK_API_TOKEN,
            base_url=deepseek_base_url(override=DEEPSEEK_API_URL),
            model=DEEPSEEK_MODEL,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float | None = None,
        max_retries: int = 3,
    ) -> str:
        """Chat completion; retries/timeouts delegated to shared.llm.LLMClient."""
        if temperature is None:
            temperature = planning_llm_temperature("recommendations")
        del max_retries
        import requests

        try:
            return self._transport.chat_messages(
                messages,
                temperature=temperature,
                timeout=planning_chat_timeout_sec(),
                raise_on_error=True,
            )
        except requests.exceptions.Timeout as e:
            raise APITimeoutError(str(e)) from e


# Prefer this name in new planning code; DeepSeekClient kept for imports.
PlanningLLMClient = DeepSeekClient
