"""Persist note to vault (save button and bulk ingest)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from knowledge_bot.core.config import load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.services.persist import write_note
from knowledge_bot.services.query import schedule_rebuild_if_enabled
from knowledge_bot.services.render import render_note
from knowledge_bot.services.tags_inventory import update_inventory_with_new_tags
from knowledge_bot.services.wikilinks import inject_wikilinks

log = logging.getLogger("kb.save_note")


def commit_routed_note(
    payload: dict[str, Any],
    summary_obj: dict[str, Any] | None = None,
) -> Path:
    """Render, write_note, refresh tag inventory; return absolute path."""
    cfg = load_config()
    summary_derived = (summary_obj or {}).get("derived") or {}
    for key in ("yt_transcript_summary", "asr_summary"):
        val = (summary_derived.get(key) or "").strip() if isinstance(summary_derived.get(key), str) else ""
        if val and not (payload.get(key) or "").strip():
            payload[key] = val
    if summary_derived:
        payload = {**payload, "_derived_for_render": summary_derived}
    rendered = render_note(cfg.templates_path, payload)
    if os.environ.get("ENABLE_WIKILINKS") == "1":
        llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
        rendered = inject_wikilinks(rendered, cfg.agent_config_path, cfg.vault_path, llm)
    note_path = write_note(cfg.vault_path, payload["type"], payload["title"], rendered)
    log.info("Written note: %s", note_path)
    schedule_rebuild_if_enabled(cfg.vault_path)
    new_tags = payload.get("tags", [])
    if new_tags:
        try:
            update_inventory_with_new_tags(cfg.agent_config_path, new_tags)
        except Exception as e:
            log.warning("Failed to update tags inventory: %s", e)
    return note_path
