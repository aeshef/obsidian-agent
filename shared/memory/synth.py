"""Memory Synthesizer: LLM extracts pattern candidates from period context.

Domain-agnostic engine: bot passes context text (history + N-day aggregates),
synth makes one JSON LLM call and accumulates candidates in InsightsStore with
confirmation threshold. Those reaching threshold are returned for user verification push.
"""
from __future__ import annotations

import json
import logging
import os

from shared.agent.config import agent_config_dir
from shared.llm import LLMClient
from shared.memory.insights import InsightsStore, get_store
from shared.prompts import load_prompt

log = logging.getLogger("shared.memory.synth")


def _synth_system_prompt() -> str:
    return load_prompt(agent_config_dir(), "memory_synth", subdir="prompts", required=True)


def synth_enabled() -> bool:
    return os.environ.get("SYNTH_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


async def synthesize(
    llm: LLMClient,
    domain: str,
    user_id: int,
    context_text: str,
    *,
    model: str | None = None,
    store: InsightsStore | None = None,
) -> list[tuple[int, str]]:
    """One synth run. Returns [(pending_id, pattern_text)] that reached threshold."""
    import asyncio

    if not context_text.strip():
        return []

    from shared.agent.config import load_models_config

    analyze = (load_models_config().get("roles") or {}).get("analyze") or {}
    try:
        synth_temp = float(analyze.get("temperature", 0.2))
    except (TypeError, ValueError):
        synth_temp = 0.2

    try:
        result = await asyncio.to_thread(
            llm.chat_json_messages,
            [
                {"role": "system", "content": _synth_system_prompt()},
                {"role": "user", "content": context_text},
            ],
            model=model,
            temperature=synth_temp,
        )
    except Exception as e:
        log.warning("synthesize LLM call failed: %s", e)
        return []

    patterns = result.get("patterns") if isinstance(result, dict) else None
    if not isinstance(patterns, list):
        return []
    clean = [str(p).strip() for p in patterns if str(p).strip()]
    if not clean:
        return []

    st = store or get_store()
    st.prune_expired()
    pushable = st.record_candidates(user_id, domain, clean)
    log.info(
        "synth domain=%s user=%s candidates=%d pushable=%d", domain, user_id, len(clean), len(pushable)
    )
    return pushable
