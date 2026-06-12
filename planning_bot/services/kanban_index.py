"""Build category/priority indexes from active + archive kanban files."""
from __future__ import annotations

import re
from pathlib import Path

from planning_bot.core.pdmsg import pdmsg
from shared.kanban_paths import iter_kanban_read_paths, read_merged_kanban_text


def _scan_kanban_text(text: str) -> tuple[dict[str, str], dict[str, str], set[str]]:
    cat_by_id: dict[str, str] = {}
    cat_by_title: dict[str, str] = {}
    prio_by_id: dict[str, str] = {}
    prio_by_title: dict[str, str] = {}
    active_ids: set[str] = set()

    task_pattern = r"- \[[ x]\] (.+?)(?=\n- \[|$)"
    for m in re.finditer(task_pattern, text, re.DOTALL):
        task_text = m.group(1).strip()
        title_line = task_text.splitlines()[0].strip() if task_text else ""
        title = title_line.strip()

        category_match = re.search(pdmsg("auto_8d7e383ebe"), task_text)
        priority_match = re.search(pdmsg("auto_a1fb4d656a"), task_text)
        id_match = re.search(r"🆔 ID:\s*([a-f0-9-]{6,})", task_text, re.IGNORECASE)
        completed = m.group(0).lstrip().startswith("- [x]")

        cat = category_match.group(1).strip() if category_match else ""
        pri = priority_match.group(1).strip() if priority_match else ""
        tid = id_match.group(1).strip().lower() if id_match else ""

        if cat:
            if tid:
                cat_by_id[tid] = cat
            if title:
                cat_by_title[title] = cat
        if pri:
            if tid:
                prio_by_id[tid] = pri
            if title:
                prio_by_title[title] = pri
        if tid and not completed:
            active_ids.add(tid)

    return (
        cat_by_id,
        cat_by_title,
        prio_by_id,
        prio_by_title,
        active_ids,
    )


def load_kanban_category_index(vault: Path) -> tuple[dict[str, str], dict[str, str]]:
    text = read_merged_kanban_text(vault)
    if not text.strip():
        return {}, {}
    cat_by_id, cat_by_title, _, _, _ = _scan_kanban_text(text)
    return cat_by_id, cat_by_title


def load_kanban_priority_index(vault: Path) -> tuple[dict[str, str], dict[str, str], set[str]]:
    text = read_merged_kanban_text(vault)
    if not text.strip():
        return {}, {}, set()
    cat_by_id, cat_by_title, prio_by_id, prio_by_title, active_ids = _scan_kanban_text(text)
    # active_ids: open tasks only — scan active file alone
    active_path = iter_kanban_read_paths(vault)[0]
    if active_path.is_file():
        _, _, _, _, active_ids = _scan_kanban_text(active_path.read_text(encoding="utf-8", errors="replace"))
    return prio_by_id, prio_by_title, active_ids
