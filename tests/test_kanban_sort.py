"""Integration: kanban sort on fixture vault copy."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from planning_bot.core.config import PRIORITY_ORDER
from tests.conftest import FIXTURE_VAULT
from tests.kanban_test_data import kanban_board_fixture_path, kanban_strings


def _count_tasks(content: str) -> int:
    return len(re.findall(r"^- \[[ x]\]", content, re.MULTILINE))


def _extract_priority(task_text: str) -> str:
    tag = kanban_strings("tag_priority")
    for name in PRIORITY_ORDER:
        if f"#{tag}/{name}" in task_text:
            return name
    return ""


def _extract_deadline_ordinal(task_text: str) -> int | None:
    tag = kanban_strings("tag_deadline")
    m = re.search(rf"#{tag}/(\d{{4}}-\d{{2}}-\d{{2}})", task_text)
    if not m:
        return None
    from datetime import datetime

    return datetime.strptime(m.group(1), "%Y-%m-%d").toordinal()


def _parse_tasks_by_section(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    headers = list(re.finditer(r"^## (.+?)$", content, re.MULTILINE))
    for i, m in enumerate(headers):
        name = m.group(1).strip()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        block = content[start:end]
        if "%% kanban" in block:
            block = block.split("%% kanban")[0]
        tasks = re.findall(r"^- \[[ x]\].+(?:\n(?:\t|    ).+)*", block, re.MULTILINE)
        sections[name] = [t.strip() for t in tasks if t.strip()]
    return sections


def _sort_key(task_text: str) -> tuple:
    deadline = _extract_deadline_ordinal(task_text)
    prio = PRIORITY_ORDER.get(_extract_priority(task_text), 99)
    if deadline is not None:
        return (0, deadline, prio, task_text.lower())
    return (1, 9999999, prio, task_text.lower())


def _is_sorted(tasks: list[str]) -> bool:
    keys = [_sort_key(t) for t in tasks]
    return keys == sorted(keys)


def test_sort_kanban_on_fixture_copy(tmp_path: Path):
    kanban_src = kanban_board_fixture_path(FIXTURE_VAULT)
    assert kanban_src.is_file(), f"fixture missing: {kanban_src}"
    copy_path = tmp_path / "kanban.md"
    shutil.copy2(kanban_src, copy_path)

    with open(kanban_src, encoding="utf-8") as f:
        orig = f.read()
    n_orig = _count_tasks(orig)

    from planning_bot.tools.vault_maintenance import sort_kanban_tasks

    assert sort_kanban_tasks(target_path=copy_path) is True

    new_content = copy_path.read_text(encoding="utf-8")
    assert _count_tasks(new_content) == n_orig

    for name, tasks in _parse_tasks_by_section(new_content).items():
        if len(tasks) > 1:
            assert _is_sorted(tasks), f"section {name!r} not sorted: {tasks}"
