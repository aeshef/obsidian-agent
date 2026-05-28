from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from knowledge_bot.app.ui import kmsg


def _ocr_letter_class() -> str:
    lo = "".join(chr(c) for c in range(0x0430, 0x0450))
    hi = "".join(chr(c) for c in range(0x0410, 0x0450))
    return f"a-zA-Z0-9{lo}{hi}"


def generate_note_review(routed: dict[str, Any], summary_obj: dict[str, Any]) -> str:
    """Build a short pre-save review message from routed payload and summary."""
    lines: list[str] = []

    note_type = routed.get("type") or kmsg("type_undefined")
    title = routed.get("title") or kmsg("untitled")
    lines.append(kmsg("review", "type_line", type=note_type))
    lines.append(kmsg("review", "title_line", title=title))
    lines.append("")

    attachments = routed.get("attachments", {})
    files = attachments.get("files", []) or []
    links = attachments.get("links", []) or []

    media_count = len(files)
    if media_count > 0:
        from knowledge_bot.core.settings import load_media_extensions
        from shared.knowledge.media_kind import media_kind_for_path

        ext_map = load_media_extensions(Path(__file__).resolve().parents[2] / "config")
        kind_icons = {
            "image": kmsg("review", "media_photo"),
            "video": kmsg("review", "media_video"),
            "document": kmsg("review", "media_document"),
            "file": kmsg("review", "media_file"),
        }
        media_types = []
        for f in files:
            kind = media_kind_for_path(str(f), extensions=ext_map)
            media_types.append(kind_icons.get(kind, kmsg("review", "media_file")))
        lines.append(
            kmsg("review", "media_summary", count=media_count, kinds=", ".join(set(media_types)))
        )

    if links:
        lines.append(kmsg("review", "links_summary", count=len(links)))
        if len(links) <= 3:
            for link in links[:3]:
                lines.append(f"   • {link[:60]}...")

    derived = summary_obj.get("derived", {})
    ocr_text = derived.get("ocr_text", "")
    if ocr_text:
        letters = _ocr_letter_class()
        alnum_count = len(re.findall(f"[{letters}]", ocr_text))
        total_chars = len(re.sub(r"\s", "", ocr_text))
        quality_ratio = alnum_count / total_chars if total_chars > 0 else 0
        cleaned = re.sub(rf"[^{letters}\s]", "", ocr_text).strip()

        if quality_ratio >= 0.3 and len(cleaned) >= 20:
            ocr_sample = ocr_text[:200].strip()
            if len(ocr_text) > 200:
                ocr_sample += "..."
            ocr_sample = re.sub(r"[*_`\[\]()]", "", ocr_sample)
            lines.append("")
            lines.append(kmsg("review", "ocr_header"))
            lines.append(f"   {ocr_sample}")

    asr_text = derived.get("asr_text", "")
    if asr_text:
        asr_sample = asr_text[:200].strip()
        if len(asr_text) > 200:
            asr_sample += "..."
        asr_sample = re.sub(r"[*_`\[\]()]", "", asr_sample)
        lines.append("")
        lines.append(kmsg("review", "asr_header"))
        lines.append(f"   {asr_sample}")

    vision_text = derived.get("vision_text", "")
    if vision_text:
        vision_sample = vision_text[:200].strip()
        if len(vision_text) > 200:
            vision_sample += "..."
        vision_sample = re.sub(r"[*_`\[\]()]", "", vision_sample)
        lines.append("")
        lines.append(kmsg("review", "vision_header"))
        lines.append(f"   {vision_sample}")

    yt_summary = derived.get("yt_transcript_summary", "")
    if yt_summary:
        yt_sample = yt_summary[:200].strip()
        if len(yt_summary) > 200:
            yt_sample += "..."
        yt_sample = re.sub(r"[*_`\[\]()]", "", yt_sample)
        lines.append("")
        lines.append(kmsg("review", "youtube_header"))
        lines.append(f"   {yt_sample}")

    tags = routed.get("tags", [])
    if tags:
        lines.append("")
        lines.append(kmsg("review", "tags_line", tags=", ".join(tags[:5])))
        if len(tags) > 5:
            lines.append(kmsg("review", "tags_more", count=len(tags) - 5))

    field_mapping = {
        "steps": kmsg("review", "field_steps"),
        "status": kmsg("review", "field_status"),
        "cuisine": kmsg("review", "field_cuisine"),
        "kind": kmsg("review", "field_kind"),
        "category": kmsg("review", "field_category"),
        "city": kmsg("review", "field_city"),
        "nsfw": kmsg("review", "field_nsfw"),
        "subtype": kmsg("review", "field_subtype"),
    }

    skip_fields = {
        "type",
        "title",
        "created",
        "tags",
        "attachments",
        "source",
        "form",
        "raw_text",
        "raw_dir",
        "filenames",
        "asr_text",
        "asr_summary",
        "summary",
    }

    fields_display: list[str] = []
    for k, v in routed.items():
        if k not in skip_fields and v and isinstance(v, (str, int, float, list)) and len(k) > 1:
            field_name = field_mapping.get(k, k)
            if isinstance(v, list):
                fields_display.append(f"{field_name} ({len(v)})")
            else:
                fields_display.append(field_name)

    if fields_display:
        lines.append("")
        lines.append(kmsg("review", "fields_line", fields=", ".join(fields_display[:5])))
        if len(fields_display) > 5:
            lines.append(kmsg("review", "fields_more", count=len(fields_display) - 5))

    return "\n".join(lines)
