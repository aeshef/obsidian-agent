"""Kanban agent helpers: resolve tasks and apply create/move/complete."""
from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any, Dict, List, Optional

from planning_bot.core.config import (
    BACKLOG_COLUMN,
    DEFAULT_CATEGORY,
    DEFAULT_PRIORITY,
    DONE_COLUMN,
    KANBAN_COLUMNS,
    LOGS_DIR,
    PRIORITY_ORDER,
)
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.kanban import KanbanBoard
from planning_bot.services.kanban_lock import kanban_transaction
from planning_bot.services import kanban_parse as kp
from shared.parsing.date_range import resolve_date_range
from shared.parsing.iso_date import parse_iso_calendar_day

_parse_sections = kp.parse_sections
_find_task_block = kp.find_task_block


def kanban_writes_allowed() -> bool:
    return os.environ.get("KANBAN_AGENT_WRITES", "0").strip().lower() in ("1", "true", "yes")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def resolve_column_name(name: str) -> Optional[str]:
    raw = (name or "").strip()
    if not raw:
        return None
    if raw in KANBAN_COLUMNS:
        return raw
    n = _norm(raw)
    for col in KANBAN_COLUMNS:
        cn = _norm(col)
        if n == cn or n in cn:
            return col
    return None


def _kanban_search_limit_max() -> int:
    from shared.agent.platform_config import platform_int

    return max(1, platform_int("planning_kanban_search", "limit_max", default=100))


def _sort_tasks(tasks: List[Dict[str, Any]], sort_by: str) -> List[Dict[str, Any]]:
    sb = (sort_by or "").strip().lower()
    if sb in ("created", "created_asc", "oldest"):
        return sorted(
            tasks,
            key=lambda x: (x.get("created_date") or "9999", x.get("title") or ""),
        )
    if sb in ("created_desc", "newest"):
        return sorted(
            tasks,
            key=lambda x: (x.get("created_date") or "", x.get("title") or ""),
            reverse=True,
        )
    return sorted(
        tasks,
        key=lambda x: (
            x.get("deadline") or "9999",
            PRIORITY_ORDER.get(x.get("priority") or "", 9),
            x.get("title") or "",
        ),
    )


def filter_tasks(
    tasks: List[Dict[str, Any]],
    *,
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
    limit: int = 40,
) -> List[Dict[str, Any]]:
    q = _norm(query)
    col = _norm(column)
    cat = _norm(category)
    pri = _norm(priority)
    d_from = parse_iso_calendar_day(deadline_from)
    d_to = parse_iso_calendar_day(deadline_to)
    if d_from and d_to and d_from > d_to:
        d_from, d_to = d_to, d_from
    c_from = parse_iso_calendar_day(created_from)
    c_to = parse_iso_calendar_day(created_to)
    if c_from and c_to and c_from > c_to:
        c_from, c_to = c_to, c_from

    out: List[Dict[str, Any]] = []
    for t in tasks:
        if completed is not None and bool(t.get("completed")) != completed:
            continue
        if col and col not in _norm(t.get("column") or ""):
            continue
        if cat and cat not in _norm(t.get("category") or ""):
            continue
        if pri and pri not in _norm(t.get("priority") or ""):
            continue
        if q and q not in _norm(t.get("title") or ""):
            continue
        dl = t.get("deadline")
        if (d_from or d_to) and dl:
            try:
                dd = date.fromisoformat(str(dl)[:10])
            except ValueError:
                continue
            if d_from and dd < d_from:
                continue
            if d_to and dd > d_to:
                continue
        elif (d_from or d_to) and not dl:
            continue
        cd = t.get("created_date")
        if (c_from or c_to) and cd:
            try:
                created = date.fromisoformat(str(cd)[:10])
            except ValueError:
                continue
            if c_from and created < c_from:
                continue
            if c_to and created > c_to:
                continue
        elif (c_from or c_to) and not cd:
            continue
        out.append(t)
    out = _sort_tasks(out, sort_by)
    cap = _kanban_search_limit_max()
    return out[: max(1, min(int(limit), cap))]


