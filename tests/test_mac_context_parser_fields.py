"""Mac context parser: extended shortcut fields."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from planning_bot.services.context_parser import parse_context_file


def test_parse_window_title_and_idle_sec(tmp_path: Path):
    path = tmp_path / "2026-06-30, 14-05.txt"
    path.write_text(
        """---
ts: 30.06.2026, 14:05
source: aeshef-osx
app: Cursor
window_title: obsidian-agent — context_parser.py
idle_sec: 42
focus: Work
---
""",
        encoding="utf-8",
    )
    snaps = parse_context_file(path)
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap["app"] == "Cursor"
    assert snap["window_title"] == "obsidian-agent — context_parser.py"
    assert snap["idle_sec"] == 42
    assert snap["active"] is True


def test_focus_window_alias_for_window_title(tmp_path: Path):
    path = tmp_path / "2026-06-30, 14-10.txt"
    path.write_text(
        """---
ts: 30.06.2026, 14:10
source: aeshef-osx
app: Obsidian
focus_window: 🎯 2026_Цели
idle_sec: 400
---
""",
        encoding="utf-8",
    )
    snap = parse_context_file(path)[0]
    assert snap["window_title"] == "🎯 2026_Цели"
    assert snap["active"] is False


def test_colon_filename_needs_rename():
    from planning_bot.services.iphone_snapshot_names import (
        needs_rename_filename,
        parse_filename_ts,
    )

    name = "2026-06-30, 14:55.txt"
    assert needs_rename_filename(name)
    ts = parse_filename_ts(name)
    assert ts is not None
    assert ts.hour == 14 and ts.minute == 55
