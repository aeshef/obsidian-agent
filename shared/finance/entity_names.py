"""Account/category name matching: normalized equality only (NLU provides canonical from context)."""
from __future__ import annotations

import re


def normalize_label(name: str) -> str:
    return re.sub(r"\s+", "", (name or "").lower().strip())


def labels_equal(a: str, b: str) -> bool:
    return normalize_label(a) == normalize_label(b)


def find_matching_label(requested: str, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if labels_equal(requested, candidate):
            return candidate
    return None
