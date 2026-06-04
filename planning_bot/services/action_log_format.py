"""Canonical markdown format for monthly action logs (write + repair)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict

# Written after every entry; must not come from pdmsg (dmsg strips trailing newlines).
ENTRY_TAIL = "\n\n---\n\n"

_GLUED_TYPE = re.compile(
    r"\*\*Тип:\*\* \{'(task_\w+)'\}\*\*Данные:\*\*",
    re.MULTILINE,
)
_GLUED_SEP = re.compile(r"---\s*##", re.MULTILINE)
_LOOSE_JSON_BLOCK = re.compile(
    r"\*\*Данные:\*\*\n+\n*```json\n+\n*",
    re.MULTILINE,
)


def format_log_entry(timestamp: str, action_type: str, data: Dict) -> str:
    """One log event block ending with ENTRY_TAIL."""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    return (
        f"## {timestamp}\n\n"
        f"**Тип:** {action_type}\n\n"
        f"**Данные:**\n```json\n{payload}\n```"
        f"{ENTRY_TAIL}"
    )


def gap_before_next_entry(log_file: Path) -> str:
    """Prefix to append when file already has content (fixes trailing --- without newline)."""
    size = log_file.stat().st_size
    if size == 0:
        return ""
    with open(log_file, "rb") as f:
        f.seek(max(0, size - 256))
        tail = f.read().decode("utf-8", errors="replace")
    if not tail:
        return ""
    if tail.endswith(ENTRY_TAIL) or tail.endswith("\n\n---\n\n"):
        return ""
    if tail.rstrip().endswith("---"):
        return "\n\n"
    if not tail.endswith("\n"):
        return "\n"
    if tail.rstrip().endswith("```"):
        return ENTRY_TAIL
    return "\n\n"


def needs_repair(content: str) -> bool:
    return bool(_GLUED_SEP.search(content) or _GLUED_TYPE.search(content) or "---##" in content)


def content_for_parse(content: str) -> str:
    """Normalize legacy glued logs in memory (parse/charts); does not write disk."""
    if not needs_repair(content):
        return content
    fixed, _ = repair_log_text(content)
    return fixed


def repair_log_text(content: str) -> tuple[str, int]:
    """Fix glued ---##, wrong **Тип:** line, and loose json fences."""
    n = 0

    def _type_repl(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        return f"**Тип:** {m.group(1)}\n\n**Данные:**"

    def _json_open(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        return "**Данные:**\n```json\n"

    def _close_after_json(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        return f"{m.group(1)}\n```\n\n"

    out = _GLUED_TYPE.sub(_type_repl, content)
    out = _GLUED_SEP.sub("---\n\n##", out)
    out = re.sub(r"\n```\n\n\n```json", "\n```json", out)
    out, c1 = _LOOSE_JSON_BLOCK.subn(_json_open, out)
    n += c1
    out, c2 = re.subn(r"(\n[}\]])\n+\n*```", _close_after_json, out)
    n += c2

    # Collapse duplicate separators before rewriting tails
    out, c3 = re.subn(r"(---\n\n){2,}", ENTRY_TAIL, out)
    n += c3
    # Ensure every ```json block is followed by separator when another ## follows
    out, c4 = re.subn(
        r"(```)\n+(## )",
        r"\1" + ENTRY_TAIL + r"\2",
        out,
    )
    n += c4

    if out and not out.endswith("\n"):
        out += "\n"
    return out, n
