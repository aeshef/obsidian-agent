"""Cheap-to-strong model cascade for the agent loop (policy in models.yaml)."""
from __future__ import annotations

from shared.agent.types import ModelRole


def _cascade_block() -> dict:
    from shared.agent.config import load_models_config

    raw = load_models_config().get("cascade") or {}
    return raw if isinstance(raw, dict) else {}


def _escalate_block() -> dict:
    raw = _cascade_block().get("escalate") or {}
    return raw if isinstance(raw, dict) else {}


def _start_strong_block() -> dict:
    raw = _cascade_block().get("start_strong") or {}
    return raw if isinstance(raw, dict) else {}


def _truthy(raw: object, *, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in ("0", "false", "no", "off", "")


def _role_named(name: object, fallback: ModelRole) -> ModelRole:
    key = str(name or "").strip().lower()
    for role in ModelRole:
        if role.value == key:
            return role
    return fallback


def cascade_enabled() -> bool:
    return _truthy(_cascade_block().get("enabled"), default=False)


def cheap_role() -> ModelRole:
    return _role_named(_cascade_block().get("cheap_role"), ModelRole.ANALYZE)


def strong_role() -> ModelRole:
    return _role_named(_cascade_block().get("strong_role"), ModelRole.CHAT)


def long_question_chars() -> int:
    block = _start_strong_block()
    raw = block.get("min_question_chars", _cascade_block().get("long_question_chars"))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def start_strong_domains() -> frozenset[str]:
    block = _start_strong_block()
    raw = block.get("domains", _cascade_block().get("start_strong_domains"))
    if isinstance(raw, list):
        return frozenset(str(d).strip() for d in raw if str(d).strip())
    return frozenset()


def start_strong_cross_domain() -> bool:
    return _truthy(_start_strong_block().get("cross_domain"), default=False)


def looks_cross_domain(question: str) -> bool:
    """True when routing.yaml host.cross_domain_escalation patterns both match."""
    from shared.agent.config import load_routing_config

    t = (question or "").strip()
    if not t:
        return False
    host = load_routing_config().get("host") or {}
    esc = host.get("cross_domain_escalation") if isinstance(host, dict) else None
    if not isinstance(esc, dict):
        return False
    finance = str(esc.get("finance_pattern") or "").strip()
    planning = str(esc.get("planning_pattern") or "").strip()
    if not finance or not planning:
        return False
    import re

    try:
        money = re.compile(finance, re.IGNORECASE)
        plan = re.compile(planning, re.IGNORECASE)
    except re.error:
        return False
    return bool(money.search(t) and plan.search(t))


def escalate_ungrounded_claims() -> bool:
    return cascade_enabled() and _truthy(
        _escalate_block().get("ungrounded_claims"), default=False
    )


def initial_role(domain: str, question: str) -> ModelRole:
    """Cheap role unless YAML start_strong matches this turn."""
    if not cascade_enabled():
        return cheap_role()
    if (domain or "").strip() in start_strong_domains():
        return strong_role()
    if start_strong_cross_domain() and looks_cross_domain(question):
        return strong_role()
    limit = long_question_chars()
    if limit and len((question or "").strip()) >= limit:
        return strong_role()
    return cheap_role()


def should_escalate_skipped_tools(
    *,
    domain: str,
    had_schemas: bool,
    tool_bodies: list[str],
) -> bool:
    """Cheap model answered without tools when this turn actually picked some."""
    if not cascade_enabled() or not had_schemas or tool_bodies:
        return False
    raw = _escalate_block().get("skipped_tools")
    if raw is None or raw is False:
        return False
    if isinstance(raw, list):
        domains = frozenset(str(d).strip() for d in raw if str(d).strip())
    elif _truthy(raw, default=False):
        from shared.agent.config import tools_first_iter_domains

        domains = tools_first_iter_domains()
    else:
        return False
    return (domain or "").strip() in domains
