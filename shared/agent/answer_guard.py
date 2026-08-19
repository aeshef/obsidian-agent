"""Detect incomplete / leaked tool-call prose in model answers (not domain-specific)."""
from __future__ import annotations

import json
import re
from typing import Any

_DEFAULT_NARRATION = (
    r"(?i)\binvoking tool\b",
    r"(?i)\b(?:tool|function)\s+call\s*:",
    r"(?i)\bget_[a-z][a-z0-9_]*\s*\(",
    r"(?i)\b[a-z][a-z0-9_]*\s*\(\s*\{",
)
_DEFAULT_FETCH = (
    r"(?i)\b(?:i(?:'ll| will) (?:check|look|fetch|compute)|let me (?:check|look))\b",
)

_INVOKING = re.compile(
    r"(?is)invoking tool\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+with\s+(\{.*?\})(?:\s*\.\.\.)?",
)
_FUNC_JSON = re.compile(
    r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*(\{.*?\})\s*\)",
    re.DOTALL,
)


def _patterns(key: str, defaults: tuple[str, ...]) -> list[re.Pattern[str]]:
    from shared.agent.platform_config import platform_value

    raw = platform_value("answer_guard", key, default=None)
    items = list(defaults)
    if isinstance(raw, list) and raw:
        items = [str(x) for x in raw if str(x).strip()]
    out: list[re.Pattern[str]] = []
    for src in items:
        try:
            out.append(re.compile(src))
        except re.error:
            continue
    return out


def looks_like_tool_narration(text: str) -> bool:
    body = (text or "").strip()
    if not body:
        return False
    return any(p.search(body) for p in _patterns("tool_narration_patterns", _DEFAULT_NARRATION))


def _digit_count(text: str) -> int:
    return sum(ch.isdigit() for ch in text or "")


def looks_like_incomplete_fetch(text: str) -> bool:
    """True when the model announced a fetch/compute instead of answering with results."""
    from shared.agent.platform_config import platform_int

    body = (text or "").strip()
    if not body:
        return False
    cap = platform_int("answer_guard", "promised_fetch_max_chars", default=520)
    if cap and len(body) > cap:
        return False
    if "|" in body and body.count("|") >= 4:
        return False
    if "\t" in body and body.count("\n") >= 3:
        return False
    if _digit_count(body) >= 12:
        return False
    return any(p.search(body) for p in _patterns("promised_fetch_patterns", _DEFAULT_FETCH))


def strip_tool_narration(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if looks_like_tool_narration(line):
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    body = re.sub(r"(?is)invoking tool\s+\S+\s+with\s+\{.*?\}", "", body).strip()
    return body


def _as_tool_call(name: str, args: dict[str, Any], idx: int) -> dict[str, Any]:
    return {
        "id": f"text-{name}-{idx}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


def coerce_text_tool_calls(text: str) -> list[dict[str, Any]]:
    """Parse 'Invoking tool X with {...}' / name({...}) into OpenAI-style tool_calls."""
    body = (text or "").strip()
    if not body:
        return []
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _add(name: str, raw_args: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            return
        if not isinstance(args, dict):
            return
        key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
        if key in seen:
            return
        seen.add(key)
        found.append(_as_tool_call(name, args, len(found)))

    for m in _INVOKING.finditer(body):
        _add(m.group(1), m.group(2))
    if not found:
        for m in _FUNC_JSON.finditer(body):
            _add(m.group(1), m.group(2))
    return found
