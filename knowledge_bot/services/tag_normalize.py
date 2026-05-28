"""Tag normalization for knowledge ingest (shared by bot and maintenance scripts)."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Sequence, Set

from shared.yaml_config import load_merged_config

_TAG_CFG_DIR = Path(__file__).resolve().parent.parent / "config"
_TRANSLIT_PATH = _TAG_CFG_DIR / "cyrillic_translit.json"


def parse_tag_llm_response(tag_resp: Any) -> list[Any]:
    """Parse LLM tags step (json_object may wrap the array under alternate keys)."""
    if isinstance(tag_resp, list):
        return tag_resp
    if not isinstance(tag_resp, dict):
        return []
    if tag_resp.get("_llm_error") or tag_resp.get("error"):
        return []
    for key in ("tags", "paths", "result", "tag_list", "items"):
        val = tag_resp.get(key)
        if isinstance(val, list):
            return val
    for val in tag_resp.values():
        if isinstance(val, list) and val and all(isinstance(x, str) for x in val):
            return val
    return []


@lru_cache(maxsize=1)
def _tag_domains_cfg() -> dict:
    return load_merged_config(str(_TAG_CFG_DIR), "tag_domains")


@lru_cache(maxsize=1)
def _translit_table() -> dict[str, str]:
    if not _TRANSLIT_PATH.is_file():
        return {}
    data = json.loads(_TRANSLIT_PATH.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def fallback_tags_for_type(
    note_type: str,
    *,
    form: str | None = None,
    source: str | None = None,
) -> list[str]:
    """Minimal tags when LLM/normalize returned empty."""
    cfg = _tag_domains_cfg()
    default_type = str(cfg.get("default_type") or "knowledge").strip().lower()
    default_domain = str(cfg.get("default_domain") or "life")
    video_type = str(cfg.get("video_type") or "video").strip().lower()
    type_domains = cfg.get("type_domains") or {}
    topic_anchors = cfg.get("topic_anchors") or {}
    known_sources = {str(s).lower() for s in (cfg.get("known_sources") or [])}
    media_types = {str(x).lower() for x in (cfg.get("media_types_with_topic_anchor") or [])}

    t = (note_type or default_type).strip().lower()
    out: list[str] = []
    domain = str(type_domains.get(t) or default_domain)
    out.append(f"domain/{domain}")
    if t in media_types:
        anchor = topic_anchors.get(t)
        if anchor:
            out.append(f"topic/{anchor}")
    src = (source or "").strip().lower()
    if src in known_sources:
        out.append(f"source/{src}")
    elif form in ("video", "link") and t == video_type:
        pass
    return out


def translit_ru(s: str) -> str:
    table = _translit_table()
    if not table:
        return s
    return s.translate(str.maketrans(table))


def slug_ascii(s: str) -> str:
    s = translit_ru(s).lower().replace(" ", "-").replace("_", "-")
    s = re.sub(r"[^a-z0-9\-/]", "", s)
    return re.sub(r"-+", "-", s).strip("-")


def normalize_tags(
    tag_candidates: Sequence[Any],
    enums_cfg,
    note_type: str,
    *,
    allowed_tags: Optional[Set[str]] = None,
) -> list[str]:
    """Normalize tags to ASCII slugs; apply enums and synonyms."""
    tag_values: list[str] = []
    for tag in tag_candidates:
        if not isinstance(tag, str) or "/" not in tag:
            continue
        ns, _, val = tag.strip().partition("/")
        ns = (ns or "").strip().lower()
        raw_val = (val or "").strip()
        syn_map = getattr(enums_cfg, "synonyms", {}).get(ns, {})
        mapped = syn_map.get(raw_val.lower())
        if mapped:
            raw_val = mapped
        cand_slug = slug_ascii(raw_val)
        per_type_enums = enums_cfg.per_type.get(note_type, {})
        allowed_list = (enums_cfg.common.get(ns) or per_type_enums.get(ns)) or []
        is_controlled = ns in enums_cfg.namespaces_controlled
        if is_controlled and allowed_list:
            chosen = None
            for allowed_val in allowed_list:
                if slug_ascii(str(allowed_val)) == cand_slug:
                    chosen = allowed_val
                    break
            if chosen:
                tag_values.append(f"{ns}/{chosen}")
        elif ns and cand_slug:
            tag_values.append(f"{ns}/{cand_slug}")

    filtered: list[str] = []
    per_type_enums = enums_cfg.per_type.get(note_type, {})
    for tag in tag_values:
        if allowed_tags is not None and tag not in allowed_tags:
            continue
        ns, _, value = tag.partition("/")
        if ns in enums_cfg.namespaces_controlled:
            allowed = enums_cfg.common.get(ns) or per_type_enums.get(ns)
            if allowed and value in allowed:
                filtered.append(tag)
        else:
            filtered.append(tag)
    return sorted(dict.fromkeys(filtered))
