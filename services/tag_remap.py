from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def flatten_mapping(m: dict[str, str]) -> dict[str, str]:
    """Module helper (user strings in YAML)."""
    if not m:
        return {}
    out: dict[str, str] = {}
    for k in m:
        v = m[k]
        if not v or v == k:
            continue
        seen: set[str] = {k}
        cur = v
        while cur in m and cur not in seen:
            seen.add(cur)
            nxt = m[cur]
            if nxt == cur:
                break
            cur = nxt
        if cur != k:
            out[k] = cur
    return out


def _remap_tag_list(
    tags: list[Any], final_map: dict[str, str]
) -> tuple[list[str], int]:
    if not tags:
        return [], 0
    changes = 0
    new_list: list[str] = []
    for t in tags:
        s = str(t).strip() if t else ""
        if not s:
            continue
        r = final_map.get(s, s)
        if r != s:
            changes += 1
        if r and r not in new_list:
            new_list.append(r)
    return sorted(new_list) if new_list else [], changes


def apply_tag_mappings(
    vault_path: Path,
    raw_mapping: dict[str, str],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Module helper (user strings in YAML)."""
    final_map = flatten_mapping({k: v for k, v in raw_mapping.items() if k and v})
    if not final_map:
        return {"ok": True, "notes_touched": 0, "tag_changes": 0, "paths": []}

    from shared.vault_layout import knowledge_subdir

    db = vault_path / knowledge_subdir()
    if not db.exists():
        return {"ok": False, "error": "knowledge subdir missing"}

    stats: dict[str, Any] = {
        "ok": True,
        "notes_touched": 0,
        "tag_changes": 0,
        "paths": [],
    }
    for path in sorted(db.rglob("*.md")):
        if "Export" in str(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not m:
            continue
        try:
            data = yaml.safe_load(m.group(1)) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        raw_tags = data.get("tags", [])
        if not isinstance(raw_tags, list) or not raw_tags:
            continue
        new_tags, ch = _remap_tag_list(raw_tags, final_map)
        if ch == 0:
            continue
        data["tags"] = new_tags
        new_fm = (
            yaml.dump(
                data,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            ).rstrip()
            + "\n"
        )
        rest = text[m.end() :]
        new_text = "---\n" + new_fm + "---\n" + rest
        rel = path.relative_to(vault_path)
        stats["paths"].append(str(rel))
        stats["notes_touched"] += 1
        stats["tag_changes"] += ch
        if not dry_run:
            path.write_text(new_text, encoding="utf-8")

    return stats


def extract_mapping_from_ontology_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    m = data.get("mappings")
    if not isinstance(m, dict):
        return {}
    return {
        str(k).strip(): str(v).strip()
        for k, v in m.items()
        if k and v and str(v).strip()
    }
