"""Harness: sync-orphan heal skips task_deleted; restores recent missing creates."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from planning_bot.services import kanban_orphan_heal as heal


def _log_entry(ts: str, action: str, payload: dict) -> str:
    import json

    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        f"## {ts}\n\n"
        f"**Тип:** {action}\n\n"
        f"**Данные:**\n"
        f"```json\n{body}\n```\n\n---\n\n"
    )


def test_collect_skips_task_deleted(tmp_path: Path):
    now = datetime.now()
    t_create = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    t_del = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    t_orphan = (now - timedelta(days=1, hours=12)).strftime("%Y-%m-%d %H:%M:%S")
    log = tmp_path / "log.md"
    log.write_text(
        _log_entry(
            t_create,
            "task_created",
            {
                "title": "intentional delete me",
                "category": "опыт",
                "priority": "высокий",
                "task_id": "aaaa1111",
            },
        )
        + _log_entry(
            t_del,
            "task_deleted",
            {"title": "intentional delete me", "task_id": "aaaa1111", "source": "explicit"},
        )
        + _log_entry(
            t_orphan,
            "task_created",
            {
                "title": "sync wipe victim",
                "category": "опыт",
                "priority": "высокий",
                "task_id": "bbbb2222",
            },
        )
        + _log_entry(
            t_orphan,
            "task_removed",
            {"title": "sync wipe victim", "task_id": "bbbb2222", "source": "monitor"},
        ),
        encoding="utf-8",
    )
    since = now - timedelta(days=7)
    orphans = heal.collect_created_orphans([log], since_dt=since)
    ids = {o["task_id"] for o in orphans}
    assert "aaaa1111" not in ids
    assert "bbbb2222" in ids


def test_filter_missing_respects_board_ids():
    corpus = "- [ ] already here\n\t🆔 ID: bbbb2222\n"
    candidates = [
        {
            "task_id": "bbbb2222",
            "title": "sync wipe victim",
            "created": "2026-08-01 12:00:00",
            "category": "опыт",
            "priority": "высокий",
        },
        {
            "task_id": "cccc3333",
            "title": "needs restore",
            "created": "2026-08-01 13:00:00",
            "category": "опыт",
            "priority": "средний",
        },
    ]
    missing, stats = heal.filter_missing(candidates, corpus)
    assert stats["skip_id"] == 1
    assert len(missing) == 1
    assert missing[0][3] == "cccc3333"


def test_module_entrypoint_help():
    with pytest.raises(SystemExit) as ei:
        heal.main(["--help"])
    assert ei.value.code == 0