def format_task_list(tasks: List[Dict[str, Any]], *, header: str) -> str:
    if not tasks:
        return pdmsg("auto_9b8cfe7614", header={header})
    lines = [header, pdmsg("auto_cd400107dc", _p1=len(tasks))]
    for t in tasks:
        tid = t.get("task_id") or "—"
        lines.append(
            pdmsg(
                "agent_task_filter_row",
                id=tid,
                title=(t.get("title") or "")[:80],
                column=t.get("column") or "?",
                category=t.get("category") or "—",
                priority=t.get("priority") or "—",
                deadline=t.get("deadline") or "—",
                created=t.get("created_date") or "—",
                completed=t.get("completed"),
            )
        )
    return "\n".join(lines)


def _rebuild_kanban_content(sections: Dict[str, List[str]], original: str) -> str:
    header_match = re.search(r"^---\s*\n\s*kanban-plugin: board\s*\n---\s*\n", original, re.MULTILINE)
    header = original[: header_match.end()] if header_match else "---\n\nkanban-plugin: board\n\n---\n\n"
    settings_match = re.search(r"%% kanban:settings", original)
    footer = original[settings_match.start() :] if settings_match else (
        '\n\n%% kanban:settings\n```\n{"kanban-plugin":"board"}\n```\n%%\n'
    )
    if not KANBAN_COLUMNS:
        return original
    order = list(KANBAN_COLUMNS)
    for col in sections:
        if col and col not in order:
            order.append(col)
    parts = [header]
    for col in order:
        if not col:
            continue
        parts.append(f"## {col}\n\n")
        for task in sections.get(col, []):
            parts.append(task + "\n\n")
    parts.append(footer.lstrip("\n") if not footer.startswith("\n") else footer)
    return "".join(parts)


_TASK_ID_HEX_RE = re.compile(r"^[0-9a-f]{6,8}$", re.IGNORECASE)
_HEX_ID_FIND = re.compile(r"[0-9a-f]{6,8}", re.IGNORECASE)


