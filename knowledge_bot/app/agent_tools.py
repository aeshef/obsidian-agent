"""Инструменты knowledge для shared agent core.

`search_knowledge_base` оборачивает 3-шаговый LLM-пайплайн brain_query (preselect → select → answer).
Стэндалон knowledge-бот по-прежнему использует
прямой flow (он умеет ещё и отправлять медиа из выбранных заметок); адаптер нужен
для режима single-bot, где knowledge участвует в общем AgentApp наравне с другими.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from shared.agent.app import DomainAdapter
from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import AgentContext, AgentAnswer, KB_MEDIA_EXTRAS_KEY, ModelRole
log = logging.getLogger("kb.agent_tools")

KNOWLEDGE_DOMAIN = "knowledge"


def _max_kb_media() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int(
        "knowledge_query",
        "max_media_per_query",
        env="KNOWLEDGE_MAX_MEDIA_PER_QUERY",
        default=6,
    )


def _queue_kb_media(ctx: AgentContext, items: list[tuple[str, str]]) -> None:
    from shared.agent.types import KB_MEDIA_EXTRAS_KEY
    from knowledge_bot.services.query.note_media import merge_media_files

    if not items:
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
    """Читает заметку с диска; возвращает (текст для LLM/пользователя, media для Telegram)."""
    from knowledge_bot.core.config import load_config
    from knowledge_bot.services.query.brain_query import _safe_note_path, _strip_file_sections
    from knowledge_bot.services.query.note_media import media_from_note_text

    cfg = load_config()
    sp = _safe_note_path(cfg.vault_path, rel)
    if not sp:
        return f"Некорректный путь: {rel}", []

    try:
        raw = sp.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"Не удалось прочитать {rel}: {e}", []

    media = media_from_note_text(raw, rel, cfg.vault_path)
    _queue_kb_media(ctx, media)

    body = _strip_file_sections(raw)
    cap = _read_note_max_chars()
    if len(body) > cap:
        body = body[:cap] + "\n\n… (обрезано, полный текст в vault)"

    media_hint = ""
    if media:
        names = ", ".join(Path(p).name for p, _ in media[:3])
        extra = f" (+{len(media) - 3})" if len(media) > 3 else ""
        media_hint = f"\n\nВложения ({len(media)}): {names}{extra} — отправляю в чат."

    title = lookup_query or rel.rsplit("/", 1)[-1]
    if len(body.strip()) < 80:
        text = (
            f"=== {title} ===\n"
            f"Путь: {rel}\n"
            f"Текста в заметке мало (шаблон или короткий ASR). "
            f"Видео/фото — отдельным сообщением ниже.{media_hint}\n\n{body.strip()}"
        )
    else:
        text = f"=== {title} ===\nПуть: {rel}{media_hint}\n\n{body.strip()}"
    queued = list(ctx.extras.get(KB_MEDIA_EXTRAS_KEY) or [])
    return text, queued or media


@tool(category="notes", always=True)
async def read_knowledge_note(ctx: AgentContext, note_title: str) -> str:
    """Читает одну заметку vault по названию или фрагменту пути (точное открытие после обзора)."""
    from knowledge_bot.core.config import load_config
    from knowledge_bot.services.query.index_builder import build_or_refresh_index, load_index
    from knowledge_bot.services.query.note_lookup import resolve_note_path

    q = (note_title or "").strip()
    if not q:
        return "Укажи название или путь заметки."

    cfg = load_config()
    build_or_refresh_index(cfg.vault_path, force=False)
    entries = load_index().get("entries") or []
    rel, reason = resolve_note_path(q, entries)
    if not rel:
        return f"Заметка не найдена в индексе ({reason}). Попробуй search_knowledge_base."

    text, _ = await read_note_content(ctx, rel, lookup_query=q)
    return text


@tool(category="notes", always=True)
async def search_knowledge_base(ctx: AgentContext, query: str) -> str:
    """Ищет ответ в vault Obsidian (каталог знаний из VAULT_REL_KNOWLEDGE / platform.yaml)."""
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
        return f"Ошибка поиска в базе знаний: {e}"

    text = (result.text or "").strip()
    if not text:
        return "Поиск в базе знаний не вернул результат (пустой ответ пайплайна)."
    if text.startswith("Не нашёл") or text.startswith("Индекс пуст") or text.startswith("Пустой вопрос"):
        return f"Поиск KB: {text}"
    _queue_kb_media(ctx, list(result.media_files))
    return text


def build_knowledge_registry() -> ToolRegistry:
    from shared.capabilities.registry import knowledge_module_enabled
    from shared.memory.episodic import attach_memory_tools

    reg = ToolRegistry()
    if not knowledge_module_enabled():
        return reg
    reg.register(read_knowledge_note)
    reg.register(search_knowledge_base)
    attach_memory_tools(reg)
    return reg


class KnowledgeAdapter(DomainAdapter):
    domain = KNOWLEDGE_DOMAIN
    role = ModelRole.ANALYZE

    def build_registry(self) -> ToolRegistry:
        return build_knowledge_registry()

    async def base_prompt(self, ctx: AgentContext) -> str:
        return (
            "Ты — ассистент по vault Obsidian. Отвечай по-русски, только по результатам инструментов. "
            "Конкретная заметка по названию — read_knowledge_note; обзор темы — search_knowledge_base. "
            "Если search_knowledge_base вернул обзор с путями/заметками — перескажи его, не говори что «ничего не найдено». "
            "Строка «Поиск KB:» — ошибка пайплайна, передай как есть."
        )

    def memory_layers(self, ctx: AgentContext):
        from shared.memory.layers import build_memory_layers

        return build_memory_layers(KNOWLEDGE_DOMAIN)


