"""Domain read-back checks, separate from language-model answer verification."""

import json


async def calendar(ctx, args, result):
    data = json.loads(result) if isinstance(result, str) else result
    if not isinstance(data, dict):
        return "unverified"
    rid = data.get("request_id")
    if not rid:
        return "rejected"
    from planning_bot.services.calendar_bridge import status

    state = status(ctx.user_id, rid)
    if state.get("status") == "created" and state.get("event_id"):
        return "verified"
    if state.get("status") in ("queued", "processing"):
        return "pending"
    return "outcome_unknown" if state.get("status") == "outcome_unknown" else "rejected"


async def kanban(ctx, args, result):
    if args.get("dry_run"):
        return "unverified"
    try:
        data = json.loads(result) if isinstance(result, str) else result
    except (ValueError, TypeError):
        return await kanban_diff(ctx, args)
    if not isinstance(data, dict) or data.get("status") != "ok":
        return "rejected"
    tid = data.get("task_id")
    if not tid:
        return "unverified"
    from planning_bot.services import kanban_parse as kp

    board = ctx.extras["bot"].kanban
    board.load()
    found = kp.find_task_block(kp.parse_sections(board.content), tid)
    if not found:
        return "outcome_unknown"
    column, _, block = found
    if column != data.get("column"):
        return "outcome_unknown"
    if args.get("action") == "complete" and "- [x]" not in block:
        return "outcome_unknown"
    if args.get("action") == "reschedule" and kp.metadata_from_block(block).get("deadline") != args.get("deadline"):
        return "outcome_unknown"
    return "verified"


async def kanban_diff(ctx, args):
    from planning_bot.core.config import DONE_COLUMN
    from planning_bot.services.kanban_agent import resolve_column_name

    board = ctx.extras["bot"].kanban
    board.load()
    after = {
        t["task_id"]: t
        for t in board.get_tasks(exclude_today=False, exclude_blocked=False, include_archive=True)
        if t.get("task_id")
    }
    before = ctx.extras.get("kanban_before", {})
    ids = ctx.extras.get("kanban_target_ids", [])
    action = args.get("action")
    if action == "create":
        from collections import Counter

        expected = [t.strip() for t in (args.get("titles") or [args.get("title", "")]) if t.strip()]
        added = [v for k, v in after.items() if k not in before]
        return "verified" if expected and Counter(t["title"] for t in added) == Counter(expected) else "unverified"
    if not ids:
        return "unverified"
    if action == "delete":
        return "verified" if all(i in before and i not in after for i in ids) else "unverified"
    if action in ("move", "complete"):
        target = DONE_COLUMN if action == "complete" else resolve_column_name(args.get("column", ""))
        if target and all(
            i in after and after[i].get("column") == target and (action != "complete" or after[i].get("completed"))
            for i in ids
        ):
            return "verified"
    return "unverified"
