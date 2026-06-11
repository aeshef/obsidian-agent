"""Maintenance metrics: dup dry-run parsing and daily ok merge."""
from __future__ import annotations

from pathlib import Path

from knowledge_bot.services.maintenance_metrics import (
    append_daily_record,
    extract_step_metrics,
    load_history,
)


def test_extract_dup_dryrun_counts_ru_delete_lines(monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    stdout = (
        "=== DRY-RUN ===\n"
        "  [foo] keep_base\n"
        "    удалить: 700_База_Данных/Мысли/a_1.md\n"
        "    удалить: 700_База_Данных/Мысли/b_1.md\n"
    )
    m = extract_step_metrics("apply_duplicates_dryrun", stdout)
    assert m["duplicates_deleted_lines"] == 2


def test_append_daily_record_latest_ok_wins(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "300_Дашборды").mkdir(parents=True)
    (vault / "300_Дашборды" / "Данные").mkdir()
    snap = {
        "notes_md_db700": 10,
        "notes_md_excl_export": 9,
        "bytes_db700": 100,
        "bytes_export": 50,
        "reprocess_total": 0,
        "reprocess_eligible": 0,
    }
    steps: list[dict] = []
    append_daily_record(
        vault,
        before=snap,
        after=snap,
        steps=steps,
        ok=False,
        ts_start="2026-06-11T00:04:00",
        ts_end="2026-06-11T00:04:30",
    )
    append_daily_record(
        vault,
        before=snap,
        after=snap,
        steps=steps,
        ok=True,
        ts_start="2026-06-11T11:03:00",
        ts_end="2026-06-11T11:03:53",
    )
    rows = load_history(vault, max_rows=5)
    today = next(r for r in rows if r.get("date") == "2026-06-11")
    assert today["runs_count"] == 2
    assert today["ok"] is True
