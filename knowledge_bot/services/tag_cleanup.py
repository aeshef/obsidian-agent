"""Cleanup helpers for malformed frontmatter tags in the knowledge vault."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from knowledge_bot.core.settings import load_enums_config
from knowledge_bot.services.frontmatter_attachments import flatten_attachment_fields
from knowledge_bot.services.tag_normalize import (
    clean_existing_tags,
    fallback_tags_for_type,
    is_malformed_tag,
    normalize_tags,
)
from shared.vault_layout import knowledge_subdir


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    if not text.startswith("---"):
        return None
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return None
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    return fm, text[end + len("\n---"):]


def _dump_frontmatter(fm: dict[str, Any], body: str) -> str:
    return (
        "---\n"
        + yaml.dump(
            flatten_attachment_fields(fm),
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        + "---"
        + body
    )


def sanitize_malformed_tags(
    vault: Path,
    agent_config_path: Path,
    *,
    apply: bool = True,
) -> list[tuple[str, list[str], list[str]]]:
    """Remove malformed tags such as `topic/[[note]]`; return changed rows."""
    enums_cfg = load_enums_config(agent_config_path)
    changed: list[tuple[str, list[str], list[str]]] = []
    root = vault / knowledge_subdir()
    if not root.is_dir():
        return changed

    for path in root.rglob("*.md"):
        if path.name.startswith("🗺️"):
            continue
        parsed = _split_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
        if not parsed:
            continue
        fm, body = parsed
        raw_tags = fm.get("tags")
        if not isinstance(raw_tags, list):
            continue
        malformed = [str(t).strip() for t in raw_tags if is_malformed_tag(t)]
        if not malformed:
            continue

        new_tags = clean_existing_tags(raw_tags)
        if not new_tags:
            note_type = str(fm.get("type") or "unknown")
            new_tags = normalize_tags(
                fallback_tags_for_type(
                    note_type,
                    form=fm.get("form"),
                    source=fm.get("source"),
                ),
                enums_cfg,
                note_type,
            )
        fm["tags"] = sorted(dict.fromkeys(new_tags))
        rel = path.relative_to(vault).as_posix()
        changed.append((rel, malformed, list(fm["tags"])))
        if apply:
            path.write_text(_dump_frontmatter(fm, body), encoding="utf-8")

    return changed
