from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from planning_bot.services.context_parser import load_chat_snapshot_from_json


def test_load_chat_snapshot_never_uses_stale_recent(tmp_path: Path):
    path = tmp_path / "context_today.json"
    path.write_text(
        json.dumps(
            {
                "today": [],
                "recent": [{"ts": "2026-06-12T18:00", "app": "Safari", "focus": "Work"}],
            }
        ),
        encoding="utf-8",
    )
    assert load_chat_snapshot_from_json(path, as_of=date(2026, 6, 14)) is None


def test_load_chat_snapshot_prefers_anchor_day(tmp_path: Path):
    path = tmp_path / "context_today.json"
    path.write_text(
        json.dumps(
            {
                "today": [
                    {"ts": "2026-06-13T23:50", "app": "Obsidian"},
                    {"ts": "2026-06-14T09:00", "app": "Cursor"},
                ]
            }
        ),
        encoding="utf-8",
    )
    snap = load_chat_snapshot_from_json(path, as_of=date(2026, 6, 14))
    assert snap is not None
    assert snap["ts"] == "2026-06-14T09:00"


def test_load_chat_snapshot_yesterday_only_when_anchor_empty(tmp_path: Path):
    path = tmp_path / "context_today.json"
    path.write_text(
        json.dumps(
            {
                "today": [{"ts": "2026-06-13T23:50", "app": "Obsidian"}],
            }
        ),
        encoding="utf-8",
    )
    snap = load_chat_snapshot_from_json(path, as_of=date(2026, 6, 14))
    assert snap is not None
    assert snap["ts"].startswith("2026-06-13")
