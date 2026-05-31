"""Parse JSON from LLM responses (including truncated by max_tokens)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger("shared.json_parse")

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _path_like_re() -> re.Pattern[str]:
    from shared.vault_layout import knowledge_path_pattern

    return knowledge_path_pattern()


def _preview_chars() -> int:
    from shared.agent.platform_config import platform_int

    return platform_int("json_parse", "error_preview_chars", default=400)


class LLMJsonParseError(ValueError):
    """Could not parse model response as JSON."""

    def __init__(
        self,
        message: str,
        *,
        raw_preview: str = "",
        finish_reason: str | None = None,
        truncated: bool = False,
    ):
        super().__init__(message)
        self.raw_preview = raw_preview
        self.finish_reason = finish_reason
        self.truncated = truncated


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = _FENCE_RE.sub("", t).strip()
    return t


def salvage_path_strings_from_text(text: str) -> list[str]:
    """Extract note-path-like strings from truncated JSON."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _path_like_re().finditer(text or ""):
        s = m.group(1).strip()
        if not s or s in seen:
            continue
        if "/" not in s and not s.endswith(".md"):
            continue
        seen.add(s)
        out.append(s)
    return out


def parse_json_object(
    text: str,
    *,
    finish_reason: str | None = None,
    allow_salvage: bool = True,
) -> dict[str, Any]:
    """Parse JSON object; on truncation try to salvage paths/candidates."""
    raw = _strip_fences(text)
    if not raw:
        raise LLMJsonParseError("empty LLM response", finish_reason=finish_reason)

    truncated = finish_reason == "length"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        if not allow_salvage:
            raise LLMJsonParseError(
                f"invalid JSON: {e}",
                raw_preview=raw[: _preview_chars()],
                finish_reason=finish_reason,
                truncated=truncated,
            ) from e
        salvaged = salvage_path_strings_from_text(raw)
        if salvaged:
            log.warning(
                "JSON parse failed (%s); salvaged %d path strings (finish_reason=%s)",
                e,
                len(salvaged),
                finish_reason,
            )
            return {"paths": salvaged, "_salvaged": True}
        raise LLMJsonParseError(
            f"invalid JSON: {e}",
            raw_preview=raw[: _preview_chars()],
            finish_reason=finish_reason,
            truncated=truncated,
        ) from e

    if isinstance(parsed, list):
        return {"paths": parsed}
    if not isinstance(parsed, dict):
        raise LLMJsonParseError(
            f"expected JSON object, got {type(parsed).__name__}",
            raw_preview=raw[:200],
            finish_reason=finish_reason,
            truncated=truncated,
        )
    if truncated and allow_salvage:
        for key in ("paths", "candidates", "rel_paths", "notes"):
            val = parsed.get(key)
            if isinstance(val, list) and val:
                parsed["_truncated"] = True
                break
    return parsed
