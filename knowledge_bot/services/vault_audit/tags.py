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
    import html
    from shared.obsidian_metric_cards import MetricCard, metric_cards_html
    from shared.obsidian_ui.config import ui_config
    L=ui_config()['labels']
    def panel(title, rows, limit=15):
        rendered=['<div class="au-audit-row"><span>'+html.escape(str(name))+'</span><strong>'+str(count)+'</strong></div>' for name,count in rows]
        body=''.join(rendered[:limit])
        if len(rendered)>limit:
            body+='<details><summary>+ '+str(len(rendered)-limit)+'</summary>'+''.join(rendered[limit:])+'</details>'
        return '<section class="au-audit-panel"><h3>'+html.escape(title)+'</h3>'+body+'</section>'
    cards=metric_cards_html([MetricCard(L['audit_notes'],str(data['total'])),MetricCard(L['audit_untagged'],str(data['without_tags'])),MetricCard(L['audit_tags'],str(data['unique']))])
    lines=[va('tags_title',knowledge_dir=knowledge_subdir()),'',cards,'', '<div class="au-audit-grid">'+panel('DOMAIN',data['domain_counts'])+panel('TOPIC',data['topic_counts'])+'</div>','']
    if data['without_tags']:
        lines+=['> [!warning] '+L['audit_untagged']]+['> - [['+p.relative_to(vault).as_posix()+']]' for p in data['untagged_paths'][:12]]+['']
    sparse=[('domain/'+n,c) for n,c in data['domain_single']]+[('topic/'+n,c) for n,c in data['topic_single']]
    if sparse:lines += [panel(L['audit_sparse'],sparse),'']
    other={k:v for k,v in data['other_ns'].items() if k not in LEGACY_NAMESPACES}
    if other:lines += ['<div class="au-audit-grid">'+''.join(panel(ns,rows,4) for ns,rows in sorted(other.items()))+'</div>','']
    return '\n'.join(lines)
