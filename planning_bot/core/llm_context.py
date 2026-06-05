"""Inline LLM context fragments (locale text in prompts/llm_context, not in .py)."""
from __future__ import annotations

from functools import lru_cache

from planning_bot.core.settings import get_config_path, load_prompt


@lru_cache(maxsize=64)
def lctx(name: str) -> str:
    return load_prompt(get_config_path(), name, subdir="prompts/llm_context")
