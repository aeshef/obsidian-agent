#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PARENT = PROJECT_ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from planning_bot.tools.vault_maintenance.kanban_ids import add_ids_to_tasks
from planning_bot.tools.vault_maintenance.kanban_sort import sort_kanban_tasks


def run_kanban_hygiene() -> bool:
    ids_ok = add_ids_to_tasks()
    sort_ok = sort_kanban_tasks()
    print(f"kanban_hygiene ids_ok={ids_ok} sort_ok={sort_ok}", flush=True)
    return bool(ids_ok and sort_ok)


if __name__ == "__main__":
    raise SystemExit(0 if run_kanban_hygiene() else 1)
