from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_gold(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    queries = data.get("queries") if isinstance(data, dict) else data
    if not isinstance(queries, list):
        return []
    skip_status = {"needs_label", "draft"}
    out: list[dict[str, Any]] = []
    for i, row in enumerate(queries):
        if not isinstance(row, dict):
            continue
        q = str(row.get("query") or "").strip()
        rel = row.get("relevant_paths") or []
        if not q:
            continue
        if str(row.get("status") or "") in skip_status:
            continue
        if not isinstance(rel, list) or not rel:
            if str(row.get("bucket") or "") == "refuse":
                rel = []
            else:
                continue
        out.append(
            {
                "id": str(row.get("id") or f"q{i:03d}"),
                "bucket": str(row.get("bucket") or "unspecified"),
                "query": q,
                "relevant_paths": [str(p) for p in rel if p],
                "status": str(row.get("status") or "seed"),
            }
        )
    return out
