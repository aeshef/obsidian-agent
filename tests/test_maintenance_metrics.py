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


def test_extract_deleted_paths_apply_duplicates(monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    stdout = (
        "  [foo] keep_base\n"
        "    удалён: 700_База_Данных/Мысли/a_1.md\n"
        "--- Сиротские Export (ссылались только с удалённых заметок) ---\n"
        "  удалён: 700_База_Данных/Export/x.png\n"
    )
    from knowledge_bot.services.maintenance_metrics import (
        collect_deletions_from_steps,
        extract_deleted_paths_from_stdout,
        write_deletion_manifest,
    )

    paths = extract_deleted_paths_from_stdout("apply_duplicates", stdout)
    assert len(paths) == 2
    assert paths[0]["reason"] == "duplicate"
    assert paths[0]["path"].endswith("a_1.md")
    assert paths[1]["reason"] == "export_orphan"

    steps = [{"metrics": {"deleted_paths": paths}}]
    assert len(collect_deletions_from_steps(steps)) == 2


def test_render_maintenance_chart_path(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    from functools import lru_cache

    from shared import vault_paths_config as vpc

    vpc.vault_paths_config.cache_clear()

    @lru_cache(maxsize=1)
    def _cfg() -> dict:
        return {
            "folders": {"dashboards": "300_Дашборды"},
            "dashboards": {"charts": "Графики", "data": "Данные"},
            "files": {
                "chart_maintenance_dynamics_png": "Хранилище/Динамика_обслуживания.png",
            },
        }

    monkeypatch.setattr(vpc, "vault_paths_config", _cfg)

    vault = tmp_path / "vault"
    data = vault / "300_Дашборды" / "Данные"
    data.mkdir(parents=True)
    (data / "vault_maintenance_history.yaml").write_text(
        "- date: '2026-06-01'\n  before: {notes_md_db700: 1, bytes_export: 0, reprocess_eligible: 0}\n"
        "  after: {notes_md_db700: 1, bytes_export: 0, reprocess_eligible: 0}\n"
        "  run: {}\n  ok: true\n",
        encoding="utf-8",
    )
    from knowledge_bot.services.maintenance_metrics import render_maintenance_charts

    paths = render_maintenance_charts(vault)
    assert len(paths) == 1
    assert paths[0].name == "Динамика_обслуживания.png"
    assert paths[0].parent.name == "Хранилище"
    legacy = vault / "300_Дашборды" / "Графики" / "vault_maintenance_dynamics.png"
    assert not legacy.is_file()


def test_write_deletion_manifest(tmp_path: Path):
    sync_dir = tmp_path / ".sync"
    deletions = [{"path": "700_База_Данных/Мысли/a_1.md", "reason": "duplicate"}]
    from knowledge_bot.services.maintenance_metrics import write_deletion_manifest

    write_deletion_manifest(sync_dir, deletions, "2026-06-15T00:07:00")
    raw = __import__("json").loads((sync_dir / "last_maintenance_deleted_paths.json").read_text())
    assert raw["deleted"] == deletions
    assert raw["summary"]["duplicate"] == 1


def test_extract_export_orphans_metrics_and_deletions(monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    stdout = (
        "EXPORT_ORPHANS_SUMMARY: total=12 bytes=3456 referenced=120 export_total=300\n"
        "EXPORT_BROKEN_REFS: count=4\n"
        "EXPORT_BROKEN_BODY_REFS_CLEANED_NOTES: count=1\n"
        "EXPORT_REHYDRATED_TOTAL: count=2\n"
        "  удалён: 700_База_Данных/Export/2026/03/a.mp4\n"
        "EXPORT_ORPHANS_DELETED_TOTAL: count=1 bytes=1024\n"
    )
    m = extract_step_metrics("export_orphans", stdout)
    assert m["export_orphans_found"] == 12
    assert m["export_broken_refs"] == 4
    assert m["export_broken_body_refs_cleaned_notes"] == 1
    assert m["export_rehydrated"] == 2
    assert m["export_orphans_deleted"] == 1
    assert m["export_orphans_deleted_bytes"] == 1024
    paths = m.get("deleted_paths") or []
    assert len(paths) == 1
    assert paths[0]["reason"] == "export_orphan"


def test_export_ref_normalization_handles_anchor_and_leading_slash():
    from knowledge_bot.services.export_refs import normalize_export_ref

    assert (
        normalize_export_ref("/700_База_Данных/Export/2026/03/file.png#preview")
        == "2026/03/file.png"
    )


def test_cleanup_broken_body_refs_preserves_existing_and_alias(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    from shared.vault_layout import knowledge_subdir

    db = tmp_path / knowledge_subdir()
    export = db / "Export" / "2026" / "03"
    export.mkdir(parents=True)
    (export / "ok.png").write_bytes(b"ok")
    note = db / "Мысли" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\ntitle: t\n---\n"
        "keep ![[700_База_Данных/Export/2026/03/ok.png#v]]\n"
        "drop ![[700_База_Данных/Export/2026/03/missing.png]]\n"
        "alias [[Export/2026/03/missing.pdf|видимый текст]]\n",
        encoding="utf-8",
    )
    from knowledge_bot.tools.export_orphans_maintenance import _cleanup_broken_body_refs

    assert _cleanup_broken_body_refs(tmp_path) == 1
    text = note.read_text(encoding="utf-8")
    assert "![[700_База_Данных/Export/2026/03/ok.png#v]]" in text
    assert "missing.png" not in text
    assert "[[Export/2026/03/missing.pdf|видимый текст]]" not in text
    assert "видимый текст" in text
