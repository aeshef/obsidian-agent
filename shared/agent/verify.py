"""Ground the draft answer against this-turn tool results via one LLM call.

No amount regex. Policy lives in config/agent/prompts/verify_grounding*.txt
and models.yaml verify.rewrite_meta_markers (drop audit-log rewrites).
On LLM failure the draft is passed through (fail open).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("shared.agent.verify")


@dataclass
class VerifyVerdict:
    ok: bool
    rewrite: str = ""


def _verify_block() -> dict:
    from shared.agent.config import load_models_config

    raw = load_models_config().get("verify") or {}
    return raw if isinstance(raw, dict) else {}


def _truthy(raw: object, *, default: bool = False) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in ("0", "false", "no", "off", "")


def verify_enabled() -> bool:
    return _truthy(_verify_block().get("enabled"), default=False)


def rewrite_meta_markers() -> list[str]:
    raw = _verify_block().get("rewrite_meta_markers") or []
    if not isinstance(raw, list):
        return []
    return [str(m).strip() for m in raw if str(m).strip()]


def rewrite_is_meta(rewrite: str) -> bool:
    """True when rewrite talks about the verifier instead of answering the user."""
    text = (rewrite or "").casefold()
    if not text:
        return False
    return any(m.casefold() in text for m in rewrite_meta_markers())


def tools_excerpt(tool_bodies: list[str], *, max_chars: int | None = None) -> str:
    blob = "\n".join(b.strip() for b in tool_bodies if (b or "").strip())
    blob = blob.strip()
    if max_chars is None:
        try:
            max_chars = int(_verify_block().get("tools_excerpt_max_chars") or 0)
        except (TypeError, ValueError):
            max_chars = 0
    if not max_chars or len(blob) <= max_chars:
        return blob
    return blob[: max_chars - 1].rstrip() + "…"


async def verify_draft(answer: str, tool_bodies: list[str]) -> VerifyVerdict:
    """Return whether `answer` is grounded. Optional rewrite is user-facing."""
    text = (answer or "").strip()
    if not verify_enabled() or not text:
        return VerifyVerdict(ok=True)
    if not any((b or "").strip() for b in tool_bodies):
        return VerifyVerdict(ok=True)
    try:
        from shared.agent.llm_classify import verify_grounding_llm

        raw = await verify_grounding_llm(text, tools_excerpt(tool_bodies))
        ok = bool(raw.get("ok"))
        rewrite = str(raw.get("rewrite") or "").strip()
        if rewrite and rewrite_is_meta(rewrite):
            log.warning("verify rewrite is audit-speak; dropping so cascade can retry")
            rewrite = ""
        return VerifyVerdict(ok=ok, rewrite=rewrite)
    except Exception:
        log.warning("verify llm failed; passing draft through", exc_info=True)
        return VerifyVerdict(ok=True)
