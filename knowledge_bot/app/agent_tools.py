"""Knowledge agent tools for shared agent core."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from shared.agent.app import DomainAdapter
from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import AgentContext, AgentAnswer, KB_MEDIA_EXTRAS_KEY, ModelRole
from shared.domain_messages import dmsg

log = logging.getLogger("kb.agent_tools")

KNOWLEDGE_DOMAIN = "knowledge"
_KA = ("knowledge_agent_tools",)


def _max_kb_media() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query",
        "max_media_per_query",
        env="KNOWLEDGE_MAX_MEDIA_PER_QUERY",
        default=6,
    )


def _queue_kb_media(ctx: AgentContext, items: list[tuple[str, str]]) -> None:
    from shared.agent.types import CHART_MEDIA_EXTRAS_KEY, KB_MEDIA_EXTRAS_KEY
    from knowledge_bot.services.query.note_media import merge_media_files

    if not items:
        return
    # Dashboard chart sends win — do not pile note images on top.
    if ctx.extras.get(CHART_MEDIA_EXTRAS_KEY):
        return
    cur = list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or [])
    ctx.extras[KB_MEDIA_EXTRAS_KEY] = merge_media_files(
        cur, items, max_total=_max_kb_media()
    )


def _read_note_max_chars() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query",
        "read_note_max_chars",
        env="KNOWLEDGE_READ_NOTE_MAX_CHARS",
        default=24000,
    )


async def read_note_content(
    ctx: AgentContext, rel: str, *, lookup_query: str | None = None
) -> tuple[str, list[tuple[str, str]]]:
    """Read note from disk; returns (LLM text, media for Telegram)."""
    from knowledge_bot.core.config import load_config
    from knowledge_bot.services.query.brain_query import _safe_note_path, _strip_file_sections
    from knowledge_bot.services.query.note_media import media_from_note_text

    cfg = load_config()
    sp = _safe_note_path(cfg.vault_path, rel)
    if not sp:
        return dmsg(*_KA, "bad_path", rel=rel), []

    try:
        raw = sp.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return dmsg(*_KA, "read_failed", rel=rel, error=e), []

    media = media_from_note_text(raw, rel, cfg.vault_path)
    _queue_kb_media(ctx, media)

    body = _strip_file_sections(raw)
    cap = _read_note_max_chars()
    if len(body) > cap:
        body = body[:cap] + dmsg(*_KA, "truncated")

    media_hint = ""
    if media:
        names = ", ".join(Path(p).name for p, _ in media[:3])
        extra = f" (+{len(media) - 3})" if len(media) > 3 else ""
        media_hint = dmsg(*_KA, "media_hint", count=len(media), names=names, extra=extra)

    title = lookup_query or rel.rsplit("/", 1)[-1]
    if len(body.strip()) < 80:
        text = dmsg(
            *_KA,
            "short_body",
            title=title,
            rel=rel,
            media_hint=media_hint,
            body=body.strip(),
        )
    else:
        text = dmsg(
            *_KA,
            "note_header_full",
            title=title,
            rel=rel,
            media_hint=media_hint,
            body=body.strip(),
        )
    queued = list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or [])
    return text, queued or media


@tool(category="notes", always=True)
async def read_knowledge_note(ctx: AgentContext, note_title: str) -> str:
    """Read one vault note by title or path fragment."""
    from knowledge_bot.core.config import load_config
    from knowledge_bot.services.query.index_builder import build_or_refresh_index, load_index
    from knowledge_bot.services.query.note_lookup import resolve_note_path

    q = (note_title or "").strip()
    if not q:
        return dmsg(*_KA, "note_title_required")

    cfg = load_config()
    build_or_refresh_index(cfg.vault_path, force=False)
    entries = load_index().get("entries") or []
    rel, reason = resolve_note_path(q, entries)
    if not rel:
        return dmsg(*_KA, "note_not_found", reason=reason)

    text, _ = await read_note_content(ctx, rel, lookup_query=q)
    return text


@tool(category="notes", always=True)
async def search_knowledge_base(
    ctx: AgentContext,
    query: str,
    include_media: bool = False,
) -> str:
    """Search Obsidian vault knowledge notes. For dashboard charts use list_vault_charts/send_vault_charts instead. Set include_media=true only when the user wants images from notes."""
    from knowledge_bot.core.config import load_config
    from knowledge_bot.core.llm import LLMClient
    from knowledge_bot.services.query import run_brain_query

    cfg = load_config()
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    uid = int(ctx.extras.get("telegram_id") or ctx.user_id)
    q = (query or ctx.question or "").strip()
    try:
        result = await asyncio.to_thread(
            run_brain_query, cfg.vault_path, cfg.agent_config_path, llm, uid, q
        )
    except Exception as e:
        log.exception("search_knowledge_base failed")
        return dmsg(*_KA, "search_error", error=e)

    text = (result.text or "").strip()
    if not text:
        return dmsg(*_KA, "search_empty")
    err_nf = dmsg(*_KA, "err_prefix_not_found")
    err_empty = dmsg(*_KA, "err_prefix_empty_index")
    err_q = dmsg(*_KA, "err_prefix_empty_question")
    if text.startswith(err_nf) or text.startswith(err_empty) or text.startswith(err_q):
        return dmsg(*_KA, "search_kb_prefix", text=text)
    if include_media:
        _queue_kb_media(ctx, list(result.media_files))
    return text


def build_knowledge_registry() -> ToolRegistry:
    from shared.capabilities.registry import knowledge_module_enabled
    from shared.memory.episodic import attach_memory_tools
    from shared.agent.chart_tools import attach_chart_tools

    reg = ToolRegistry()
    if not knowledge_module_enabled():
        return reg
    from knowledge_bot.app.knowledge_write_tools import append_knowledge_note
    from shared.agent.series_tools import attach_series_tools

    reg.register(read_knowledge_note)
    reg.register(search_knowledge_base)
    reg.register(append_knowledge_note)
    attach_memory_tools(reg)
    attach_chart_tools(reg)
    attach_series_tools(reg)
    return reg


class KnowledgeAdapter(DomainAdapter):
    domain = KNOWLEDGE_DOMAIN
    role = ModelRole.ANALYZE

    def build_registry(self) -> ToolRegistry:
        return build_knowledge_registry()

    async def base_prompt(self, ctx: AgentContext) -> str:
        return dmsg(*_KA, "unified_prompt")

    def memory_layers(self, ctx: AgentContext):
        from shared.memory.layers import build_memory_layers

        return build_memory_layers(KNOWLEDGE_DOMAIN)
