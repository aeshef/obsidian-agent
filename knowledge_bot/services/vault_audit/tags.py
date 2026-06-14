"""Tags section for vault audit report (read-only, i18n via domain_messages)."""
from __future__ import annotations

import json
from pathlib import Path

from knowledge_bot.i18n.domain_text import vault_audit as va
from knowledge_bot.services.tags_inventory import scan_all_notes
from knowledge_bot.services.untagged_notes import find_untagged_note_paths
from shared.vault_layout import knowledge_subdir

LEGACY_NAMESPACES = frozenset({"priority", "language", "vibe"})


def render_tags_report(vault: Path, *, as_json: bool = False) -> str:
    inv = scan_all_notes(vault)
    tags = inv.get("tags", {})
    total = inv.get("total_notes", 0)
    with_tags = inv.get("notes_with_tags", 0)
    without_tags = inv.get("notes_without_tags", total - with_tags)
    untagged_paths = find_untagged_note_paths(vault)

    domain_counts: list[tuple[str, int]] = []
    topic_counts: list[tuple[str, int]] = []
    other_ns: dict[str, list[tuple[str, int]]] = {}

    for tag, info in tags.items():
        count = info.get("count", 0)
        if "/" not in tag:
            other_ns.setdefault("_other", []).append((tag, count))
            continue
        ns, value = tag.split("/", 1)
        if ns == "domain":
            domain_counts.append((value, count))
        elif ns == "topic":
            topic_counts.append((value, count))
        elif ns not in LEGACY_NAMESPACES:
            other_ns.setdefault(ns, []).append((value, count))

    domain_counts.sort(key=lambda x: -x[1])
    topic_counts.sort(key=lambda x: -x[1])
    for k in other_ns:
        other_ns[k].sort(key=lambda x: -x[1])

    topic_single = [(v, c) for v, c in topic_counts if c <= 2]
    domain_single = [(v, c) for v, c in domain_counts if c <= 2]

    if as_json:
        out = {
            "total_notes": total,
            "notes_with_tags": with_tags,
            "notes_without_tags": without_tags,
            "untagged_paths": [p.relative_to(vault).as_posix() for p in untagged_paths],
            "unique_tags": len(tags),
            "domain": {"total": len(domain_counts), "by_count": domain_counts, "single_or_pair": domain_single},
            "topic": {"total": len(topic_counts), "by_count": topic_counts, "single_or_pair": topic_single},
            "other_namespaces": {k: v for k, v in other_ns.items()},
        }
        return json.dumps(out, ensure_ascii=False, indent=2)

    kd = knowledge_subdir()
    sep = va("line_sep")
    lines = [
        sep,
        va("tags_title", knowledge_dir=kd),
        sep,
        va("tags_summary", total=total, with_tags=with_tags, without_tags=without_tags),
    ]
    if without_tags:
        lines.append(va("tags_untagged_header"))
        for p in untagged_paths[:50]:
            lines.append(f"  - {p.relative_to(vault).as_posix()}")
        if len(untagged_paths) > 50:
            lines.append(va("tags_untagged_more", count=len(untagged_paths) - 50))
        lines.append("")
    lines.extend(
        [
            va("tags_unique", count=len(tags)),
            "",
            va("tags_domain_header"),
            va("line_dash"),
        ]
    )
    for value, count in domain_counts[:30]:
        lines.append(va("tags_row", name=value, count=count))
    lines.extend(["", va("tags_topic_header"), va("line_dash")])
    for value, count in topic_counts[:40]:
        lines.append(va("tags_row", name=value, count=count))
    lines.extend(
        [
            "",
            va("tags_topic_single_header"),
            va("line_dash"),
            va("tags_topic_single_count", count=len(topic_single)),
        ]
    )
    for value, count in sorted(topic_single, key=lambda x: (x[1], x[0])):
        lines.append(va("tags_topic_single_row", topic=value, count=count))
    lines.extend(
        [
            "",
            va("tags_domain_single_header"),
            va("line_dash"),
            va("tags_domain_single_count", count=len(domain_single)),
        ]
    )
    for value, count in sorted(domain_single, key=lambda x: (x[1], x[0])):
        lines.append(va("tags_domain_single_row", domain=value, count=count))
    lines.extend(["", va("tags_other_ns_header"), va("line_dash")])
    for ns in sorted(other_ns.keys()):
        if ns in LEGACY_NAMESPACES:
            continue
        items = other_ns[ns]
        lines.append(va("tags_other_ns_row", namespace=ns, count=len(items), top=str(items[:5])))
    lines.append(sep)
    return "\n".join(lines)
