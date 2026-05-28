from __future__ import annotations

import json
import logging
import os

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from knowledge_bot.app.ui import kmsg
from knowledge_bot.core.config import load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.core.schema import allowed_fields_for_type
from knowledge_bot.core.settings import get_author_context, load_enums_config, load_prompt
from knowledge_bot.services.render import render_note
from knowledge_bot.services.tags_inventory import get_tags_inventory_for_prompt
from knowledge_bot.services.wikilinks import inject_wikilinks

from .. import state as app_state
from ..state import pending_limit, preview_keyboard


async def on_set_type(cb: CallbackQuery) -> None:
    st = app_state._PENDING.get(cb.message.message_id)
    if not st:
        await cb.answer(
            kmsg("pending_data_lost", limit=pending_limit()),
            show_alert=True,
        )
        return
    new_type = cb.data.split(":", 1)[1]

    st["payload"]["type"] = new_type

    app_state._PENDING[cb.message.message_id] = st
    cfg_l = load_config()
    llm_l = LLMClient(cfg_l.deepseek_api_key, cfg_l.deepseek_base_url)
    summary_l = st.get("summary")
    try:
        naming_system = load_prompt(cfg_l.agent_config_path, "naming")
        naming_input = json.dumps(
            {
                "type": new_type,
                "summary": summary_l,
                "filenames": st["payload"].get("filenames", []),
                "hint_title": st["payload"].get("title"),
            },
            ensure_ascii=False,
        )
        named = llm_l.chat_json(naming_system, naming_input).content or {}

        if isinstance(named, dict):
            title_val = named.get("title")
            if isinstance(title_val, str) and title_val.strip():
                title_clean = title_val.strip()
                if not (title_clean.startswith("{") or title_clean.startswith("[")):
                    if len(title_clean) < 200:
                        st["payload"]["title"] = title_clean
    except Exception:
        pass
    try:
        enums_cfg = load_enums_config(cfg_l.agent_config_path)
        allowed_fields = allowed_fields_for_type(new_type) or []
        field_system = load_prompt(cfg_l.agent_config_path, "field_fill")
        user = {
            "type": new_type,
            "allowed_fields": allowed_fields,
            "summary": summary_l,
            "filenames": st["payload"].get("filenames", []),
            "enums": {
                "namespaces_controlled": enums_cfg.namespaces_controlled,
                "common": enums_cfg.common,
                "per_type": enums_cfg.per_type,
            },
        }
        filled = llm_l.chat_json(field_system, json.dumps(user, ensure_ascii=False)).content or {}
        for k in allowed_fields:
            if k in filled:
                st["payload"][k] = filled[k]
    except Exception:
        pass
    try:
        enums_cfg = load_enums_config(cfg_l.agent_config_path)
        tags_system = load_prompt(cfg_l.agent_config_path, "tags")
        ctx = get_author_context(cfg_l.agent_config_path)
        author_line = kmsg("author_context_line", context=ctx) if ctx else ""
        tags_system = tags_system.replace("{{AUTHOR_CONTEXT_LINE}}", author_line)
        tags_inventory_text = get_tags_inventory_for_prompt(cfg_l.agent_config_path)
        domain_topic_path = cfg_l.agent_config_path.parent / "docs" / "DOMAIN_VS_TOPIC.md"
        domain_topic_block = ""
        if domain_topic_path.exists():
            domain_topic_block = "\n\n---\n" + domain_topic_path.read_text(encoding="utf-8")
        tags_system = f"{tags_system}\n\n{tags_inventory_text}{domain_topic_block}"
        fields_for_tags = {}
        for k, v in st["payload"].items():
            if k not in {"type", "title", "created", "tags", "attachments", "source", "form", "raw_text", "raw_dir"}:
                fields_for_tags[k] = v
        tags_user = {
            "type": new_type,
            "summary": summary_l,
            "attachments": {"links": st["payload"].get("attachments", {}).get("links", [])},
            "enums": {
                "namespaces_controlled": enums_cfg.namespaces_controlled,
                "common": enums_cfg.common,
                "per_type": enums_cfg.per_type,
            },
            "synonyms": enums_cfg.synonyms,
            "filenames": st["payload"].get("filenames", []),
            "fields": fields_for_tags,
        }
        tag_resp = llm_l.chat_json(tags_system, json.dumps(tags_user, ensure_ascii=False)).content or []
        tag_candidates = tag_resp.get("tags") if isinstance(tag_resp, dict) else (tag_resp if isinstance(tag_resp, list) else [])
        from knowledge_bot.services.tag_normalize import normalize_tags

        st["payload"]["tags"] = normalize_tags(tag_candidates, enums_cfg, new_type)
    except Exception:
        pass
    rendered = render_note(cfg_l.templates_path, st["payload"])
    if os.environ.get("ENABLE_WIKILINKS") == "1":
        llm_l = LLMClient(cfg_l.deepseek_api_key, cfg_l.deepseek_base_url)
        rendered = inject_wikilinks(rendered, cfg_l.agent_config_path, cfg_l.vault_path, llm_l)
    st["rendered"] = rendered
    app_state._PENDING[cb.message.message_id] = st
    await cb.message.edit_text(
        kmsg(
            "preview_ready_typed",
            type=new_type,
            title=st["payload"]["title"],
        ),
        reply_markup=preview_keyboard().as_markup(),
    )
    try:
        await cb.answer(kmsg("type_updated"))
    except TelegramBadRequest:
        pass
