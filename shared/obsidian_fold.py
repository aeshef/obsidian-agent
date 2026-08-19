"""Foldable Obsidian sections with consistent callout chrome.

Prefer ``> [!note]-`` callouts (same look as other dashboard folds).
Tables → bullets. Embeds go inside the callout as ``> ![[…]]``.
Use ``force_details=True`` only when HTML ``<details>`` is required.
"""
from __future__ import annotations

import re
from typing import Iterable, Sequence

_SEP_CELL = re.compile(r"^:?-{3,}:?$")


def _iter_lines(parts: Iterable[object]) -> list[str]:
    out: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, (list, tuple)):
            items: Sequence[object] = part
        else:
            items = [part]
        for item in items:
            for line in str(item).splitlines():
                out.append(line.rstrip())
    while out and not out[-1].strip():
        out.pop()
    return out


def _is_table_sep(cells: Sequence[str]) -> bool:
    nonempty = [c for c in cells if c]
    return bool(nonempty) and all(_SEP_CELL.match(c) for c in nonempty)


def tables_to_bullets(lines: Sequence[str]) -> list[str]:
    """Replace GFM table blocks with ``- a · b · c`` bullets (Obsidian-safe)."""
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if not lines[i].strip().startswith("|"):
            out.append(lines[i])
            i += 1
            continue
        block: list[str] = []
        while i < n and lines[i].strip().startswith("|"):
            block.append(lines[i].strip())
            i += 1
        rows: list[list[str]] = []
        for row in block:
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if _is_table_sep(cells):
                continue
            rows.append(cells)
        if not rows:
            continue
        data = rows[1:] if len(rows) > 1 else rows
        for cells in data:
            cells = [c for c in cells if c]
            if cells:
                out.append("- " + " · ".join(cells))
        if i < n and lines[i].strip():
            out.append("")
    return out


def _is_rich(lines: Sequence[str]) -> bool:
    for ln in lines:
        s = ln.strip()
        if s.startswith("|") or s.startswith("![[") or s.startswith("```"):
            return True
        if s.startswith("<") and "img" in s.lower():
            return True
    return False


def _squeeze_blanks(lines: Sequence[str]) -> list[str]:
    out: list[str] = []
    prev_blank = True
    for ln in lines:
        blank = not ln.strip()
        if blank and prev_blank:
            continue
        out.append(ln)
        prev_blank = blank
    while out and not out[-1].strip():
        out.pop()
    return out


def fold_section(
    title: str,
    *parts: object,
    collapsed: bool = True,
    force_details: bool | None = None,
) -> list[str]:
    """Return markdown lines for a foldable block.

    Prefer Obsidian callouts (``> [!note]-``) so all folds share the same chrome.
    Tables → bullets. Embeds stay inside the callout as ``> ![[…]]`` (works in
    reading view; ``<details>`` only if ``force_details=True``).
    """
    title = (title or "").strip() or "Details"
    lines = _squeeze_blanks(tables_to_bullets(_iter_lines(parts)))
    if not lines:
        return []

    if force_details is True:
        open_attr = "" if collapsed else " open"
        body = "\n".join(lines).strip()
        return [
            f"<details{open_attr}>",
            f"<summary>{title}</summary>",
            "",
            body,
            "",
            "</details>",
            "",
        ]

    # Normalize: blank line before/after embeds inside the eventual callout body
    normalized: list[str] = []
    prev_kind = ""
    for ln in lines:
        s = ln.strip()
        if s.startswith("```"):
            kind = "fence"
        elif s.startswith("![["):
            kind = "embed"
        elif not s:
            kind = "blank"
        else:
            kind = "text"
        if normalized and kind in {"fence", "embed"} and prev_kind not in {"blank", kind, ""}:
            normalized.append("")
        if normalized and kind == "text" and prev_kind in {"embed", "fence"}:
            normalized.append("")
        normalized.append(ln)
        prev_kind = "blank" if kind == "blank" else kind
    body_lines = _squeeze_blanks(normalized)

    mark = "-" if collapsed else "+"
    inner = [f"> {ln}" if ln.strip() else ">" for ln in body_lines]
    while inner and inner[-1] == ">":
        inner.pop()
    return [f"> [!note]{mark} {title}", ">"] + inner + ["", ""]
