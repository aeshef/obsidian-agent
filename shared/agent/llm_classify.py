"""LLM domain and intent classification. No keyword fallback."""
from __future__ import annotations

import asyncio
import json
import logging
from functools import lru_cache
from typing import Any

from shared.agent.config import agent_config_dir, load_routing_config
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
    clip = platform_int("llm_classify", "dialogue_hint_chars", default=160)
    max_lines = platform_int("llm_classify", "dialogue_hint_max_lines", default=12)
    if chat_id is None:
        return ""
    from shared.memory.session import get_history

    lines: list[str] = []
    for dom in domains:
        for m in get_history(chat_id, dom)[-per_domain:]:
            ts = m.ts or "time_unknown"
            lines.append(f"[{dom}][{ts}] {m.role}: {(m.content or '')[:clip]}")
    return "\n".join(lines[-max_lines:])


def _tool_select_history_hint(history: list | None, *, n: int | None = None) -> str:
    if n is None:
        n = platform_int("llm_classify", "tool_select_history_turns", default=6)
    clip = platform_int("llm_classify", "dialogue_hint_chars", default=160)
    if not history:
        return ""
    lines: list[str] = []
    for m in history[-n:]:
        role = str(getattr(m, "role", "") or "")
        if role not in ("user", "assistant"):
            continue
        text = str(getattr(m, "content", "") or "")[:clip]
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


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
    if raw.get("_salvaged") and "domain" not in raw:
        log.warning("host_domain: salvaged non-router JSON %r → general", raw)
        return "general"

    dom_raw = str(raw.get("domain", "")).strip().lower()
    if not dom_raw:
        dom = _require_json_field(raw, "domain", allowed, label="host_domain")
    elif dom_raw not in allowed:
        enabled_set = set(enabled)
        if dom_raw in ("planning", "finance", "knowledge") and dom_raw not in enabled_set:
            log.warning(
                "host_domain: LLM chose disabled %s (enabled=%s) → general",
                dom_raw,
                enabled,
            )
            dom = "general"
        else:
            raise LLMClassificationError(
                f"host_domain: invalid domain={dom_raw!r}, expected one of {sorted(allowed)}"
            )
    else:
        dom = dom_raw
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
    history: list | None = None,
):
    """Select tool names for agent loop. No keyword fallback.

    Returns ToolSelection: offered (schemas/allowlist) vs picked (LLM+always).
    schema_pin stays offered when anything is picked; it is not a must-call list.
    """
    from shared.agent.tools import ToolRegistry
    from shared.agent.types import ToolSelection

    if not isinstance(registry, ToolRegistry):
        raise TypeError("registry must be ToolRegistry")

    all_names = registry.names()
    if not all_names:
        raise LLMClassificationError("select_tools: empty registry")

    always = {n for n in all_names if registry.get(n).always}
    from shared.agent.config import schema_pin_names

    pin = {n for n in schema_pin_names(domain) if n in registry._tools}
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
            "dialogue_context": _tool_select_history_hint(history),
            "catalog": catalog,
        },
        label="tool_select",
    )
    picked_raw = raw.get("tools")
    if not isinstance(picked_raw, list):
        raise LLMClassificationError(
            f"tool_select: missing or invalid 'tools' list in {raw!r}"
        )

    unknown: list[str] = []
    optional: list[str] = []
    seen_optional: set[str] = set()
    for item in picked_raw:
        name = str(item).strip()
        if not name:
            continue
        if name not in registry._tools:
            unknown.append(name)
            continue
        if name not in always and name not in seen_optional:
            optional.append(name)
            seen_optional.add(name)
    if unknown:
        raise LLMClassificationError(
            f"tool_select: unknown tools {unknown}, available={all_names}"
        )

    # Soft budget: always-on tools are never dropped. max_tools_selected caps
    # LLM picks only (pin names the model listed count; unlisted pin does not).
    max_optional = platform_int("agent", "max_tools_selected", default=0)
    if max_optional and max_optional > 0 and len(optional) > max_optional:
        dropped = optional[max_optional:]
        optional = optional[:max_optional]
        log.info(
            "tool select budget: kept=%s dropped=%s max_optional=%s always=%s pin=%s domain=%s",
            optional,
            dropped,
            max_optional,
            len(always),
            sorted(pin),
            domain,
        )

    picked_set = set(always) | set(optional)
    offered_set = set(picked_set)
    if picked_set:
        offered_set |= pin
    offered = sorted(offered_set)
    picked = sorted(picked_set)
    if not picked:
        log.info("tool select: chat-only (no tools) domain=%s text=%.50s", domain, query)
    else:
        log.info(
            "tool select LLM: offered=%s picked=%s always=%s pin=%s domain=%s text=%.50s",
            offered,
            picked,
            sorted(always),
            sorted(pin),
            domain,
            query,
        )
    return ToolSelection(offered=offered, picked=picked)


