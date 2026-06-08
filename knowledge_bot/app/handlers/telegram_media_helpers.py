"""Telegram file download and derived-field merge (shared with media.py)."""
from __future__ import annotations

import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from aiogram.types import Message

from knowledge_bot.app.ui import kmsg
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.services.extract import extract_from_path
from knowledge_bot.services.persist import save_raw_file

from ..state import get_asr_semaphore

_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def is_video_document(doc: Any) -> bool:
    mime = (getattr(doc, "mime_type", None) or "").lower()
    if mime.startswith("video/"):
        return True
    name = (getattr(doc, "file_name", None) or "").lower()
    return any(name.endswith(ext) for ext in _VIDEO_SUFFIXES)


def telegram_file_too_big(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "too big" in s or "file is too large" in s


def ingest_limitation_text(summary_obj: dict[str, Any], routed: dict[str, Any]) -> str | None:
    """Hint when a large TG video file was not available from Bot API."""
    if not (summary_obj.get("meta") or {}).get("telegram_file_too_big"):
        return None
    derived = summary_obj.get("derived") or {}
    has_asr = bool((derived.get("asr_text") or "").strip())
    links = (routed.get("attachments") or {}).get("links") or []
    parts = [kmsg("ingest", "tg_video_too_big")]
    if not has_asr:
        parts.append(kmsg("ingest", "asr_needed"))
    if not links:
        parts.append(kmsg("ingest", "add_youtube_link"))
    return " ".join(parts)


async def fetch_telegram_file_bytes(
    message: Message,
    file_id: str,
    _cfg: Any = None,
) -> tuple[bytes, str]:
    """Download by file_id via message.bot (unified host token)."""
    tg_file = await message.bot.get_file(file_id)
    file_path = getattr(tg_file, "file_path", None)
    if not file_path:
        raise RuntimeError("Telegram get_file returned empty file_path")
    buf = BytesIO()
    await message.bot.download_file(file_path, buf)
    name = file_path.split("/")[-1]
    return buf.getvalue(), name


def attach_saved_file(
    routed: dict[str, Any],
    cfg: Any,
    saved: Path,
    name: str,
) -> None:
    if not isinstance(routed.get("attachments"), dict):
        routed["attachments"] = {"links": [], "files": []}
    routed["attachments"].setdefault("links", [])
    routed["attachments"].setdefault("files", [])
    try:
        rel = saved.relative_to(cfg.vault_path)
        routed["attachments"]["files"].append(str(rel))
        routed["raw_dir"] = str(rel.parent)
    except Exception:
        routed["attachments"]["files"].append(str(saved))
        routed["raw_dir"] = str(saved.parent)
    routed.setdefault("filenames", []).append(name)


def merge_extract_derived(
    summary_obj: dict[str, Any],
    derived: Any,
    *,
    filter_music_asr: bool = False,
    log: logging.Logger | None = None,
) -> None:
    summary_obj.setdefault("derived", {})
    if derived.pdf_text:
        summary_obj["derived"]["pdf_text"] = (
            summary_obj["derived"].get("pdf_text", "") + "\n" + derived.pdf_text
        ).strip()
    if derived.ocr_text:
        existing = summary_obj["derived"].get("ocr_text", "")
        summary_obj["derived"]["ocr_text"] = (
            (existing + "\n" + derived.ocr_text).strip() if existing else derived.ocr_text
        )
        if log:
            log.info("OCR captured len=%d", len(derived.ocr_text))
    if derived.asr_text:
        use = True
        if filter_music_asr:
            asr_lower = derived.asr_text.lower().strip()
            use = not (
                len(derived.asr_text) < 100
                and any(
                    p in asr_lower
                    for p in (
                        "sugar",
                        "tongue",
                        "sweet",
                        "body",
                        "love",
                        "baby",
                        "tonight",
                        "feel",
                        "touch",
                        "kiss",
                        "dance",
                        "music",
                        "song",
                    )
                )
                and not any(
                    w in asr_lower
                    for w in (
                        "how",
                        "what",
                        "why",
                        "when",
                        "where",
                        "tutorial",
                        "guide",
                        "step",
                        "method",
                        "technique",
                        "process",
                        "recipe",
                        "ingredient",
                    )
                )
            )
        if use:
            existing = summary_obj["derived"].get("asr_text", "")
            summary_obj["derived"]["asr_text"] = (
                (existing + "\n" + derived.asr_text).strip() if existing else derived.asr_text
            )
            if log:
                log.info("ASR captured len=%d", len(derived.asr_text))
    if derived.vision_text:
        existing = summary_obj["derived"].get("vision_text", "")
        summary_obj["derived"]["vision_text"] = (
            (existing + "\n" + derived.vision_text).strip() if existing else derived.vision_text
        )
        if log:
            log.info("Vision captured len=%d", len(derived.vision_text))


async def run_extract_on_saved(
    saved: Path,
    text: str,
    summary_obj: dict[str, Any],
    llm: LLMClient | None,
    *,
    filter_music_asr: bool = False,
    ocr_profile: str = "photo",
    log: logging.Logger | None = None,
) -> None:
    asr_sem = get_asr_semaphore()
    async with asr_sem:
        derived = await asyncio.to_thread(
            extract_from_path,
            str(saved),
            text,
            llm if ocr_profile == "photo" else None,
            ocr_profile=ocr_profile,
        )
        import gc

        gc.collect()
    merge_extract_derived(
        summary_obj, derived, filter_music_asr=filter_music_asr, log=log
    )


async def try_telethon_save_video(
    message: Message,
    text: str,
    routed: dict[str, Any],
    summary_obj: dict[str, Any],
    llm: LLMClient,
    cfg: Any,
    log: logging.Logger,
    *,
    default_name: str | None = None,
) -> bool:
    """Telethon MTProto full download + extract. True when saved."""
    from knowledge_bot.services.telethon_download import download_message_media

    got = await download_message_media(message)
    if not got:
        return False
    content, path_name = got
    name = default_name or path_name
    if not any(name.lower().endswith(ext) for ext in _VIDEO_SUFFIXES):
        stem = name.rsplit(".", 1)[0] if "." in name else name
        name = f"{stem}.mp4"
    saved = save_raw_file(cfg.export_root, name, content)
    log.info("Saved video (Telethon): %s (%d bytes)", saved, len(content))
    attach_saved_file(routed, cfg, saved, name)
    routed["form"] = "video"
    summary_obj.setdefault("meta", {})["form"] = "video"
    summary_obj.get("meta", {}).pop("telegram_file_too_big", None)
    try:
        log.info("ASR/OCR begin (Telethon) for %s", saved)
        await run_extract_on_saved(
            saved, text, summary_obj, llm, filter_music_asr=True, log=log
        )
    except Exception as ee:
        log.warning("extract after Telethon failed: %s", ee)
    return True


async def video_download_fallback(
    message: Message,
    vid: Any,
    text: str,
    routed: dict[str, Any],
    summary_obj: dict[str, Any],
    llm: LLMClient,
    cfg: Any,
    log: logging.Logger,
) -> None:
    """Fallback when Bot API cannot return large video (>20 MB)."""
    routed["form"] = "video"
    summary_obj.setdefault("meta", {})["form"] = "video"
    summary_obj["meta"]["telegram_file_too_big"] = True
    name = getattr(vid, "file_name", None) or f"telegram_video_{message.message_id}.mp4"
    routed.setdefault("filenames", []).append(name)

    cap = (message.caption or text or "").strip()
    if cap:
        prev = (summary_obj.get("raw_text") or "").strip()
        summary_obj["raw_text"] = f"{prev}\n{cap}".strip() if prev else cap

    thumb = getattr(vid, "thumbnail", None)
    if not thumb:
        log.info(
            "video too big, no thumbnail: msg_id=%s file_size=%s",
            message.message_id,
            getattr(vid, "file_size", None),
        )
        return

    try:
        content, thumb_name = await fetch_telegram_file_bytes(
            message, thumb.file_id, cfg
        )
        if not thumb_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            thumb_name = f"{thumb_name}_thumb.jpg"
        saved = save_raw_file(cfg.export_root, thumb_name, content)
        log.info("Saved video thumbnail fallback: %s (%d bytes)", saved, len(content))
        attach_saved_file(routed, cfg, saved, thumb_name)
        await run_extract_on_saved(
            saved, text, summary_obj, llm, ocr_profile="thumbnail", log=log
        )
        if os.environ.get("OPENROUTER_API_KEY"):
            try:
                from knowledge_bot.services.extract.vision import extract_vision_from_image

                vision = await asyncio.to_thread(extract_vision_from_image, saved)
                if vision:
                    summary_obj.setdefault("derived", {})
                    prev = (summary_obj["derived"].get("vision_text") or "").strip()
                    summary_obj["derived"]["vision_text"] = (
                        f"{prev}\n{vision}".strip() if prev else vision
                    )
                    if log:
                        log.info("Vision on TG thumbnail: %d chars", len(vision))
            except Exception as ve:
                log.warning("thumbnail vision failed: %s", ve)
        else:
            log.info("Vision on TG thumbnail skipped: no OPENROUTER_API_KEY")
    except Exception as te:
        log.warning("video thumbnail fallback failed: %s", te)
