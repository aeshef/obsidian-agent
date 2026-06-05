"""Knowledge bot LLM — re-export shared client (single implementation)."""
from __future__ import annotations

from shared.llm import LLMClient, LLMResponse, LLMResult

__all__ = ["LLMClient", "LLMResponse", "LLMResult"]
