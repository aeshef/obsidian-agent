"""Hierarchical finance category matching for agent filters."""
from __future__ import annotations


def normalize_category_query(query: str | None) -> str:
    """Normalize user/LLM category filters to a comparable stem.

    Accepts hierarchical globs the prompts historically suggested:
    ``Food/*``, ``Food*``, ``Food/`` → prefix stem ``food`` (match parent + children).
    """
    q = (query or "").strip().lower()
    if not q:
        return ""
    # Strip common wildcard suffixes before slash handling.
    while q.endswith("*"):
        q = q[:-1]
    if q.endswith("/"):
        q = q[:-1]
    return q.strip()


def category_matches(query: str | None, category: str | None) -> bool:
    """True if ``category`` belongs to the filter family in ``query``.

    Matching rules (case-insensitive):
    - empty query → match all
    - exact label
    - parent of a slash-path: ``Food`` matches ``Food/Out``
    - legacy substring (``out`` in ``Food/Out``)
    - ``Food/*`` / ``Food/`` normalized like parent prefix
    """
    stem = normalize_category_query(query)
    if not stem:
        return True
    cat = (category or "").strip().lower()
    if not cat:
        return False
    if cat == stem or cat.startswith(stem + "/"):
        return True
    # Keep substring fallback for leaf fragments ("out", "products").
    return stem in cat
