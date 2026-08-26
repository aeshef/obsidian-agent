from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List
from planning_bot.core.pdmsg import pdmsg

from planning_bot.core.config import KANBAN_COLUMNS

if TYPE_CHECKING:
    from planning_bot.services.action_log import ActionLogger
    from planning_bot.services.goals import GoalsManager
    from planning_bot.services.kanban import KanbanBoard

log = logging.getLogger(__name__)


def assemble_planning_snapshot(
    *,
    kanban: "KanbanBoard",
    goals_manager: "GoalsManager",
    action_logger: "ActionLogger | None" = None,
) -> str:
    parts: List[str] = []

    if action_logger is not None:
        try:
            chain = action_logger.get_recent_events_chain()
            if chain:
                parts.append(chain)
        except Exception as e:
            log.debug("action log chain: %s", e)

    try:
        goals = goals_manager.get_goals()
        if goals:
            parts.append(pdmsg("auto_2a863a5e3a") + "\n".join(f"— {g}" for g in goals))
    except Exception as e:
        log.debug("goals: %s", e)

    try:
        qf = goals_manager.get_quarterly_focus()
        if qf:
            parts.append(pdmsg("auto_0a989cc886") + "\n".join(f"— {g}" for g in qf))
    except Exception as e:
        log.debug("quarterly focus: %s", e)

    try:
        gc = goals_manager.get_goals_context_what_to_do_only()
        if gc:
            parts.append(
                pdmsg("auto_1708d23066") + gc
            )
    except Exception as e:
        log.debug("goals_context: %s", e)

    try:
        all_tasks = kanban.get_tasks(exclude_today=False, exclude_blocked=False)

        def fmt(t: Dict) -> str:
            pri = t.get("priority") or "—"
            cat = t.get("category") or "—"
            dl = pdmsg("auto_5a82d75eb3", _p1=t['deadline']) if t.get("deadline") else ""
            done = pdmsg("auto_d80d7e46b1") if t.get("completed") else ""
            return f"  [{pri}] {t['title']} | {cat}{dl}{done}"

        by_col: Dict[str, List[Dict]] = {col: [] for col in KANBAN_COLUMNS}
        unknown_col: List[Dict] = []
        for t in all_tasks:
            col = t.get("column")
            if col in by_col:
                by_col[col].append(t)
            else:
                unknown_col.append(t)

        kanban_lines = [pdmsg("auto_05a5c6be34")]
        for col in KANBAN_COLUMNS:
            tasks = by_col[col]
            kanban_lines.append(f"{col} ({len(tasks)}):")
            if tasks:
                kanban_lines.extend(fmt(t) for t in tasks)
            else:
                kanban_lines.append(pdmsg("auto_937e1c141e"))
        if unknown_col:
            kanban_lines.append(pdmsg("auto_401e01315d", _p1=len(unknown_col)))
            kanban_lines.extend(fmt(t) for t in unknown_col)
        parts.append("\n".join(kanban_lines))
    except Exception as e:
        log.debug("kanban: %s", e)

    return "\n\n".join(parts)