def _blocks_by_id(sections: Dict[str, List[str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for blocks in sections.values():
        for block in blocks:
            bid = kp.extract_id_from_block(block)
            if bid:
                out[bid] = block
    return out


def _match_ids_by_title(sections: Dict[str, List[str]], refs: List[str]) -> List[str]:
    by_id = _blocks_by_id(sections)
    matches: List[str] = []
    for bid, block in by_id.items():
        bt = _norm(kp.title_from_block(block))
        for ref in refs:
            nr = _norm(ref)
            if nr == _norm(bid) or (bt and (nr in bt or bt in nr)):
                matches.append(bid)
                break
    return list(dict.fromkeys(matches))


def _newest_id(sections: Dict[str, List[str]], ids: List[str]) -> str:
    by_id = _blocks_by_id(sections)

    def key(tid: str) -> str:
        return kp.created_date_from_block(by_id.get(tid, ""))

    return max(ids, key=key)


def resolve_task_ids(
    sections: Dict[str, List[str]],
    *,
    task_id: str = "",
    title: str = "",
    all_matching: bool = False,
) -> tuple[List[str], str]:
    tid = (task_id or "").strip()
    ttitle = (title or "").strip()
    hex_list = [h.lower() for h in _HEX_ID_FIND.findall(tid)]
    if len(hex_list) > 1:
        on_board = [h for h in hex_list if _find_task_block(sections, h)]
        missing = [h for h in hex_list if h not in on_board]
        if on_board:
            note = pdmsg("auto_061500b24f", _p1=', '.join(missing)) if missing else ""
            return on_board, note
        return [], pdmsg("auto_301215a223", _p1=', '.join(hex_list))

    if tid and _TASK_ID_HEX_RE.match(tid):
        needle = tid.lower()
        if _find_task_block(sections, needle):
            return [needle], ""
        return [], pdmsg("auto_5f0c96e62f", tid={tid})

    refs: List[str] = []
    if tid and not _TASK_ID_HEX_RE.match(tid):
        refs.append(tid)
    if ttitle:
        refs.append(ttitle)
    if not refs:
        return [], pdmsg("auto_382edf03c4")

    uniq = _match_ids_by_title(sections, refs)
    if len(uniq) == 1:
        return uniq, ""
    if len(uniq) > 1:
        if all_matching:
            return uniq, pdmsg("auto_6bb22dd815", _p1=len(uniq), _p3=', '.join(uniq))
        chosen = _newest_id(sections, uniq)
        return (
            [chosen],
            pdmsg("auto_d0350b047b", _p1=', '.join(uniq), _p3=chosen),
        )
    return [], pdmsg("kanban_task_not_found", ref=refs[0])


def resolve_task_ref(
    sections: Dict[str, List[str]],
    *,
    task_id: str = "",
    title: str = "",
    all_matching: bool = False,
) -> tuple[Optional[str], str]:
    ids, note = resolve_task_ids(
        sections, task_id=task_id, title=title, all_matching=all_matching
    )
    if not ids:
        return None, note
    return ids[0], note


def apply_kanban_action(
    board: KanbanBoard,
    *,
    action: str,
    dry_run: bool = False,
    task_id: str = "",
    title: str = "",
    titles: Optional[List[str]] = None,
    category: str = DEFAULT_CATEGORY,
    priority: str = DEFAULT_PRIORITY,
    column: str = "",
    all_matching: bool = False,
    logger=None,
) -> str:
    act = (action or "").strip().lower()
    if act not in ("create", "move", "complete"):
        return pdmsg("kanban_unknown_action", action=action)

    writes_ok = kanban_writes_allowed()
    if act == "create":
        from planning_bot.core.config import CATEGORIES
        from planning_bot.services.kanban_format import normalize_category, normalize_priority

        batch = [t.strip() for t in (titles or []) if (t or "").strip()]
        if not batch and (title or "").strip():
            batch = [title.strip()]
        if not batch:
            return pdmsg("auto_500c1d0683")

        cat_norm = normalize_category(category)
        pri_norm = normalize_priority(priority)

        if dry_run:
            lines = [
                pdmsg(
                    "auto_690e1f6cab",
                    _p1=t,
                    _p3=BACKLOG_COLUMN,
                    _p5=cat_norm,
                    _p7=pri_norm,
                )
                for t in batch
            ]
            return "\n".join(lines)
        if not writes_ok:
            return pdmsg("auto_9105976fe5")

        items = [(t, cat_norm, pri_norm) for t in batch]
        if len(items) == 1:
            tid = board.add_task_to_backlog(items[0][0], items[0][1], items[0][2])
            created = [(tid, items[0][0], cat_norm, pri_norm)]
        else:
            ids = board.add_tasks_to_backlog(items)
            created = list(zip(ids, batch, [cat_norm] * len(ids), [pri_norm] * len(ids)))

        for tid, t_title, c_norm, p_norm in created:
            if logger:
                logger.log_task_created(t_title, c_norm, p_norm, task_id=tid)
        _sync_state_file(board)

        lines_out: List[str] = []
        for tid, t_title, c_norm, p_norm in created:
            lines_out.append(
                pdmsg(
                    "kanban_task_created",
                    task_id=tid,
                    title=t_title,
                    category=c_norm,
                    priority=p_norm,
                )
            )
        out = "\n".join(lines_out)
        raw_cat = (category or "").strip().lower()
        if raw_cat and raw_cat != cat_norm:
            allowed = ", ".join(CATEGORIES) if CATEGORIES else cat_norm
            out += "\n" + pdmsg(
                "kanban_category_remapped",
                requested=category.strip(),
                used=cat_norm,
                allowed=allowed,
            )
        if len(created) > 1:
            out += "\n" + pdmsg("kanban_batch_created", count=len(created))
        return out

    if not (task_id or "").strip() and not (title or "").strip():
        return pdmsg("auto_5f55b37cbc", act={act})

    board.load()
    sections = _parse_sections(board.content)
    ids, note = resolve_task_ids(
        sections, task_id=task_id, title=title, all_matching=all_matching
    )
    if not ids:
        return note

    prefix = f"{note}\n" if note else ""
    if len(ids) == 1:
        one = _apply_move_or_complete(
            board,
            sections,
            act=act,
            task_id=ids[0],
            column=column,
            dry_run=dry_run,
            writes_ok=writes_ok,
            logger=logger,
        )
        return prefix + one

    lines: List[str] = []
    with kanban_transaction(board.file_path):
        board.load()
        sections = _parse_sections(board.content)
        for tid in ids:
            lines.append(
                _apply_move_or_complete(
                    board,
                    sections,
                    act=act,
                    task_id=tid,
                    column=column,
                    dry_run=dry_run,
                    writes_ok=writes_ok,
                    logger=logger,
                    reload=False,
                )
            )
            if not dry_run and writes_ok:
                sections = _parse_sections(board.content)
    return prefix + "\n".join(lines)


def _apply_move_or_complete(
    board: KanbanBoard,
    sections: Dict[str, List[str]],
    *,
    act: str,
    task_id: str,
    column: str,
    dry_run: bool,
    writes_ok: bool,
    logger,
    reload: bool = True,
) -> str:
    found = _find_task_block(sections, task_id)
    if not found:
        return pdmsg("auto_26f9884391", task_id={task_id})

    src_col, idx, block = found
    target_col = (column or "").strip() or (DONE_COLUMN if act == "complete" else "")

    if act == "complete":
        new_block = re.sub(r"- \[ \]", "- [x]", block, count=1)
        target_col = DONE_COLUMN
    elif act == "move":
        if not target_col:
            return pdmsg("auto_95291e7d4f")
        resolved = resolve_column_name(target_col) or target_col
        if resolved not in KANBAN_COLUMNS:
            return pdmsg(
                "kanban_unknown_column",
                column=target_col,
                allowed=", ".join(KANBAN_COLUMNS),
            )
        target_col = resolved
        new_block = block
    else:
        return f"unsupported {act}"

    if dry_run:
        return f"[dry-run] {act} id={task_id}: {src_col} → {target_col}"
    if not writes_ok:
        return (
            pdmsg("auto_a909f1b98e", act={act}, task_id={task_id}, target_col={target_col})
        )

    def _mutate() -> None:
        nonlocal sections
        if reload:
            board.load()
            sections = _parse_sections(board.content)
            found2 = _find_task_block(sections, task_id)
            if not found2:
                raise ValueError(pdmsg("auto_26f9884391", task_id={task_id}))
            src2, idx2, block2 = found2
            sections[src2].pop(idx2)
            blk = re.sub(r"- \[ \]", "- [x]", block2, count=1) if act == "complete" else block2
        else:
            sections[src_col].pop(idx)
            blk = new_block
        if target_col not in sections:
            sections[target_col] = []
        sections[target_col].append(blk)
        board.content = _rebuild_kanban_content(sections, board.content)
        board.save()

    if reload:
        with kanban_transaction(board.file_path):
            _mutate()
    else:
        _mutate()
    _sync_state_file(board)
    if logger:
        task_title = (kp.title_from_block(new_block) or "")[:80]
        category = kp.metadata_from_block(new_block).get("category")
        if act == "complete":
            logger.log_task_completed(task_title, task_id=task_id, category=category)
        else:
            logger.log_task_moved(
                task_title,
                src_col,
                target_col,
                task_id=task_id,
                category=category,
            )
    return f"OK: {act} id={task_id} → {target_col}"


def _sync_state_file(board: KanbanBoard) -> None:
    try:
        from planning_bot.services.kanban_monitor import KanbanMonitor

        KanbanMonitor()._sync_kanban_state_json()
    except Exception:
        pass
