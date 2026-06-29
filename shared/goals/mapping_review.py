"""Goals↔tasks mapping review — Obsidian-native markdown for prompt tuning."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set


def format_quarter_label(quarter: str) -> str:
    q = (quarter or "").strip()
    if not q:
        return ""
    if len(q) >= 2 and q[0].upper() == "Q" and q[1].isdigit():
        return q if q[0] == "Q" else f"Q{q[1:]}"
    return f"Q{q}"


def sanitize_inline(text: str, *, max_len: int = 140) -> str:
    """Single-line safe text for callouts and table cells."""
    s = re.sub(r"\s+", " ", (text or "").replace("\r", " ").replace("\n", " ")).strip()
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _priority_emoji(priority: str | None, emojis: Dict[str, str]) -> str:
    return emojis.get(priority or "", "⚪")


def _goal_sort_key(goal: Dict[str, Any]) -> tuple:
    q = format_quarter_label(goal.get("quarter") or "")
    qn = int(q[1]) if len(q) == 2 and q[1].isdigit() else 99
    open_first = 0 if goal.get("open_count", 0) > 0 else 1
    return (open_first, qn, goal.get("category") or "", goal.get("priority") or "", goal.get("text") or "")


def collect_orphan_goal_refs(
    goals: Dict[str, Dict],
    readable_mapping: Dict[str, Any] | None,
) -> List[Dict[str, str]]:
    valid = set(goals.keys())
    seen: Set[str] = set()
    orphans: List[Dict[str, str]] = []
    if not readable_mapping:
        return orphans
    for info in readable_mapping.values():
        for g in info.get("goals") or []:
            gid = g.get("id")
            if not gid or gid in valid or gid in seen:
                continue
            seen.add(gid)
            orphans.append({"id": gid, "text": sanitize_inline(g.get("text") or "?")})
    return sorted(orphans, key=lambda x: x["text"])


def collect_multi_goal_tasks(
    mapping: Dict[str, List[str]],
    tasks_by_id: Dict[str, Dict],
    task_titles: Dict[str, str],
    *,
    min_goals: int = 3,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for task_id, goal_ids in mapping.items():
        unique = sorted({g for g in goal_ids if g})
        if len(unique) < min_goals:
            continue
        task = tasks_by_id.get(task_id) or {}
        title = sanitize_inline(task.get("title") or task_titles.get(task_id) or task_id)
        out.append(
            {
                "task_id": task_id,
                "title": title,
                "goal_count": len(unique),
                "goal_ids": unique,
                "completed": bool(task.get("completed")),
            }
        )
    out.sort(key=lambda x: (-x["goal_count"], x["title"].lower()))
    return out


def _task_entry(task_id: str, task: Dict | None, task_titles: Dict[str, str]) -> Dict[str, Any]:
    title = sanitize_inline((task or {}).get("title") or task_titles.get(task_id) or task_id)
    return {
        "task_id": task_id,
        "title": title,
        "completed": bool((task or {}).get("completed")),
        "column": sanitize_inline((task or {}).get("column") or ""),
        "source": (task or {}).get("source") or "",
    }


def build_review_data(
    goals: Dict[str, Dict],
    mapping: Dict[str, List[str]],
    tasks_by_id: Dict[str, Dict],
    task_titles: Dict[str, str],
    *,
    readable_mapping: Dict[str, Any] | None = None,
    multi_goal_threshold: int = 3,
) -> Dict[str, Any]:
    goal_tasks: Dict[str, List[Dict[str, Any]]] = {gid: [] for gid in goals}
    mapped_task_ids: Set[str] = set()

    for task_id, goal_ids in mapping.items():
        if not goal_ids:
            continue
        mapped_task_ids.add(task_id)
        entry = _task_entry(task_id, tasks_by_id.get(task_id), task_titles)
        for gid in goal_ids:
            if gid in goal_tasks:
                goal_tasks[gid].append(entry)

    for gid in goal_tasks:
        goal_tasks[gid].sort(key=lambda t: (t["completed"], t["title"].lower()))

    goals_out: List[Dict[str, Any]] = []
    for gid, meta in goals.items():
        tasks = goal_tasks.get(gid) or []
        done = sum(1 for t in tasks if t["completed"])
        goals_out.append(
            {
                "id": gid,
                "text": sanitize_inline(meta.get("text") or ""),
                "category": meta.get("category") or "",
                "priority": meta.get("priority") or "",
                "quarter": meta.get("quarter") or "",
                "context": sanitize_inline(meta.get("context") or "", max_len=260),
                "include": sanitize_inline(meta.get("include") or "", max_len=260),
                "exclude": sanitize_inline(meta.get("exclude") or "", max_len=260),
                "success": sanitize_inline(meta.get("success") or "", max_len=260),
                "tasks": tasks,
                "open_count": len(tasks) - done,
                "done_count": done,
            }
        )
    goals_out.sort(key=_goal_sort_key)

    unmapped_goals = [g for g in goals_out if not g["tasks"]]
    goals_with_tasks = [g for g in goals_out if g["tasks"]]

    unmapped_tasks: List[Dict[str, Any]] = []
    for task_id, task in tasks_by_id.items():
        if task_id in mapped_task_ids:
            continue
        unmapped_tasks.append(_task_entry(task_id, task, task_titles))
    unmapped_tasks.sort(key=lambda t: (t["completed"], t["title"].lower()))
    unmapped_open = [t for t in unmapped_tasks if not t["completed"]]
    unmapped_done = [t for t in unmapped_tasks if t["completed"]]

    open_mapped = sum(
        1
        for task_id, goal_ids in mapping.items()
        if goal_ids and not (tasks_by_id.get(task_id) or {}).get("completed")
    )

    ts = datetime.now()
    return {
        "generated_at": ts.strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "active_goals": len(goals),
            "goals_with_tasks": len(goals_with_tasks),
            "goals_without_tasks": len(unmapped_goals),
            "mapped_task_refs": len(mapped_task_ids),
            "open_mapped_tasks": open_mapped,
            "unmapped_board_tasks": len(unmapped_tasks),
            "open_unmapped_tasks": len(unmapped_open),
        },
        "orphan_goal_refs": collect_orphan_goal_refs(goals, readable_mapping),
        "multi_goal_tasks": collect_multi_goal_tasks(
            mapping, tasks_by_id, task_titles, min_goals=multi_goal_threshold
        ),
        "goals": goals_with_tasks,
        "unmapped_goals": unmapped_goals,
        "unmapped_tasks": unmapped_tasks,
        "unmapped_open": unmapped_open,
        "unmapped_done": unmapped_done,
    }


def _format_column(task: Dict[str, Any], msg: Callable[[str], str]) -> str:
    col = task.get("column") or "—"
    if task.get("source") == "archive":
        return f"{col} ({msg('goals_mapping_review_source_archive')})"
    return col


def _task_bullet(task: Dict[str, Any], msg: Callable[[str], str]) -> str:
    mark = msg("goals_mapping_review_status_done" if task["completed"] else "goals_mapping_review_status_open")
    col = _format_column(task, msg)
    return f"- {mark} {task['title']} · `{task['task_id']}` · {col}"


def _goal_context_lines(goal: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for key in ("context", "include", "exclude", "success"):
        value = goal.get(key)
        if value:
            lines.append(f"`{key}::` {value}")
    if lines:
        lines.append("")
    return lines


def _callout_lines(title: str, body_lines: List[str], *, collapsed: bool = True, kind: str = "abstract") -> List[str]:
    fold = "-" if collapsed else "+"
    lines = [f"> [!{kind}]{fold} {title}"]
    if not body_lines:
        lines.append("> _…_")
        return lines
    for line in body_lines:
        if line == "":
            lines.append(">")
        elif line.startswith("> "):
            lines.append(line)
        else:
            lines.append(f"> {line}")
    return lines


def _nested_done_callout(
    tasks: List[Dict[str, Any]],
    msg: Callable[[str], str],
    *,
    title: str,
) -> List[str]:
    if not tasks:
        return []
    inner = [f"> > [!done]- {title}"]
    for t in tasks:
        inner.append(f"> > {_task_bullet(t, msg)}")
    return inner


def render_goals_mapping_review(
    data: Dict[str, Any],
    msg: Callable[[str], str],
    priority_emojis: Dict[str, str],
) -> str:
    s = data["summary"]
    lines: List[str] = [
        "---",
        "tags:",
        "  - goals/review",
        f"updated: \"{data['generated_at']}\"",
        "---",
        "",
        f"# {msg('goals_mapping_review_title')}",
        "",
        msg("goals_mapping_review_intro").replace("{updated}", data["generated_at"]),
        "",
        f"## {msg('goals_mapping_review_summary_heading')}",
        "",
        f"| {msg('goals_mapping_review_col_metric')} | {msg('goals_mapping_review_col_value')} |",
        "|---|---|",
        f"| {msg('goals_mapping_review_stat_active_goals')} | {s['active_goals']} |",
        f"| {msg('goals_mapping_review_stat_goals_with_tasks')} | {s['goals_with_tasks']} |",
        f"| {msg('goals_mapping_review_stat_goals_without_tasks')} | {s['goals_without_tasks']} |",
        f"| {msg('goals_mapping_review_stat_mapped_tasks')} | {s['mapped_task_refs']} ({msg('goals_mapping_review_stat_open_suffix')}: {s['open_mapped_tasks']}) |",
        f"| {msg('goals_mapping_review_stat_unmapped_tasks')} | {s['unmapped_board_tasks']} ({msg('goals_mapping_review_stat_open_suffix')}: {s['open_unmapped_tasks']}) |",
        "",
        "> [!warning] " + msg("goals_mapping_review_progress_warning"),
        "",
    ]

    multi = data.get("multi_goal_tasks") or []
    if multi:
        lines.extend(["---", "", f"## {msg('goals_mapping_review_suspicious_heading')}", ""])
        lines.append("> [!danger] " + msg("goals_mapping_review_suspicious_hint"))
        lines.append("")
        for t in multi:
            lines.append(
                f"- `{t['task_id']}` → **{t['goal_count']}** "
                f"{msg('goals_mapping_review_suspicious_goals_suffix')}: {t['title']}"
            )
        lines.append("")

    orphans = data.get("orphan_goal_refs") or []
    if orphans:
        lines.extend(["---", "", f"## {msg('goals_mapping_review_orphans_heading')}", ""])
        for o in orphans:
            lines.append(f"- `{o['id']}` — {o['text']}")
        lines.append("")

    if data.get("unmapped_goals"):
        lines.extend(["---", "", f"## {msg('goals_mapping_review_unmapped_goals_heading')}", ""])
        for g in data["unmapped_goals"]:
            pe = _priority_emoji(g.get("priority"), priority_emojis)
            q = format_quarter_label(g.get("quarter") or "")
            meta_bits = [x for x in [q, g.get("category")] if x]
            meta = f" ({' · '.join(meta_bits)})" if meta_bits else ""
            lines.append(f"- {pe} {g['text']}{meta} · `{g['id']}`")
        lines.append("")

    lines.extend(["---", "", f"## {msg('goals_mapping_review_per_goal_heading')}", ""])

    for g in data.get("goals") or []:
        pe = _priority_emoji(g.get("priority"), priority_emojis)
        q = format_quarter_label(g.get("quarter") or "")
        meta_bits = [x for x in [q, g.get("category")] if x]
        meta = f" · {' · '.join(meta_bits)}" if meta_bits else ""
        title = (
            f"{pe} {g['text']}{meta} · "
            f"{msg('goals_mapping_review_goal_summary').format(open=g['open_count'], done=g['done_count'], total=len(g['tasks']))} · "
            f"`{g['id']}`"
        )
        open_tasks = [t for t in g["tasks"] if not t["completed"]]
        done_tasks = [t for t in g["tasks"] if t["completed"]]
        body: List[str] = _goal_context_lines(g)
        if open_tasks:
            body.append(f"**{msg('goals_mapping_review_section_open')} ({len(open_tasks)})**")
            body.extend(_task_bullet(t, msg) for t in open_tasks)
        elif done_tasks:
            body.append(f"_{msg('goals_mapping_review_no_open_tasks')}_")
        if done_tasks:
            body.append("")
            body.extend(
                _nested_done_callout(
                    done_tasks,
                    msg,
                    title=msg("goals_mapping_review_section_done").format(count=len(done_tasks)),
                )
            )
        lines.extend(_callout_lines(title, body, collapsed=True))
        lines.append("")

    unmapped_open = data.get("unmapped_open") or []
    unmapped_done = data.get("unmapped_done") or []
    if unmapped_open or unmapped_done:
        lines.extend(["---", "", f"## {msg('goals_mapping_review_unmapped_tasks_heading')}", ""])
        if unmapped_open:
            body = [_task_bullet(t, msg) for t in unmapped_open]
            title = msg("goals_mapping_review_unmapped_open_summary").format(count=len(unmapped_open))
            lines.extend(_callout_lines(title, body, collapsed=True, kind="info"))
            lines.append("")
        if unmapped_done:
            body: List[str] = []
            body.extend(
                _nested_done_callout(
                    unmapped_done,
                    msg,
                    title=msg("goals_mapping_review_unmapped_done_summary").format(count=len(unmapped_done)),
                )
            )
            title = msg("goals_mapping_review_unmapped_done_heading").format(count=len(unmapped_done))
            lines.extend(_callout_lines(title, body, collapsed=True, kind="done"))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def review_to_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
