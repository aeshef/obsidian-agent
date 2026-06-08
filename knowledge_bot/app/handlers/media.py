from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram.types import Message

from knowledge_bot.core.llm import LLMClient
from knowledge_bot.services.persist import save_raw_file

from .telegram_media_helpers import (
    attach_saved_file,
    fetch_telegram_file_bytes,
    is_video_document,
    merge_extract_derived,
    run_extract_on_saved,
    try_telethon_save_video,
    video_download_fallback,
)
from ..state import _MEDIA_GROUPS, get_asr_semaphore


async def process_single_media(
    message: Message,
    text: str,
    routed: dict[str, Any],
    summary_obj: dict[str, Any],
    llm: LLMClient,
    cfg: Any,
    log: logging.Logger,
) -> None:
    """Process a single media attachment from a message."""
    # If there is a Telegram document, download and save to Export, link from note
    try:
        doc = getattr(message, "document", None)
        if doc and message.bot:
            content, path_name = await fetch_telegram_file_bytes(
                message, doc.file_id, cfg
            )
            name = doc.file_name or path_name
            saved = save_raw_file(cfg.export_root, name, content)
            log.info("Saved document: %s (%d bytes)", saved, len(content))
            attach_saved_file(routed, cfg, saved, name)
            is_video = is_video_document(doc)
            routed["form"] = "video" if is_video else "file"
            summary_obj.setdefault("meta", {})["form"] = routed["form"]
            try:
                await run_extract_on_saved(
                    saved,
                    text,
                    summary_obj,
                    llm,
                    filter_music_asr=is_video,
                    log=log,
                )
            except Exception as ee:
                log.warning("document extract failed: %s", ee)
    except Exception as e:
        log.warning("failed to download/save document: %s", e)
        doc = getattr(message, "document", None)
        if doc and is_video_document(doc) and message.bot:
            saved_via_telethon = await try_telethon_save_video(
                message,
                text,
                routed,
                summary_obj,
                llm,
                cfg,
                log,
                default_name=doc.file_name,
            )
            if not saved_via_telethon and getattr(doc, "file_name", None):
                routed.setdefault("filenames", []).append(doc.file_name)
                routed.setdefault("form", "file")

    # If there is a Telegram photo, download best size and save to Export; embed later in render
    try:
        photos = getattr(message, "photo", None)
        if photos and message.bot:
            best = photos[-1]
            content, path_name = await fetch_telegram_file_bytes(
                message, best.file_id, cfg
            )
            name = path_name
            saved = save_raw_file(cfg.export_root, name, content)
            log.info("Saved photo: %s (%d bytes)", saved, len(content))
            attach_saved_file(routed, cfg, saved, name)
            if not summary_obj["meta"].get("form"):
                summary_obj["meta"]["form"] = "image"
            try:
                await run_extract_on_saved(saved, text, summary_obj, llm, log=log)
            except Exception as ee:
                log.warning("image extract failed: %s", ee)
    except Exception as e:
        log.warning("failed to download/save photo: %s", e)

    # If there is a Telegram video, download, save to Export and run ASR
    try:
        vid = getattr(message, "video", None) or getattr(message, "video_note", None)
        if vid and message.bot:
            content, path_name = await fetch_telegram_file_bytes(
                message, vid.file_id, cfg
            )
            name = getattr(vid, "file_name", None) or path_name
            saved = save_raw_file(cfg.export_root, name, content)
            log.info("Saved video: %s (%d bytes)", saved, len(content))
            attach_saved_file(routed, cfg, saved, name)
            routed["form"] = "video"
            summary_obj.setdefault("meta", {})["form"] = "video"
            try:
                log.info("ASR/OCR begin for %s", saved)
                await run_extract_on_saved(
                    saved, text, summary_obj, llm, filter_music_asr=True, log=log
                )
            except Exception as ee:
                log.warning("asr extract failed: %s", ee)
    except Exception as e:
        log.warning("failed to download/save video: %s", e)
        vid = getattr(message, "video", None) or getattr(message, "video_note", None)
        if vid and message.bot:
            name = getattr(vid, "file_name", None) or f"telegram_video_{message.message_id}.mp4"
            if not await try_telethon_save_video(
                message, text, routed, summary_obj, llm, cfg, log, default_name=name
            ):
                await video_download_fallback(
                    message, vid, text, routed, summary_obj, llm, cfg, log
                )

    try:
        voice = getattr(message, "voice", None) or getattr(message, "audio", None)
        if voice and message.bot:
            content, path_name = await fetch_telegram_file_bytes(
                message, voice.file_id, cfg
            )
            ext = (getattr(voice, "mime_type", None) or "audio/ogg").split("/")[-1].split(";")[0].strip() or "ogg"
            if ext not in ("ogg", "m4a", "mp3", "wav"):
                ext = "ogg"
            name = path_name
            if not name.lower().endswith(f".{ext}"):
                name = f"{name}.{ext}" if "." not in name else name.rsplit(".", 1)[0] + f".{ext}"
            saved = save_raw_file(cfg.export_root, name, content)
            log.info("Saved voice/audio: %s (%d bytes)", saved, len(content))
            attach_saved_file(routed, cfg, saved, name)
            routed["form"] = "audio"
            summary_obj.setdefault("meta", {})["form"] = "audio"
            try:
                await run_extract_on_saved(saved, text, summary_obj, llm, log=log)
            except Exception as ee:
                log.warning("voice/audio ASR failed: %s", ee)
    except Exception as e:
        log.warning("failed to download/save voice or audio: %s", e)


