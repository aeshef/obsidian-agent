#!/usr/bin/env python3
from planning_bot.core.pdmsg import pdmsg
import os
import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

REMAP_ALL = '--remap-all' in sys.argv
NO_PROMOTE = '--no-promote' in sys.argv


def _mapping_limit(default: int) -> int:
    raw = os.environ.get("GOALS_MAPPING_LIMIT", "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def select_missing_tasks(all_tasks, existing_mapping, *, remap_all: bool = False):
    tasks_with_id = [t for t in all_tasks if t.get("task_id")]
    if remap_all:
        return tasks_with_id
    return [t for t in tasks_with_id if t["task_id"] not in existing_mapping]


def record_no_goal_mapping(goals_mapper, task_id: str, title: str) -> None:
    goals_mapper.mapping[task_id] = []
    goals_mapper.save_mapping(task_info={task_id: title})


def _process_tasks(goals_mapper, llm, missing, all_goals, limit: int) -> int:
    goals_by_id = {g["id"]: g.get("text", "?") for g in all_goals}
    logging.getLogger("llm").setLevel(logging.WARNING)  # (comment)
    to_process = missing[:limit]
    print(pdmsg("auto_549b646b63", _p1=len(all_goals), _p3=len(to_process)))
    mapped = 0
    for idx, task in enumerate(to_process, 1):
        task_id = task['task_id']
        title = task.get('title', '') or task.get('raw_text', '')[:200]
        category = task.get('category') or pdmsg("auto_1945da1fe5")

        print(f"[{idx}/{len(to_process)}] {title[:60]}...", end=" ", flush=True)
        try:
            result = llm.map_task_to_goals(title, category, all_goals)
            goal_ids = result.get('goal_ids', [])
            reasoning = result.get('reasoning', '').strip()

            if goal_ids:
                goals_mapper.add_task_mapping(task_id, goal_ids, task_title=title)
                mapped += 1
                goal_names = [goals_by_id.get(gid, f"??{gid}") for gid in goal_ids]
                print(f"✅ → {', '.join(goal_names)}")
            else:
                record_no_goal_mapping(goals_mapper, task_id, title)
                print(pdmsg("auto_4e30ce6f86"))

        except Exception as e:
            logger.error(f"❌ {task_id}: {e}")
            continue

    print(pdmsg("auto_1a09008344", _p1=mapped, _p3=len(missing)))
    return mapped


def main():
    from planning_bot.core.config import MAPPING_FILE
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.goals_mapper import GoalsMapper
    from planning_bot.core.llm import DeepSeekClient
    from shared.goals.mapping_files import (
        clear_remap_in_progress,
        load_mapping_titles,
        promote_mapping_file,
        staging_mapping_file,
        touch_remap_in_progress,
    )

    kanban = KanbanBoard()
    prod_mapper = GoalsMapper()
    llm = DeepSeekClient()

    if REMAP_ALL:
        staging_path = staging_mapping_file(prod_mapper.vault_path)
        production_path = prod_mapper.mapping_file
        goals_mapper = GoalsMapper(mapping_file=staging_path)
        goals_mapper.mapping = {}
        goals_mapper.task_titles = load_mapping_titles(production_path)

        logger.info(
            "Staging remap: production=%s staging=%s (production untouched until promote)",
            production_path,
            staging_path,
        )
        touch_remap_in_progress(
            prod_mapper.vault_path,
            staging=staging_path,
            production=production_path,
        )
        goals_mapper.save_mapping()

        all_tasks = kanban.get_tasks(exclude_today=False, exclude_blocked=False)
        missing = select_missing_tasks(all_tasks, {}, remap_all=True)
        limit = _mapping_limit(500)
        logger.info(pdmsg("auto_78daa6c5ee", _p1=len(missing)))
    else:
        goals_mapper = prod_mapper
        logger.info(pdmsg("auto_b01c8bed70"))
        all_tasks = kanban.get_tasks(exclude_today=False, exclude_blocked=True)
        tasks_with_id = [t for t in all_tasks if t.get('task_id')]
        missing = select_missing_tasks(all_tasks, goals_mapper.mapping, remap_all=False)
        limit = _mapping_limit(20)
        logger.info(pdmsg("auto_ffbd805644", _p1=len(tasks_with_id), _p3=len(missing)))

    if not missing:
        logger.info(pdmsg("auto_0848da3bdb"))
        if REMAP_ALL:
            clear_remap_in_progress(prod_mapper.vault_path)
        return 0

    all_goals = goals_mapper.get_all_goals()
    if not all_goals:
        logger.warning(pdmsg("auto_ad2a96d8e8"))
        if REMAP_ALL:
            clear_remap_in_progress(prod_mapper.vault_path)
        return 1

    try:
        _process_tasks(goals_mapper, llm, missing, all_goals, limit)
    except Exception:
        if REMAP_ALL:
            logger.error("Remap failed; staging kept at %s", goals_mapper.mapping_file)
        raise
    finally:
        if REMAP_ALL and NO_PROMOTE:
            logger.info("Skipping promote (--no-promote); staging at %s", goals_mapper.mapping_file)

    if REMAP_ALL and not NO_PROMOTE:
        promote_mapping_file(goals_mapper.mapping_file, production_path)
        clear_remap_in_progress(prod_mapper.vault_path)
        logger.info("Promoted staging mapping → %s", production_path)

    return 0


if __name__ == '__main__':
    sys.exit(main())
