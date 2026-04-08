from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from knowledge_bot.core.llm import LLMClient
from knowledge_bot.core.settings import load_prompt

log = logging.getLogger("kb.query.intent")


def _looks_like_single_url(s: str) -> bool:
    t = s.strip()
    return bool(re.match(r"^https?://\S+$", t, re.IGNORECASE))


def classify_text_intent(agent_config_path: Path, llm: LLMClient, text: str) -> str:
    """Module helper (user strings in YAML)."""
    if os.environ.get("KNOWLEDGE_ALWAYS_QUERY", "").strip() == "1":
        return "query"
    if os.environ.get("KNOWLEDGE_ALWAYS_SAVE", "").strip() == "1":
        return "save"

    t = (text or "").strip()
    if not t:
        return "chat"
    if _looks_like_single_url(t):
        return "save"

    system = load_prompt(agent_config_path, "text_intent")
    payload = json.dumps({"text": t[:12000]}, ensure_ascii=False)
    try:
        raw = llm.chat_json(system, payload, timeout=45.0).content
    except Exception:
        log.exception("text intent LLM failed, defaulting to chat")
        return "chat"

    if not isinstance(raw, dict):
        return "chat"
    intent = str(raw.get("intent") or "").strip().lower()
    if intent not in ("query", "save", "chat"):
        return "chat"
    log.info("text intent: %s (%s)", intent, (raw.get("reason") or "")[:120])
    return intent
