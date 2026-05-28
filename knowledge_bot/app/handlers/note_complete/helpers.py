"""Shared helpers for note completion pipeline."""
from __future__ import annotations

import asyncio
import gc
import logging
import os
import re
from typing import Any

from aiogram.types import Message

from knowledge_bot.services.extract import download_via_ytdlp, extract_from_path

from ...state import get_asr_semaphore

_YTDLP_DOMAINS = ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "x.com", "twitter.com")


def collect_urls(bundle, all_messages: list[Message]) -> list[str]:
    urls = list(bundle.urls or [])
    for msg in all_messages:
        txt = msg.text or msg.caption or ""
        ents = getattr(msg, "entities", None) or getattr(msg, "caption_entities", None) or []
        for ent in ents:
            if getattr(ent, "type", "") == "text_link" and getattr(ent, "url", ""):
                urls.append(ent.url)
            elif getattr(ent, "type", "") == "url" and txt:
                start, length = getattr(ent, "offset", 0), getattr(ent, "length", 0)
                urls.append(txt[start : start + length])
    return urls


def merge_attachment_links(routed: dict, bundle, all_messages: list[Message]) -> None:
    """Merge URLs from routed payload, raw text, and Telegram entities."""

    def _normalize_url(u: str) -> str:
        return u.strip().strip(".,);]'")

    links: set[str] = set()
    anchors: dict[str, str] = {}
    for u in routed.get("attachments", {}).get("links", []) or []:
        if isinstance(u, str) and u.startswith(("http://", "https://")):
            links.add(_normalize_url(u))
    for m in re.finditer(r"https?://[^\s)]+", bundle.raw_text or ""):
        links.add(_normalize_url(m.group(0)))
    for msg in all_messages:
        ents = msg.entities if msg.text is not None else msg.caption_entities
        txt = msg.text if msg.text is not None else (msg.caption or "")
        if not ents:
            continue
        for ent in ents:
            start = getattr(ent, "offset", 0)
            length = getattr(ent, "length", 0)
            piece = (txt or "")[start : start + length]
            url_val = getattr(ent, "url", None) or piece
            if isinstance(url_val, str) and url_val.startswith(("http://", "https://")):
                nurl = _normalize_url(url_val)
                links.add(nurl)
                anchor_text = piece.strip()
                if anchor_text and anchor_text != url_val:
                    anchors.setdefault(nurl, anchor_text)
    routed.setdefault("attachments", {"links": [], "files": []})
    routed["attachments"]["links"] = sorted(links)
    if anchors:
        routed["links_anchors"] = [{"url": u, "text": anchors[u]} for u in sorted(anchors.keys())]


async def ytdlp_fallback(cfg, routed: dict, summary_obj: dict, *, merge_asr: bool = True) -> None:
    """Download video via yt-dlp when Telegram file is unavailable."""
    if os.environ.get("YTDLP_ENABLED", "0") != "1":
        return
    if (routed.get("attachments", {}) or {}).get("files"):
        return
    ytdlp_url = None
    for u in routed.get("attachments", {}).get("links", []) or []:
        if any(d in u for d in _YTDLP_DOMAINS):
            ytdlp_url = u
            break
    if not ytdlp_url:
        return
    log = logging.getLogger("kb.note_complete")
    try:
        saved_path = download_via_ytdlp(ytdlp_url, cfg.export_root)
        if not saved_path:
            return
        try:
            rel = saved_path.relative_to(cfg.vault_path)
            routed["attachments"]["files"].append(str(rel))
            routed["raw_dir"] = str(rel.parent)
        except Exception:
            routed["attachments"]["files"].append(str(saved_path))
            routed["raw_dir"] = str(saved_path.parent)
        routed["form"] = routed.get("form") or "video"
        routed.setdefault("filenames", []).append(saved_path.name)
        asr_sem = get_asr_semaphore()
        async with asr_sem:
            derived = await asyncio.to_thread(extract_from_path, str(saved_path))
            gc.collect()
        if derived.asr_text:
            if merge_asr:
                existing = summary_obj["derived"].get("asr_text", "")
                summary_obj["derived"]["asr_text"] = (
                    (existing + "\n" + derived.asr_text).strip() if existing else derived.asr_text
                )
            else:
                summary_obj["derived"]["asr_text"] = derived.asr_text
        if derived.vision_text:
            if merge_asr:
                existing = summary_obj["derived"].get("vision_text", "")
                summary_obj["derived"]["vision_text"] = (
                    (existing + "\n" + derived.vision_text).strip() if existing else derived.vision_text
                )
            else:
                summary_obj["derived"]["vision_text"] = derived.vision_text
    except Exception as e:
        log.warning("ytdlp fallback failed: %s", e)
