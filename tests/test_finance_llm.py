"""finance_bot uses shared.llm transport."""
from __future__ import annotations

from bot.llm import LLMClient
from shared.llm import LLMClient as SharedLLMClient


def test_finance_llm_is_shared_subclass():
    assert issubclass(LLMClient, SharedLLMClient)
