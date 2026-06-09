"""LLM note type routing for knowledge ingest (routing.txt prompt)."""
from __future__ import annotations

import json
import logging
from typing import Any

from knowledge_bot.core.config import load_config
from knowledge_bot.core.settings import (
    enums_for_llm_payload,
    get_author_context,
    load_enums_config,
    load_prompt,
    load_types_config,
)
from knowledge_bot.i18n.domain_text import routing_author_line

log = logging.getLogger("kb.routing")


def route_and_fill(llm: Any, summary_obj: dict[str, Any], *, source_hint: str = "telegram") -> dict[str, Any]:
    """Pick note type and minimal payload via routing prompt."""
    cfg = load_config()
    types_cfg = load_types_config(cfg.agent_config_path)
    enums_cfg = load_enums_config(cfg.agent_config_path)
    allowed_types = sorted(types_cfg.types.keys())

    routing_system = load_prompt(cfg.agent_config_path, "routing")
    author_line = routing_author_line(get_author_context(cfg.agent_config_path))
    routing_system = routing_system.replace("{{AUTHOR_CONTEXT_LINE}}", author_line)

    user_payload = {
        "summary": summary_obj,
        "allowed_types": allowed_types,
        "enums": enums_for_llm_payload(enums_cfg),
        "source_hint": source_hint,
    }
    try:
        resp = llm.chat_json(routing_system, json.dumps(user_payload, ensure_ascii=False))
        routed = resp.content if resp and isinstance(resp.content, dict) else {}
    except Exception as e:
        log.warning("route_and_fill LLM failed: %s", e)
        routed = {}

    if not isinstance(routed, dict):
        routed = {}

    routed.setdefault("type", types_cfg.default_type)
    routed.setdefault("attachments", {"links": [], "files": []})
    routed.setdefault("source", source_hint)
    if source_hint and not routed.get("form"):
        meta = summary_obj.get("meta") if isinstance(summary_obj.get("meta"), dict) else {}
        form = meta.get("form")
        if form:
            routed["form"] = form
    return routed
