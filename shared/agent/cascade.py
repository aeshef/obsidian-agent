"""Cheap-to-strong model cascade for the agent loop."""
from __future__ import annotations

from shared.agent.types import ModelRole
from shared.constants import DOMAIN_UNIFIED


def _cascade_block() -> dict:
    from shared.agent.config import load_models_config

    raw = load_models_config().get("cascade") or {}
    return raw if isinstance(raw, dict) else {}


def cascade_enabled() -> bool:
    raw = _cascade_block().get("enabled", True)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def long_question_chars() -> int:
    try:
        return max(0, int(_cascade_block().get("long_question_chars", 280)))
    except (TypeError, ValueError):
        return 280


def start_strong_domains() -> frozenset[str]:
    raw = _cascade_block().get("start_strong_domains")
    if isinstance(raw, list) and raw:
        return frozenset(str(d).strip() for d in raw if str(d).strip())
    return frozenset({DOMAIN_UNIFIED})


def initial_role(domain: str, question: str) -> ModelRole:
    """ANALYZE (cheap) unless the query is already a hard JOIN / long brief."""
    if not cascade_enabled():
        return ModelRole.ANALYZE
    if (domain or "").strip() in start_strong_domains():
        return ModelRole.CHAT
    limit = long_question_chars()
    if limit and len((question or "").strip()) >= limit:
        return ModelRole.CHAT
    return ModelRole.ANALYZE


def should_escalate_skipped_tools(
    *,
    domain: str,
    had_schemas: bool,
    tool_bodies: list[str],
) -> bool:
    """Flash answered without tools on a domain that normally must use them."""
    if not cascade_enabled() or not had_schemas or tool_bodies:
        return False
    from shared.agent.config import tools_first_iter_domains

    return (domain or "").strip() in tools_first_iter_domains()
