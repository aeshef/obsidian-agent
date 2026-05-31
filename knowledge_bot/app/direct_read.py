"""Прямое чтение заметки по названию в запросе (минуя LLM tool-select)."""
from __future__ import annotations

import logging

from shared.agent.types import AgentAnswer, AgentContext, KB_MEDIA_EXTRAS_KEY

log = logging.getLogger("kb.direct_read")

_DIRECT_READ_MIN_SCORE = 80


async def try_direct_note_answer(ctx: AgentContext) -> AgentAnswer | None:
    from knowledge_bot.app.agent_tools import read_note_content
    from knowledge_bot.core.config import load_config
    from knowledge_bot.services.query.index_builder import build_or_refresh_index, load_index
    from knowledge_bot.services.query.note_lookup import best_note_path_for_message

    cfg = load_config()
    build_or_refresh_index(cfg.vault_path, force=False)
    entries = load_index().get("entries") or []
    rel, score = best_note_path_for_message(
        ctx.question, entries, min_score=_DIRECT_READ_MIN_SCORE
    )
    if not rel:
        return None

    log.info("direct read note: %s (score=%s) question=%.60s", rel, score, ctx.question)
    text, media = await read_note_content(ctx, rel)
    return AgentAnswer(text=text, media_files=media)
