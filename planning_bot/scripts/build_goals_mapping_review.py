#!/usr/bin/env python3
"""Build collapsible goals↔tasks mapping review (prompt tuning, half-year revision)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from planning_bot.core.pdmsg import pdmsg
from shared.goals.mapping_review import (
    build_review_data,
    render_goals_mapping_review,
    review_to_json,
)
from shared.vault_paths_config import dashboards_sub, folder, vault_file, vault_rel_path


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / folder("tasks")).is_dir() and (p / folder("goals")).is_dir():
            return p
    return start.parents[3]


def main() -> int:
    os.environ.pop("PYTHONPATH", None)
    from shared.domain_messages import clear_domain_messages_cache
    from shared.locale import agent_locale
    from planning_bot.core.config import _kanban_schema
    from planning_bot.services.goals_mapper import GoalsMapper
    from planning_bot.services.kanban import KanbanBoard

    clear_domain_messages_cache()
    agent_locale()

    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=str)
    ap.add_argument(
        "--reconcile",
        action="store_true",
        help="Persist mapping cleanup (orphan goal IDs; optional ghost tasks with --remove-ghost-tasks)",
    )
    ap.add_argument(
        "--remove-ghost-tasks",
        action="store_true",
        help="With --reconcile: drop mappings for task_ids absent from board+archive",
    )
    ap.add_argument("--json", action="store_true", help="Also write goals_mapping_review.json under dashboards/data")
    args = ap.parse_args()

    vault = Path(args.vault).resolve() if args.vault else _discover_vault(Path(__file__).resolve())

    kanban = KanbanBoard()
    tasks = kanban.get_tasks(exclude_today=False, exclude_blocked=False, include_archive=True)
    tasks_by_id = {t["task_id"]: t for t in tasks if t.get("task_id")}
    known_task_ids = set(tasks_by_id.keys())

    mapper = GoalsMapper()
    readable_mapping = None
    if mapper.mapping_file.is_file():
        try:
            raw = json.loads(mapper.mapping_file.read_text(encoding="utf-8"))
            readable_mapping = raw.get("readable_mapping")
        except (OSError, json.JSONDecodeError, ValueError):
            readable_mapping = None

    if args.reconcile:
        stats = mapper.reconcile_mapping(
            known_task_ids=known_task_ids,
            persist=True,
            remove_ghost_tasks=args.remove_ghost_tasks,
        )
        print(pdmsg("goals_mapping_review_reconcile_done", **stats))

    priority_emojis = (_kanban_schema().get("priority_emojis") or {})

    data = build_review_data(
        mapper.goals,
        mapper.mapping,
        tasks_by_id,
        mapper.task_titles,
        readable_mapping=readable_mapping,
    )

    out_md = vault / folder("goals") / vault_file("goals_mapping_review_md")
    body = render_goals_mapping_review(
        data, pdmsg, _kanban_schema().get("priority_emojis") or {}
    )
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(body, encoding="utf-8")
    print(f"OK: {out_md}")

    if args.json:
        out_json = (
            vault
            / folder("dashboards")
            / dashboards_sub("data")
            / vault_rel_path("goals_mapping_review_json")
        )
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(review_to_json(data), encoding="utf-8")
        print(f"OK: {out_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
