from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Any

import yaml

from knowledge_bot.core.config import load_config
from knowledge_bot.services.tag_normalize import is_malformed_tag


def extract_tags_from_note(note_path: Path) -> Set[str]:
    """English docstring omitted (see domain_messages.yaml)."""
    try:
        text = note_path.read_text(encoding="utf-8", errors="ignore")
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not match:
            return set()
        frontmatter = match.group(1)
        data = yaml.safe_load(frontmatter) or {}
        tags = data.get("tags", [])
        if isinstance(tags, list):
            return {str(tag).strip() for tag in tags if tag and not is_malformed_tag(tag)}
        return set()
    except Exception:
        return set()


def scan_all_notes(vault_path: Path) -> Dict[str, Dict[str, Any]]:
    """Module helper (user strings in YAML)."""
    from shared.vault_layout import knowledge_subdir

    db_root = vault_path / knowledge_subdir()
    if not db_root.exists():
        return {"tags": {}, "namespaces": {}, "total_notes": 0, "notes_with_tags": 0}
    
    tags_inventory: Dict[str, Dict[str, any]] = defaultdict(lambda: {"count": 0, "examples": []})
    namespaces: Dict[str, Set[str]] = defaultdict(set)
    total_notes = 0
    notes_with_tags = 0
    
    for note_path in db_root.rglob("*.md"):
        if "Export" in str(note_path):
            continue
        total_notes += 1
        tags = extract_tags_from_note(note_path)
        if tags:
            notes_with_tags += 1
            rel_path = note_path.relative_to(vault_path)
            for tag in tags:
                tag_str = str(tag).strip()
                if not tag_str:
                    continue
                tags_inventory[tag_str]["count"] += 1
                if len(tags_inventory[tag_str]["examples"]) < 3:
                    tags_inventory[tag_str]["examples"].append(str(rel_path))
                if "/" in tag_str:
                    namespace, value = tag_str.split("/", 1)
                    namespaces[namespace].add(value)
    
    namespaces_dict = {ns: sorted(values) for ns, values in namespaces.items()}
    
    tags_dict = {
        tag: {
            "count": info["count"],
            "examples": info["examples"][:3]
        }
        for tag, info in sorted(tags_inventory.items())
    }
    
    return {
        "tags": tags_dict,
        "namespaces": namespaces_dict,
        "total_notes": total_notes,
        "notes_with_tags": notes_with_tags,
        "notes_without_tags": total_notes - notes_with_tags,
    }


def _inventory_path(agent_config_path: Path) -> Path:
    p = agent_config_path / "tags_inventory.yaml"
    if p.exists():
        return p
    ex = agent_config_path / "tags_inventory.yaml.example"
    return ex if ex.exists() else p


def load_tags_inventory(agent_config_path: Path) -> Dict[str, Any]:
    """English docstring omitted (see domain_messages.yaml)."""
    inv_path = _inventory_path(agent_config_path)
    if not inv_path.exists():
        return {"tags": {}, "namespaces": {}, "total_notes": 0, "notes_with_tags": 0}
    try:
        data = yaml.safe_load(inv_path.read_text(encoding="utf-8")) or {}
        return {
            "tags": data.get("tags", {}),
            "namespaces": data.get("namespaces", {}),
            "total_notes": data.get("total_notes", 0),
            "notes_with_tags": data.get("notes_with_tags", 0)
        }
    except Exception:
        return {"tags": {}, "namespaces": {}, "total_notes": 0, "notes_with_tags": 0}


