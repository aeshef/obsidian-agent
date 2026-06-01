"""Extract key: value from Shortcuts / Obsidian blocks (structure, not NLU)."""
from __future__ import annotations

import re
from typing import Dict

_KV_LINE_RE = re.compile(r"^([a-z_][a-z0-9_]*)\s*:\s*(.*)$", re.IGNORECASE)


def extract_kv_fields(
    text: str,
    *,
    multiline_keys: frozenset[str] = frozenset({"sleep"}),
) -> Dict[str, str]:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    segments = re.split(r"(?m)^\s*---\s*$", text.strip())
    fields: Dict[str, str] = {}

    for seg in segments:
        lines = [ln.rstrip() for ln in seg.splitlines()]
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line:
                continue
            m = _KV_LINE_RE.match(line)
            if not m:
                continue
            key = m.group(1).lower()
            parts = [m.group(2).strip()] if m.group(2).strip() else []
            if key in multiline_keys:
                while i < len(lines):
                    nxt = lines[i].strip()
                    if not nxt:
                        i += 1
                        continue
                    if _KV_LINE_RE.match(nxt):
                        break
                    parts.append(nxt)
                    i += 1
            val = "\n".join(p for p in parts if p).strip()
            if val:
                fields[key] = val
            elif key not in fields:
                fields[key] = ""

    return fields


def safe_float(value: str) -> float | None:
    v = (value or "").strip().replace(",", ".")
    if not v or v in ("-", "—"):
        return None
    try:
        return round(float(v), 4)
    except (ValueError, TypeError):
        return None