async def classify_calendar_activities_llm(
    events: list[dict[str, Any]],
    *,
    taxonomy: dict[str, str],
    allowed: set[str],
) -> dict[str, str]:
    """Map event id → activity type. No keyword fallback."""
    if not events:
        return {}
    if not allowed:
        raise LLMClassificationError("calendar_activity: empty allowed type set")
    if not taxonomy:
        taxonomy = {t: t for t in sorted(allowed)}

    system = _load_prompt_file("calendar_activity_router.txt")
    payload_events = [
        {
            "id": str(ev.get("id") or "").strip(),
            "title": (ev.get("title") or "").strip(),
            "tag": (ev.get("tag") or None),
            "start": ev.get("start"),
            "end": ev.get("end"),
            "is_allday": bool(ev.get("is_allday")),
        }
        for ev in events
        if str(ev.get("id") or "").strip()
    ]
    if not payload_events:
        raise LLMClassificationError("calendar_activity: events missing ids")

    timeout = platform_float(
        "llm_classify", "calendar_activity_timeout_sec", default=60.0
    )
    raw = await asyncio.to_thread(
        _llm().chat_json_messages,
        [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {"taxonomy": taxonomy, "events": payload_events},
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=platform_float("llm_classify", "temperature", default=0.0),
        timeout=timeout,
        raise_on_error=True,
    )
    if not isinstance(raw, dict) or not raw:
        raise LLMClassificationError("calendar_activity: empty LLM JSON response")
    items = raw.get("items")
    if not isinstance(items, list):
        raise LLMClassificationError(
            f"calendar_activity: missing or invalid 'items' in {raw!r}"
        )

    wanted = {e["id"] for e in payload_events}
    out: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("id") or "").strip()
        typ = str(item.get("type") or "").strip()
        if not eid or eid not in wanted:
            continue
        if typ not in allowed:
            raise LLMClassificationError(
                f"calendar_activity: invalid type={typ!r} for id={eid}, "
                f"expected one of {sorted(allowed)}"
            )
        out[eid] = typ

    missing = wanted - set(out)
    if missing:
        raise LLMClassificationError(
            f"calendar_activity: LLM omitted event ids {sorted(missing)[:12]}"
        )
    log.info("calendar activity LLM: classified %s event(s)", len(out))
    return out


async def verify_grounding_llm(answer: str, tools: str) -> dict[str, Any]:
    """JSON: ok bool, optional rewrite. No keyword/regex grounding."""
    system = _load_prompt_file("verify_grounding.txt")
    raw = await _chat_json_classify(
        system,
        {"answer": answer, "tools": tools},
        label="verify_grounding",
    )
    ok_raw = raw.get("ok")
    if isinstance(ok_raw, bool):
        ok = ok_raw
    else:
        ok = str(ok_raw or "").strip().lower() in ("1", "true", "yes", "ok")
    rewrite = str(raw.get("rewrite") or "").strip()
    log.info("verify grounding LLM: ok=%s rewrite=%s", ok, bool(rewrite))
    return {"ok": ok, "rewrite": rewrite}