async def resolve_incoming_messages(
    message: Message,
    text: str,
    log: logging.Logger,
) -> tuple[Message, list[Message], str, int | None, bool] | None:
    """Collect media group or single message; None if already processing."""
    media_group_id = getattr(message, "media_group_id", None)
    if media_group_id is None and hasattr(message, "model_dump"):
        try:
            data = message.model_dump()
            media_group_id = data.get("media_group_id")
        except Exception:
            pass

    if not text and (message.video or message.photo or message.document):
        log.debug(
            "Media message: message_id=%d, media_group_id=%s, has_video=%s, has_photo=%s",
            message.message_id,
            media_group_id,
            bool(message.video),
            bool(message.photo),
        )

    if media_group_id:
        if media_group_id not in _MEDIA_GROUPS:
            _MEDIA_GROUPS[media_group_id] = {"messages": [], "processing": False, "processed": False}

        _MEDIA_GROUPS[media_group_id]["messages"].append(message)
        total_count = len(_MEDIA_GROUPS[media_group_id]["messages"])
        log.info("Added message to media_group %s (total: %d)", media_group_id, total_count)

        if _MEDIA_GROUPS[media_group_id]["processing"] or _MEDIA_GROUPS[media_group_id]["processed"]:
            log.debug("Media group %s already processing/processed, skipping", media_group_id)
            return None

        is_first_message = (total_count == 1)
        if not is_first_message:
            log.debug("Not first message in media_group %s, skipping processing", media_group_id)
            return None

        log.info("First message in media_group %s, waiting 3 seconds to collect others...", media_group_id)
        await asyncio.sleep(3)

        if _MEDIA_GROUPS[media_group_id]["processing"] or _MEDIA_GROUPS[media_group_id]["processed"]:
            log.debug("Media group %s already processing/processed after wait, skipping", media_group_id)
            return None

        _MEDIA_GROUPS[media_group_id]["processing"] = True

        main_message = _MEDIA_GROUPS[media_group_id]["messages"][0]
        all_messages = _MEDIA_GROUPS[media_group_id]["messages"]
        combined_text = "\n".join([(m.text or m.caption or "") for m in all_messages if (m.text or m.caption)])
        if not combined_text:
            combined_text = text
        log.info(
            "Processing media_group %s with %d messages, combined_text len=%d",
            media_group_id,
            len(all_messages),
            len(combined_text),
        )

        use_semaphore = True
        return main_message, all_messages, combined_text, media_group_id, use_semaphore

    return message, [message], text, None, False
