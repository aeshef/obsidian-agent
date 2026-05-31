"""Exact title/stem lookup in the knowledge index (no fuzzy ranking)."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from shared.domain_messages import dmsg


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().strip()
    s = re.sub(r"[\s_\-]+", " ", s)
    return s


def resolve_note_path(query: str, entries: list[dict[str, Any]]) -> tuple[str | None, str]:
    """Return (rel_path, reason). Reasons are configured in domain_messages.yaml."""
    q = _norm(query)
    if not q or not entries:
        return None, dmsg("note_lookup", "empty_query")

    q_compact = q.replace(" ", "")
    for e in entries:
        rel = e.get("rel_path")
        if not isinstance(rel, str):
            continue
        title = _norm(str(e.get("title") or ""))
        stem = _norm(rel.rsplit("/", 1)[-1].replace(".md", ""))
        stem_compact = stem.replace(" ", "")
        if title == q or stem_compact == q_compact:
            return rel, "exact title or stem"
        if q in _norm(rel):
            return rel, "exact path fragment"

    return None, dmsg("note_lookup", "no_exact_match")