def save_tags_inventory(agent_config_path: Path, inventory: Dict[str, Any]) -> None:
    """English docstring omitted (see domain_messages.yaml)."""
    inv_path = agent_config_path / "tags_inventory.yaml"
    inv_path.write_text(
        yaml.safe_dump(inventory, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8"
    )


def rebuild_inventory() -> Dict[str, Any]:
    """English docstring omitted (see domain_messages.yaml)."""
    cfg = load_config()
    inventory = scan_all_notes(cfg.vault_path)
    save_tags_inventory(cfg.agent_config_path, inventory)
    return inventory


def update_inventory_with_new_tags(agent_config_path: Path, new_tags: List[str]) -> None:
    """English docstring omitted (see domain_messages.yaml)."""
    inventory = load_tags_inventory(agent_config_path)
    tags_dict = inventory.get("tags", {})
    namespaces_dict = inventory.get("namespaces", {})
    
    for tag in new_tags:
        tag_str = str(tag).strip()
        if not tag_str or is_malformed_tag(tag_str):
            continue
        if tag_str not in tags_dict:
            tags_dict[tag_str] = {"count": 0, "examples": []}
        tags_dict[tag_str]["count"] += 1
        if "/" in tag_str:
            namespace, value = tag_str.split("/", 1)
            if namespace not in namespaces_dict:
                namespaces_dict[namespace] = []
            if value not in namespaces_dict[namespace]:
                namespaces_dict[namespace].append(value)
                namespaces_dict[namespace].sort()
    
    inventory["tags"] = tags_dict
    inventory["namespaces"] = namespaces_dict
    save_tags_inventory(agent_config_path, inventory)


def _format_tags_prompt_block(
    inventory: Dict[str, Any],
    tags_dict: Dict[str, Dict[str, Any]],
    *,
    header_line: str,
    existing_line: str,
    rule_line: str,
    tag_line_limit: int = 20,
) -> str:
    from knowledge_bot.i18n.domain_text import tags_inv

    if not tags_dict:
        return header_line

    lines = [header_line, "", existing_line]
    by_namespace: Dict[str, List[tuple[str, int]]] = defaultdict(list)
    for tag, info in tags_dict.items():
        if is_malformed_tag(tag):
            continue
        count = int(info.get("count") or 0)
        if "/" in tag:
            namespace, value = tag.split("/", 1)
            by_namespace[namespace].append((value, count))
        else:
            by_namespace["_other"].append((tag, count))
    for namespace in sorted(by_namespace.keys()):
        if namespace == "_other":
            continue
        items = sorted(by_namespace[namespace], key=lambda x: -x[1])
        if items:
            lines.append(f"\n{namespace}/:")
            for value, count in items[:tag_line_limit]:
                lines.append(tags_inv("tag_line", namespace=namespace, value=value, count=count))
    lines.append("\n" + rule_line.strip())
    return "\n".join(lines)


def get_tags_inventory_for_prompt(agent_config_path: Path) -> str:
    """Full tag inventory for new notes (pipeline, set_type)."""
    from knowledge_bot.i18n.domain_text import tags_inv

    inventory = load_tags_inventory(agent_config_path)
    tags_dict = inventory.get("tags") or {}
    if not tags_dict:
        return tags_inv("empty")
    header = tags_inv(
        "header",
        total_notes=inventory.get("total_notes", 0),
        notes_with_tags=inventory.get("notes_with_tags", 0),
    )
    return _format_tags_prompt_block(
        inventory,
        tags_dict,
        header_line=header,
        existing_line=tags_inv("existing_tags"),
        rule_line=tags_inv("rule"),
        tag_line_limit=20,
    )


def get_tags_inventory_for_prompt_restricted(agent_config_path: Path, min_count: int = 2) -> str:
    """Only tags with count >= min_count (retag_notes, refill_singleton)."""
    from knowledge_bot.i18n.domain_text import tags_inv

    inventory = load_tags_inventory(agent_config_path)
    tags_dict = {
        t: info
        for t, info in (inventory.get("tags") or {}).items()
        if int(info.get("count") or 0) >= min_count
    }
    if not tags_dict:
        return tags_inv("empty_min_count")
    return _format_tags_prompt_block(
        inventory,
        tags_dict,
        header_line=tags_inv("header_min_count", min_count=min_count),
        existing_line=tags_inv("existing_strict"),
        rule_line=tags_inv("rule_strict"),
        tag_line_limit=30,
    )


if __name__ == "__main__":
    from knowledge_bot.i18n.domain_text import tags_inv

    inventory = rebuild_inventory()
    print(
        tags_inv(
            "cli_rebuilt",
            total_notes=inventory["total_notes"],
            notes_with_tags=inventory["notes_with_tags"],
        )
    )
    print(tags_inv("cli_unique", count=len(inventory["tags"])))
    print(tags_inv("cli_namespaces", count=len(inventory["namespaces"])))

