"""LLM domain and intent classification. No keyword fallback."""
from __future__ import annotations

import asyncio
import json
import logging
from functools import lru_cache
from typing import Any

from shared.agent.config import agent_config_dir, load_routing_config, load_tools_config
from shared.agent.platform_config import platform_float, platform_int
from shared.llm import LLMClient
from shared.prompts import load_prompt

log = logging.getLogger("shared.agent.llm_classify")


class LLMClassificationError(RuntimeError):
    """LLM classifier unavailable or returned invalid response."""


_LLM: LLMClient | None = None


def _llm() -> LLMClient:
    global _LLM
    if _LLM is None:
        _LLM = LLMClient()
    return _LLM


def clear_prompt_cache() -> None:
    _load_prompt_file.cache_clear()


@lru_cache(maxsize=32)
def _load_prompt_file(name: str) -> str:
    stem = name.removesuffix(".txt") if name.endswith(".txt") else name
    text = load_prompt(agent_config_dir(), stem, subdir="prompts", required=True)
    if not text.strip():
        raise LLMClassificationError(
            f"prompt is empty: {stem} (config/agent/prompts/{stem}.txt)"
        )
    return text


def _require_json_field(
    raw: dict[str, Any],
    key: str,
    allowed: set[str],
    *,
    label: str,
) -> str:
    if not raw:
        raise LLMClassificationError(f"{label}: empty LLM JSON response")
    if key not in raw:
        raise LLMClassificationError(f"{label}: missing field '{key}' in {raw!r}")
    val = str(raw[key]).strip().lower()
    if val not in allowed:
        raise LLMClassificationError(
            f"{label}: invalid {key}={val!r}, expected one of {sorted(allowed)}"
        )
    return val


async def _chat_json_classify(system: str, user_payload: dict[str, Any], *, label: str) -> dict[str, Any]:
    raw = await asyncio.to_thread(
        _llm().chat_json_messages,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        temperature=platform_float("llm_classify", "temperature", default=0.0),
        timeout=platform_float("llm_classify", "timeout_sec", default=25.0),
        raise_on_error=True,
    )
    if not isinstance(raw, dict) or not raw:
        raise LLMClassificationError(f"{label}: LLM returned non-object JSON")
    return raw


def dialogue_hint(
    chat_id: int | None,
    domains: list[str],
    *,
    per_domain: int | None = None,
) -> str:
    if per_domain is None:
        per_domain = platform_int(
            "llm_classify", "dialogue_hint_per_domain", default=2
        )
    if chat_id is None:
        return ""
    from shared.memory.session import get_history

    lines: list[str] = []
    for dom in domains:
        for m in get_history(chat_id, dom)[-per_domain:]:
            lines.append(f"[{dom}] {m.role}: {(m.content or '')[:160]}")
    return "\n".join(lines[-12:])


async def classify_host_domain_llm(
    text: str,
    *,
    enabled: list[str],
    chat_id: int | None = None,
    ui_mode: str = "auto",
) -> str:
    """finance | planning | knowledge | general | unified (when multiple domains available)."""
    if not enabled:
        raise LLMClassificationError("classify_host_domain: no enabled domains")

    allowed = set(enabled) | {"general"}
    if len(enabled) >= 2:
        allowed.add("unified")

    system = _load_prompt_file("host_domain_router.txt")
    raw = await _chat_json_classify(
        system,
        {
            "message": text,
            "enabled_domains": enabled,
            "allow_unified": len(enabled) >= 2,
            "ui_mode": ui_mode,
            "dialogue_context": dialogue_hint(chat_id, enabled),
        },
        label="host_domain",
    )
    dom = _require_json_field(raw, "domain", allowed, label="host_domain")
    log.info(
        "host domain LLM: %s (conf=%s) text=%.50s",
        dom,
        raw.get("confidence"),
        text,
    )
    if dom not in ("general", "unified") and dom not in enabled:
        raise LLMClassificationError(
            f"host_domain: LLM chose {dom!r} but enabled={enabled}"
        )
    return dom


def map_general_domain(dom_name: str) -> str:
    if dom_name != "general":
        return dom_name
    cfg = load_routing_config().get("host") or {}
    return str(cfg.get("general_domain") or "planning")


async def classify_finance_intent_llm(
    text: str,
    *,
    chat_id: int | None = None,
) -> str:
    system = _load_prompt_file("finance_intent_router.txt")
    raw = await _chat_json_classify(
        system,
        {"message": text, "dialogue_context": dialogue_hint(chat_id, ["finance"], per_domain=3)},
        label="finance_intent",
    )
    intent = _require_json_field(
        raw,
        "intent",
        {"finance_query", "add_transaction", "chitchat"},
        label="finance_intent",
    )
    log.info("finance intent LLM: %s text=%.50s", intent, text)
    return intent


async def classify_planning_intent_llm(text: str) -> str:
    system = _load_prompt_file("planning_intent_router.txt")
    raw = await _chat_json_classify(system, {"message": text}, label="planning_intent")
    intent = _require_json_field(
        raw, "intent", {"task", "chat"}, label="planning_intent"
    )
    log.info("planning intent LLM: %s text=%.50s", intent, text)
    return intent


async def select_tools_llm(
    query: str,
    registry: Any,
    *,
    domain: str,
) -> list[str]:
    """Select tool names for agent loop. No keyword fallback."""
    from shared.agent.tools import ToolRegistry

    if not isinstance(registry, ToolRegistry):
        raise TypeError("registry must be ToolRegistry")

    all_names = registry.names()
    if not all_names:
        raise LLMClassificationError("select_tools: empty registry")

    always = {n for n in all_names if registry.get(n).always}
    catalog = [
        {
            "name": n,
            "description": registry.get(n).description,
            "category": registry.get(n).category,
            "always": registry.get(n).always,
        }
        for n in all_names
    ]
    from shared.capabilities.hints import domain_hint_text

    hints = domain_hint_text(domain)

    system = _load_prompt_file("tool_select_router.txt")
    raw = await _chat_json_classify(
        system,
        {
            "domain": domain,
            "domain_hint": hints,
            "message": query,
            "catalog": catalog,
        },
        label="tool_select",
    )
    picked = raw.get("tools")
    if not isinstance(picked, list):
        raise LLMClassificationError(
            f"tool_select: missing or invalid 'tools' list in {raw!r}"
        )

    selected: set[str] = set(always)
    unknown: list[str] = []
    for item in picked:
        name = str(item).strip()
        if not name:
            continue
        if name in registry._tools:
            selected.add(name)
        else:
            unknown.append(name)
    if unknown:
        raise LLMClassificationError(
            f"tool_select: unknown tools {unknown}, available={all_names}"
        )
    if not picked and not selected:
        log.info("tool select: chat-only (no tools) domain=%s text=%.50s", domain, query)
        return []
    if not picked and selected:
        log.info(
            "tool select: LLM picked none, using always=%s domain=%s",
            sorted(selected),
            domain,
        )

    out = sorted(selected)
    log.info(
        "tool select LLM: %s (always=%s) domain=%s text=%.50s",
        out,
        sorted(always),
        domain,
        query,
    )
    return out
