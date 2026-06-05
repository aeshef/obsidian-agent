"""Canonical markdown format for monthly action logs (write + repair)."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict

from planning_bot.core.pdmsg import pdmsg

ENTRY_TAIL = "\n\n---\n\n"
_GLUED_SEP = re.compile(r"---\s*##", re.MULTILINE)


def _type_label() -> str:
    return pdmsg("log_entry_type_label", default="**Type:**").strip() or "**Type:**"


def _data_label() -> str:
    return pdmsg("log_entry_data_label", default="**Data:**").strip() or "**Data:**"


@lru_cache(maxsize=1)
def _glued_type_re() -> re.Pattern[str]:
    t = re.escape(_type_label())
    d = re.escape(_data_label())
    return re.compile(rf"{t}\s*\{{'(task_\w+)'\}}{d}", re.MULTILINE)


@lru_cache(maxsize=1)
def _loose_json_block_re() -> re.Pattern[str]:
    """Match corrupted blocks only: 2+ blank lines between data label and ```json."""
    d = re.escape(_data_label())
    return re.compile(rf"{d}\n\n+\n*```json\n+\n*", re.MULTILINE)


def format_log_entry(timestamp: str, action_type: str, data: Dict) -> str:
    """One log entry block ending with ENTRY_TAIL."""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    t = _type_label()
    d = _data_label()
    return (
        f"## {timestamp}\n\n"
        f"{t} {action_type}\n\n"
        f"{d}\n```json\n{payload}\n```"
        f"{ENTRY_TAIL}"
    )


def gap_before_next_entry(log_file: Path) -> str:
    """Prefix when file already has content (fixes trailing --- without newline)."""
    size = log_file.stat().st_size
    if size == 0:
        return ""
    with open(log_file, "rb") as f:
        f.seek(max(0, size - 512))
        tail = f.read().decode("utf-8", errors="replace")
    if not tail:
        return ""
    if "---##" in tail or _GLUED_SEP.search(tail):
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
    return bool(_GLUED_SEP.search(content) or _glued_type_re().search(content) or "---##" in content)


def content_for_parse(content: str) -> str:
    """Normalize legacy glued logs in memory; does not write disk."""
    if not needs_repair(content):
        return content
    fixed, _ = repair_log_text(content)
    return fixed


def repair_log_text(content: str) -> tuple[str, int]:
    """Fix glued ---##, wrong type line, and loose json fences."""
    n = 0
    type_lbl = _type_label()
    data_lbl = _data_label()

    def _type_repl(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        return f"{type_lbl} {m.group(1)}\n\n{data_lbl}"

    def _json_open(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        return f"{data_lbl}\n```json\n"

    def _close_after_json(m: re.Match[str]) -> str:
        nonlocal n
        n += 1
        return f"{m.group(1)}\n```\n\n"

    out = _glued_type_re().sub(_type_repl, content)
    out = _GLUED_SEP.sub("---\n\n##", out)
    out = re.sub(r"\n```\n\n\n```json", "\n```json", out)
    out, c1 = _loose_json_block_re().subn(_json_open, out)
    n += c1
    out, c2 = re.subn(r"(\n[}\]])\n+\n*```", _close_after_json, out)
    n += c2
    out, c3 = re.subn(r"(---\n\n){2,}", ENTRY_TAIL, out)
    n += c3
    out, c4 = re.subn(
        r"(```)\n+(## )",
        r"\1" + ENTRY_TAIL + r"\2",
        out,
    )
    n += c4
    out, c5 = re.subn(r"\n{3,}", "\n\n", out)
    n += c5
    if out and not out.endswith("\n"):
        out += "\n"
    return out, n
