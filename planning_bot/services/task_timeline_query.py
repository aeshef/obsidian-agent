from __future__ import annotations

from typing import Any, Dict, List, Optional

from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.kanban import KanbanBoard


def find_task_on_board(
    board: KanbanBoard,
    *,
    task_id: str = "",
    task_title: str = "",
) -> Optional[Dict[str, Any]]:
    board.load()
    tasks = board.get_tasks(exclude_today=False, exclude_blocked=False)
    tid = (task_id or "").strip()
    title_q = (task_title or "").strip()
    if tid:
        for task in tasks:
            if task.get("task_id") == tid:
                return task
    if not title_q:
        return None
    title_low = title_q.lower()
    exact = [t for t in tasks if (t.get("title") or "") == title_q]
    if len(exact) == 1:
        return exact[0]
    partial = [t for t in tasks if title_low in (t.get("title") or "").lower()]
    if len(partial) == 1:
        return partial[0]
    return None


def format_task_timeline(
    logger,
    board: KanbanBoard,
    *,
    task_id: str = "",
    task_title: str = "",
) -> str:
    tid = (task_id or "").strip()
    title_q = (task_title or "").strip()
    if not tid and not title_q:
        return pdmsg("agent_task_timeline_need_id")

    task = find_task_on_board(board, task_id=tid, task_title=title_q)
    resolved_id = tid or (task or {}).get("task_id") or ""
    resolved_title = (task or {}).get("title") or title_q

    history: List[Dict] = []
    if logger is not None:
        history = logger.get_task_history(
            task_id=resolved_id or None,
            task_title=resolved_title if not resolved_id else None,
        )

    if not task and not history:
        return pdmsg("agent_task_timeline_not_found", query=resolved_title or resolved_id)

    lines: List[str] = [
        pdmsg(
            "agent_task_timeline_header",
            task_id=resolved_id or "—",
            title=(resolved_title or "—")[:120],
        )
    ]
    if task:
        lines.append(
            pdmsg(
                "agent_task_timeline_board",
                column=task.get("column") or "?",
                created=task.get("created_date") or "—",
                category=task.get("category") or "—",
                priority=task.get("priority") or "—",
                deadline=task.get("deadline") or "—",
                completed=bool(task.get("completed")),
            )
        )
    if not history:
        lines.append(pdmsg("agent_task_timeline_no_log"))
        return "\n".join(lines)

    from planning_bot.services.activity_log_query import format_task_event_dump

    dump = format_task_event_dump(
        history,
        history,
        title=pdmsg("agent_task_timeline_events_header", count=len(history)),
        slice_kind="all",
    )
    lines.append(dump)
    return "\n".join(lines)
