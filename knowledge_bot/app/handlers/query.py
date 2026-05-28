from __future__ import annotations

import asyncio
import logging
import time

from aiogram.types import FSInputFile, Message

from knowledge_bot.app.ui import kmsg
from knowledge_bot.core.config import load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.services.query import BrainQueryResult, run_brain_query, split_telegram_chunks
from knowledge_bot.services.query.text_intent import classify_text_intent

from ..state import (
    _MEDIA_GROUPS,
    bulk_record_failed,
    bulk_take_processing_ack,
    get_processing_semaphore,
    is_bulk_ingest,
    main_reply_keyboard,
)
from .media import resolve_incoming_messages
from .modes import try_handle_mode_button
from .note_complete import process_complete


async def handle_brain_query_flow(message: Message, question: str) -> None:
    """Brain query: LLM steps + optional media from matched notes."""
    log = logging.getLogger("kb.bot")
    cfg = load_config()
    uid = message.from_user.id if message.from_user else 0
    proc = None
    try:
        proc = await message.answer(kmsg("searching"))
    except Exception:
        pass
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    try:
        result: BrainQueryResult = await asyncio.to_thread(
            run_brain_query,
            cfg.vault_path,
            cfg.agent_config_path,
            llm,
            uid,
            question,
        )
    except Exception as e:
        log.exception("brain query failed: %s", e)
        result = BrainQueryResult(text=kmsg("query_error", error=e))
    if proc:
        try:
            await proc.delete()
        except Exception:
            pass

    # text chunks
    for chunk in split_telegram_chunks(result.text):
        try:
            await message.answer(chunk)
        except Exception as send_err:
            log.warning("failed to send brain chunk: %s", send_err)

    # media attachments from matched notes
    if result.media_files:
        for file_rel, note_title in result.media_files:
            file_path = cfg.vault_path / file_rel
            if not file_path.is_file():
                log.warning("media file missing: %s", file_path)
                continue
            ext = file_path.suffix.lower()
            try:
                f = FSInputFile(str(file_path))
                if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
                    await message.answer_video(f, caption=note_title)
                elif ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                    await message.answer_photo(f, caption=note_title)
                else:
                    await message.answer_document(f, caption=note_title)
                log.info("sent media: %s", file_rel)
            except Exception as me:
                log.warning("failed to send media %s: %s", file_rel, me)


async def handle_message(message: Message) -> None:
    log = logging.getLogger("kb.bot")
    cfg = load_config()
    if cfg.telegram_user_id and message.from_user and message.from_user.id != cfg.telegram_user_id:
        await message.answer(kmsg("access_denied"))
        return

    # ignore stale messages after bot restart
    if message.date:
        message_age_seconds = time.time() - message.date.timestamp()
        if message_age_seconds > 300:
            log.info("Ignoring old message (age: %.1f seconds, message_id=%d)", message_age_seconds, message.message_id)
            return

    uid = message.from_user.id if message.from_user else 0
    bulk_mode = is_bulk_ingest(uid)

    if message.text and await try_handle_mode_button(message):
        return

    text = message.text or message.caption or ""
    has_media = bool(
        message.photo
        or message.document
        or message.video
        or message.audio
        or message.voice
        or message.video_note
    )

    # route logging for caption-only / text+media
    if message.caption and not message.text:
        log.info(
            "caption-only media (no text field) msg_id=%s content_type=%s",
            message.message_id,
            getattr(message, "content_type", None),
        )
    elif message.text and has_media:
        log.info(
            "text + attachment msg_id=%s content_type=%s",
            message.message_id,
            getattr(message, "content_type", None),
        )

    # plain text: classify query vs new note
    if message.text and not has_media:
        t0 = message.text.strip()
        low = t0.lower().split("@", 1)[0]
        if low in ("/start", "/help", "/bulk"):
            bulk_hint = kmsg("bulk_hint_on") if not bulk_mode else kmsg("bulk_hint_active")
            await message.answer(
                kmsg("ingest_hint") + bulk_hint,
                reply_markup=main_reply_keyboard(bulk_active=bulk_mode),
            )
            return
        if not bulk_mode:
            llm_route = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
            intent = await asyncio.to_thread(
                classify_text_intent, cfg.agent_config_path, llm_route, message.text
            )
            log.info("text intent result: %s (msg_id=%s)", intent, message.message_id)
            if intent == "chat":
                await message.answer(
                    kmsg("greeting"),
                    reply_markup=main_reply_keyboard(bulk_active=bulk_mode),
                )
                return
            if intent == "query":
                await handle_brain_query_flow(message, t0)
                return

    resolved = await resolve_incoming_messages(message, text, log)
    if resolved is None:
        return

    main_message, all_messages, combined_text, media_group_id, use_semaphore = resolved

    log.info(
        "Incoming message len=%d bulk=%s msg_id=%s",
        len(combined_text),
        bulk_mode,
        getattr(main_message, "message_id", None),
    )

    if bulk_mode and bulk_take_processing_ack(uid):
        try:
            await main_message.answer(kmsg("bulk_processing"))
        except Exception:
            pass

    # always serialize heavy pipeline
    semaphore = get_processing_semaphore()
    async with semaphore:
        try:
            await process_complete(
                main_message,
                all_messages,
                combined_text,
                media_group_id if use_semaphore else None,
                log,
                bulk_mode=bulk_mode,
            )
        except Exception as e:
            log.exception("Error processing message (message_id=%s): %s", getattr(main_message, "message_id", None), e)
            if bulk_mode:
                bulk_record_failed(uid)
                try:
                    await main_message.answer(kmsg("bulk_error", error=e)[:400])
                except Exception:
                    pass
            mg = media_group_id if use_semaphore else None
            if mg is not None and mg in _MEDIA_GROUPS:
                _MEDIA_GROUPS[mg]["processing"] = False
            import gc
            gc.collect()
