"""Kanban sync must not treat monthly archive as lost task IDs."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib" / "sync_kanban_protect.py"
spec = importlib.util.spec_from_file_location("sync_kanban_protect", LIB)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


BOARD_HEADER = """---

kanban-plugin: board

---

"""

BOARD_FOOTER = """
%% kanban:settings
```
{"kanban-plugin":"board"}
```
%%
"""


def _card(title: str, tid: str, done: bool = True) -> str:
    mark = "x" if done else " "
    return f"- [{mark}] {title}\n\t📅 Created: 2026-07-01\n\t🆔 ID: {tid}\n"


def _board(*cards: str, column: str = "Done") -> str:
    body = "\n".join(cards)
    return f"{BOARD_HEADER}## {column}\n\n{body}\n{BOARD_FOOTER}"


def _archive(*cards: str) -> str:
    body = "\n".join(cards)
    return f"## Done · 2026-07\n\n{body}\n"


def test_looks_like_archive_uses_month_heading():
    assert mod.looks_like_archive(_archive(_card("Old", "aaa11111")))
    assert not mod.looks_like_archive(_board(_card("Old", "aaa11111")))
    assert mod.looks_like_board(_board(_card("Old", "aaa11111")))


def test_drop_task_blocks_keeps_neighbors_and_footer():
    text = _board(
        _card("Keep me", "bbbbbbbb"),
        _card("Archived", "deadbeef"),
        _card("Also keep", "cccccccc"),
    )
    out, n = mod.drop_task_blocks(text, {"deadbeef"})
    assert n == 1
    assert "deadbeef" not in out
    assert "bbbbbbbb" in out
    assert "cccccccc" in out
    assert "kanban:settings" in out
    assert "kanban-plugin: board" in out


def test_archive_only_extras_do_not_protect_same_cycle_thin_server():
    local = _board(_card("Old", "deadbeef"), _card("New local", "cafe0001", done=False))
    # After archive the server board only has the new-month / remaining work.
    # Simulate: server already thinned old card; local still fat + a create.
    # Wait — mixed case is separate. Pure same-cycle: local fat, server thin, no new ids.
    local_fat = _board(_card("Old", "deadbeef"), _card("Old2", "aaa11111"))
    server_thin = _board(_card("This month", "bbbbbbbb"))
    archive = _archive(_card("Old", "deadbeef"), _card("Old2", "aaa11111"))
    plan = mod.plan_board_protect(local_fat, server_thin, archive)
    assert plan.dropped == 2
    assert "deadbeef" not in plan.new_local_text
    assert not plan.genuine_local
    assert plan.protect is False
    assert plan.skip_force_push is False


def test_genuine_local_create_still_protects_after_stripping_archive():
    local = _board(
        _card("Archived", "deadbeef"),
        _card("Created during sync", "cafe0001", done=False),
    )
    server = _board(_card("This month", "bbbbbbbb"))
    archive = _archive(_card("Archived", "deadbeef"))
    plan = mod.plan_board_protect(local, server, archive)
    assert plan.dropped == 1
    assert "deadbeef" not in plan.new_local_text
    assert "cafe0001" in plan.new_local_text
    assert plan.genuine_local == {"cafe0001"}
    assert plan.protect is True
    assert plan.skip_force_push is False


def test_cleaned_local_can_overwrite_fat_server_board():
    """Resurrection: archive ran, then Mac pushed the fat board back."""
    fat = _board(_card("Old", "deadbeef"), _card("Keep August", "bbbbbbbb"))
    archive = _archive(_card("Old", "deadbeef"))
    plan = mod.plan_board_protect(fat, fat, archive)
    assert plan.dropped == 1
    assert "deadbeef" not in plan.new_local_text
    assert "bbbbbbbb" in plan.new_local_text
    assert plan.protect is True
    assert plan.skip_force_push is False
    assert "deadbeef" not in plan.missing_real


def test_stale_mac_still_blocked_when_server_has_many_real_ids():
    local = _board(_card("Only local leftover", "aaaaaaa1"))
    server_cards = [_card(f"Srv {i}", f"{i:08x}") for i in range(8)]
    server = _board(*server_cards)
    archive = _archive(_card("Unrelated", "deadbeef"))
    plan = mod.plan_board_protect(local, server, archive)
    assert plan.skip_force_push is True
    assert len(plan.missing_real) == 8


def test_small_intentional_delete_still_allowed():
    local = _board(_card("Keep", "bbbbbbbb"))
    server = _board(_card("Keep", "bbbbbbbb"), _card("Deleted on Mac", "cafe0001"))
    archive = _archive(_card("Unrelated", "deadbeef"))
    plan = mod.plan_board_protect(local, server, archive)
    assert plan.skip_force_push is False
    assert plan.missing_real == {"cafe0001"}


def test_strip_dir_only_touches_board(tmp_path: Path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    board = tasks / "Board.md"
    archive = tasks / "Closed.md"
    board.write_text(
        _board(_card("Dup", "deadbeef"), _card("Stay", "bbbbbbbb")),
        encoding="utf-8",
    )
    archive.write_text(_archive(_card("Dup", "deadbeef")), encoding="utf-8")
    rc = mod.cmd_strip_dir(
        type("A", (), {"tasks_root": str(tasks), "archive_rel": "", "dry_run": False})()
    )
    assert rc == 0
    text = board.read_text(encoding="utf-8")
    assert "deadbeef" not in text
    assert "bbbbbbbb" in text
    assert "deadbeef" in archive.read_text(encoding="utf-8")


def test_discover_archive_rel(tmp_path: Path):
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    (tasks / "Board.md").write_text(_board(_card("Open", "bbbbbbbb")), encoding="utf-8")
    (tasks / "Closed.md").write_text(_archive(_card("Old", "deadbeef")), encoding="utf-8")
    assert mod.discover_archive_rel(tasks) == "Closed.md"
