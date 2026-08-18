"""Ground money amounts in the agent answer against tool outputs."""
from __future__ import annotations

import re

# Currency sign and Latin RUB/rub only in this module (CI: no Cyrillic in .py).
_K_SUFFIX = chr(0x43A)  # Cyrillic ka, "thousands" in RU money shorthand
_RUB = chr(0x20BD)
_NBSP = chr(0xA0)
_AMOUNT_RE = re.compile(
    r"(?P<num>\d(?:[\d\s]*\d)?(?:[.,]\d{1,2})?)\s*"
    rf"(?P<k>[k{_K_SUFFIX}])?\s*"
    rf"(?P<cur>{re.escape(_RUB)}|rub\.?|RUB)?",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
_BARE_INT_RE = re.compile(r"\d[\d\s]{1,14}\d")


def _parse_number(num: str, *, thousands_suffix: bool) -> int | None:
    compact = num.replace(" ", "").replace(_NBSP, "").replace(",", ".")
    try:
        value = float(compact)
    except ValueError:
        return None
    if thousands_suffix:
        value *= 1000.0
    return int(round(value))


def claimed_amounts(text: str) -> list[int]:
    """Integer amounts the answer asserts (must have currency or k-suffix)."""
    out: list[int] = []
    seen: set[int] = set()
    for m in _AMOUNT_RE.finditer(text or ""):
        if not m.group("cur") and not m.group("k"):
            continue
        parsed = _parse_number(m.group("num"), thousands_suffix=bool(m.group("k")))
        if parsed is None or parsed in seen:
            continue
        seen.add(parsed)
        out.append(parsed)
    return out


def tool_amounts(bodies: list[str]) -> set[int]:
    """Amounts available to ground against: marked money plus 3+ digit integers."""
    blob = "\n".join(bodies or [])
    found: set[int] = set()
    for m in _AMOUNT_RE.finditer(blob):
        parsed = _parse_number(m.group("num"), thousands_suffix=bool(m.group("k")))
        if parsed is not None:
            found.add(parsed)
    for m in _BARE_INT_RE.finditer(blob):
        raw = m.group(0).replace(" ", "").replace(_NBSP, "")
        if _YEAR_RE.match(raw):
            continue
        try:
            found.add(int(raw))
        except ValueError:
            continue
    return found


def ungrounded_amounts(answer: str, tool_bodies: list[str]) -> list[int]:
    """Claimed money figures that do not appear (as integers) in tool output."""
    claimed = claimed_amounts(answer)
    if not claimed:
        return []
    allowed = tool_amounts(tool_bodies)
    return [n for n in claimed if n not in allowed]


def format_amount_list(amounts: list[int]) -> str:
    return ", ".join(f"{n:,}".replace(",", " ") for n in amounts)


def tools_excerpt(tool_bodies: list[str], *, max_chars: int = 800) -> str:
    blob = "\n".join(b.strip() for b in tool_bodies if (b or "").strip())
    blob = blob.strip()
    if len(blob) <= max_chars:
        return blob
    return blob[: max_chars - 1].rstrip() + "…"
