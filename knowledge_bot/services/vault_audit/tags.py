"""Tags section for vault audit report (callout markdown + optional JSON)."""
from __future__ import annotations

import json
from pathlib import Path

from knowledge_bot.i18n.domain_text import vault_audit as va
from knowledge_bot.services.tags_inventory import scan_all_notes
from knowledge_bot.services.untagged_notes import find_untagged_note_paths
from shared.vault_layout import knowledge_subdir

LEGACY_NAMESPACES = frozenset({"priority", "language", "vibe"})


def _scan(vault: Path) -> dict:
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

    return {
        "total": total,
        "with_tags": with_tags,
        "without_tags": without_tags,
        "untagged_paths": untagged_paths,
        "unique": len(tags),
        "domain_counts": domain_counts,
        "topic_counts": topic_counts,
        "topic_single": [(v, c) for v, c in topic_counts if c <= 2],
        "domain_single": [(v, c) for v, c in domain_counts if c <= 2],
        "other_ns": other_ns,
        "tags": tags,
    }


def render_tags_report(vault: Path, *, as_json: bool = False) -> str:
    data = _scan(vault)
    if as_json:
        out = {
            "total_notes": data["total"],
            "notes_with_tags": data["with_tags"],
            "notes_without_tags": data["without_tags"],
            "untagged_paths": [p.relative_to(vault).as_posix() for p in data["untagged_paths"]],
            "unique_tags": data["unique"],
            "domain": {
                "total": len(data["domain_counts"]),
                "by_count": data["domain_counts"],
                "single_or_pair": data["domain_single"],
            },
            "topic": {
                "total": len(data["topic_counts"]),
                "by_count": data["topic_counts"],
                "single_or_pair": data["topic_single"],
            },
            "other_namespaces": {k: v for k, v in data["other_ns"].items()},
        }
        return json.dumps(out, ensure_ascii=False, indent=2)
    return render_tags_markdown(vault, data=data)


def render_tags_markdown(vault: Path, *, data: dict | None = None) -> str:
    """Human vault-audit tags section — callouts, no ASCII fences."""
    data = data or _scan(vault)
    kd = knowledge_subdir()
    lines: list[str] = [
        va("tags_title", knowledge_dir=kd),
        va(
            "tags_summary",
            total=data["total"],
            with_tags=data["with_tags"],
            without_tags=data["without_tags"],
        ),
        va("tags_unique", count=data["unique"]),
        "",
    ]

    if data["without_tags"]:
        lines.append(va("tags_untagged_header"))
        for p in data["untagged_paths"][:12]:
            lines.append(f"- `{p.relative_to(vault).as_posix()}`")
        extra = len(data["untagged_paths"]) - 12
        if extra > 0:
            lines.append(va("tags_untagged_more", count=extra))
        lines.append("")

    single_n = len(data["topic_single"]) + len(data["domain_single"])
    if single_n:
        lines.append(va("tags_topic_single_header"))
        lines.append(va("tags_topic_single_count", count=single_n))
        lines.append("")

    lines.append(va("tags_domain_header"))
    lines.append("")
    for value, count in data["domain_counts"][:12]:
        lines.append(va("tags_row", name=value, count=count))
    extra = len(data["domain_counts"]) - 12
    if extra > 0:
        lines.append(va("tags_untagged_more", count=extra))
    lines.append("")

    lines.append(va("tags_topic_header"))
    lines.append("")
    for value, count in data["topic_counts"][:15]:
        lines.append(va("tags_row", name=value, count=count))
    extra = len(data["topic_counts"]) - 15
    if extra > 0:
        lines.append(va("tags_untagged_more", count=extra))
    lines.append("")

    if data["topic_single"]:
        lines.append(va("tags_topic_single_header"))
        for value, count in sorted(data["topic_single"], key=lambda x: (x[1], x[0]))[:20]:
            lines.append(va("tags_topic_single_row", topic=value, count=count))
        extra = len(data["topic_single"]) - 20
        if extra > 0:
            lines.append(va("tags_untagged_more", count=extra))
        lines.append("")

    other = {k: v for k, v in data["other_ns"].items() if k not in LEGACY_NAMESPACES}
    if other:
        lines.append(va("tags_other_ns_header"))
        for ns in sorted(other.keys()):
            items = other[ns]
            top = ", ".join(f"{n} ({c})" for n, c in items[:4])
            lines.append(va("tags_other_ns_row", namespace=ns, count=len(items), top=top))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
