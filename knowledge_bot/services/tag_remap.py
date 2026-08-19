from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Facet `category/*` is type-specific (place / wishlist), not domain/tech.
# Never map wishlist hardware to domain/tech — use gadgets.
_TOPIC_TO_DOMAIN = {
    "topic/technology": "domain/tech",
    "topic/tech": "domain/tech",
}


@lru_cache(maxsize=1)
def taxonomy_ascii_map() -> dict[str, str]:
    """Cyrillic category/* aliases live in enums.yaml synonyms (not in Python)."""
    out = dict(_TOPIC_TO_DOMAIN)
    path = Path(__file__).resolve().parent.parent / "config" / "enums.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return out
    syn = data.get("synonyms") if isinstance(data, dict) else None
    cat = syn.get("category") if isinstance(syn, dict) else None
    if isinstance(cat, dict):
        for src, dst in cat.items():
            src_s, dst_s = str(src).strip(), str(dst).strip()
            if src_s and dst_s and src_s != dst_s:
                out[f"category/{src_s}"] = f"category/{dst_s}"
    return out


def __getattr__(name: str) -> Any:
    if name == "TAXONOMY_ASCII_MAP":
        return taxonomy_ascii_map()
    raise AttributeError(name)


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


def canonicalize_tags(tags: list[str]) -> list[str]:
    """Apply taxonomy_ascii_map (topic/technology → domain/tech, category aliases → ASCII)."""
    final_map = flatten_mapping(taxonomy_ascii_map())
    new_list, _ = _remap_tag_list(tags, final_map)
    return new_list


def remap_category_field(data: dict[str, Any], final_map: dict[str, str]) -> int:
    """Rewrite frontmatter `category:` when the tag map has category/old → category/new."""
    cat = data.get("category")
    if not isinstance(cat, str) or not cat.strip():
        return 0
    raw = cat.strip()
    old = f"category/{raw}"
    new_full = final_map.get(old, old)
    if not new_full.startswith("category/"):
        return 0
    new_val = new_full.split("/", 1)[1]
    if new_val == raw:
        return 0
    data["category"] = new_val
    return 1


def apply_tag_mappings(
    vault_path: Path,
    raw_mapping: dict[str, str],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Module helper (user strings in YAML)."""
    final_map = flatten_mapping({k: v for k, v in raw_mapping.items() if k and v})
    if not final_map:
        return {"ok": True, "notes_touched": 0, "tag_changes": 0, "field_changes": 0, "paths": []}

    from knowledge_bot.services.frontmatter_attachments import flatten_attachment_fields
    from shared.vault_layout import knowledge_subdir

    db = vault_path / knowledge_subdir()
    if not db.exists():
        return {"ok": False, "error": "knowledge subdir missing"}

    stats: dict[str, Any] = {
        "ok": True,
        "notes_touched": 0,
        "tag_changes": 0,
        "field_changes": 0,
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
        tag_ch = 0
        if isinstance(raw_tags, list) and raw_tags:
            new_tags, tag_ch = _remap_tag_list(raw_tags, final_map)
            if tag_ch:
                data["tags"] = new_tags
        field_ch = remap_category_field(data, final_map)
        if tag_ch == 0 and field_ch == 0:
            continue
        data = flatten_attachment_fields(data)
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
        stats["tag_changes"] += tag_ch
        stats["field_changes"] += field_ch
        if not dry_run:
            path.write_text(new_text, encoding="utf-8")

    return stats


def apply_taxonomy_ascii(
    vault_path: Path,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Idempotent Cyrillic category + topic/technology → ASCII. Safe to run on both sides."""
    return apply_tag_mappings(vault_path, taxonomy_ascii_map(), dry_run=dry_run)


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
