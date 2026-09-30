"""Kanban tools and conversational task references."""
from __future__ import annotations
from typing import Optional, List
from shared.agent.tools import tool
from shared.agent.types import AgentContext
from planning_bot.core.config import DEFAULT_CATEGORY, DEFAULT_PRIORITY
from planning_bot.core.pdmsg import pdmsg


def _bot(ctx):
    return ctx.extras["bot"]

@tool(category="tasks")
async def get_kanban(ctx: AgentContext, column: Optional[str] = None) -> str:
    """Kanban board snapshot (all columns or one)."""
    from planning_bot.core.config import KANBAN_COLUMNS, DONE_COLUMN

    bot = _bot(ctx)
    from shared.agent.platform_config import platform_int

    bot.kanban.load()
    tasks = bot.kanban.get_tasks(
        exclude_today=False,
        exclude_blocked=False,
        include_archive=True,
    )
    done_preview = max(1, platform_int("planning", "kanban_done_preview_max", default=1000))

    from planning_bot.services.reference_date import format_deadline_hint, reference_today_iso

    today = reference_today_iso()

    def fmt(t: dict) -> str:
        tid = t.get("task_id") or "—"
        pri = t.get("priority") or "—"
        cat = t.get("category") or "—"
        dl = format_deadline_hint(t.get("deadline"), today)
        done = pdmsg("agent_task_done_suffix") if t.get("completed") else ""
        return f"  [{tid}] [{pri}] {t.get('title', '')} | {cat}{dl}{done}"

    from planning_bot.services.kanban_agent import resolve_column_name

    if column:
        resolved = resolve_column_name(column)
        cols = [resolved] if resolved else KANBAN_COLUMNS
    else:
        cols = KANBAN_COLUMNS
    lines: list[str] = [
        pdmsg("agent_kanban_today_anchor", today=today),
        pdmsg("agent_kanban_today_hint"),
        pdmsg("agent_kanban_board_header"),
    ]
    shown = []
    for col in cols:
        all_col = [t for t in tasks if t.get("column") == col]
        col_tasks = all_col
        if col == DONE_COLUMN and len(all_col) > done_preview:
            col_tasks = sorted(
                all_col,
                key=lambda t: (t.get("created_date") or "", t.get("task_id") or ""),
                reverse=True,
            )[:done_preview]
            lines.append(
                pdmsg("agent_kanban_col_truncated", col=col, total=len(all_col), preview=done_preview)
            )
        else:
            lines.append(pdmsg("agent_kanban_col_count", col=col, count=len(col_tasks)))
        shown.extend(col_tasks)
        lines.extend(fmt(t) for t in col_tasks) if col_tasks else lines.append(pdmsg("agent_kanban_empty"))
    from planning_bot.services.task_followup import remember
    remember(ctx.user_id, shown)
    return "\n".join(lines)


@tool(category="tasks")
async def search_tasks(
    ctx: AgentContext,
    query: str = "",
    column: str = "",
    category: str = "",
    priority: str = "",
    deadline_from: str = "",
    deadline_to: str = "",
    created_from: str = "",
    created_to: str = "",
    sort_by: str = "",
    completed: Optional[bool] = None,
    limit: int = 25,
) -> str:
    """Search kanban: text, column, category, priority, deadline/created ranges (YYYY-MM-DD), sort_by=created_asc|created_desc|deadline."""
    from planning_bot.services.kanban_agent import filter_tasks, format_task_list

    bot = _bot(ctx)
    bot.kanban.load()
    tasks = bot.kanban.get_tasks(
        exclude_today=False,
        exclude_blocked=False,
        include_archive=True,
    )
    matched = filter_tasks(
        tasks,
        query=query,
        column=column,
        category=category,
        priority=priority,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        created_from=created_from,
        created_to=created_to,
        sort_by=sort_by,
        completed=completed,
        limit=limit,
    )
    from planning_bot.services.task_followup import remember
    remember(ctx.user_id, matched)
    return format_task_list(matched, header=pdmsg("agent_tasks_filter_header"))


@tool(category="tasks")
async def get_task_timeline(
    ctx: AgentContext,
    task_id: str = "",
    task_title: str = "",
) -> str:
    """One task: board metadata (created_date, column) + full log chain (created/moved/completed)."""
    from planning_bot.services.task_timeline_query import format_task_timeline

    bot = _bot(ctx)
    return format_task_timeline(
        bot.logger,
        bot.kanban,
        task_id=task_id,
        task_title=task_title,
    )


from unified_bot.integrations.verifiers import kanban as verify_kanban

@tool(category="tasks", serial=True, mutating=True, verifier=verify_kanban)
async def apply_kanban_task(
    ctx: AgentContext,
    action: str,
    dry_run: bool = False,
    task_id: str = "",
    title: str = "",
    titles: Optional[List[str]] = None,
    category: str = DEFAULT_CATEGORY,
    priority: str = DEFAULT_PRIORITY,
    column: str = "",
    all_matching: bool = False,
    position: int = 0,
    deadline: str = "",
) -> str:
    """Board mutation: create | move | complete | delete | reschedule | undo. Use stable task_id from history; position is the original displayed list, only if its ordering is unchanged. reschedule requires deadline YYYY-MM-DD. undo restores the last single move/complete/reschedule only if unchanged. Ambiguous references require choice. KANBAN_AGENT_WRITES=1."""
    from planning_bot.services.kanban_agent import apply_kanban_action

    bot = _bot(ctx)
    logger = bot.logger
    bot.kanban.load()
    from planning_bot.services import kanban_parse as kp
    from planning_bot.services.kanban_agent import resolve_task_ids
    sections=kp.parse_sections(bot.kanban.content)
    snapshot=bot.kanban.get_tasks(exclude_today=False,exclude_blocked=False,include_archive=True)
    ctx.extras['kanban_before']={t.get('task_id'):t for t in snapshot if t.get('task_id')}
    ctx.extras['kanban_target_ids']=resolve_task_ids(sections,task_id=task_id,title=title,all_matching=all_matching)[0] if action!='create' else []
    from planning_bot.services.task_followup import resolve_position, mutate
    if position:
        task_id = resolve_position(ctx.user_id, position)
    if action in ("undo", "reschedule") or (action in ("move", "complete") and not all_matching):
        return mutate(bot.kanban, ctx.user_id, action=action, task_id=task_id, title=title,
                      column=column, deadline=deadline, dry_run=dry_run, logger=logger)
    return apply_kanban_action(
        bot.kanban,
        action=action,
        dry_run=dry_run,
        task_id=task_id,
        title=title,
        titles=titles,
        category=category,
        priority=priority,
        column=column,
        all_matching=all_matching,
        logger=logger,
    )



@tool(category="tasks", read_only=True)
async def get_recent_task_references(ctx: AgentContext) -> str:
    """Read last task list positions and stable IDs for follow-ups; do not infer ordinals from a differently reordered assistant list."""
    import json
    from planning_bot.services.task_followup import load
    data=load(ctx.user_id)
    return json.dumps({"tasks":data.get("list",[]),"can_undo":bool(data.get("undo"))},ensure_ascii=False)
