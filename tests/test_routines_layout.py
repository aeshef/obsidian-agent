"""Routines vault layout migration."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def vault_env(tmp_path, monkeypatch):
    routines = tmp_path / "400_Routines"
    op = routines / "Calendar"
    op.mkdir(parents=True)
    (routines / "Routine_statistics.md").write_text("# stats\n", encoding="utf-8")
    cfg = {
        "folders": {"routines": "400_Routines"},
        "routines": {
            "operational": "Calendar",
            "signals": "Signals",
            "data": "Data",
            "charts": "Charts",
            "charts_routines": "Routines",
            "charts_signals": "Signals",
        },
        "files": {
            "routines_calendar_subdir": "Calendar/",
            "routines_config_md": "Tasks_Config.md",
            "routines_history_md": "History.md",
            "routines_today_json": "routines_today.json",
            "routines_today_legacy_md": "Today.md",
            "routines_stats_md": "Charts/Routines/stats.md",
            "routines_stats_legacy_md": "Routine_statistics.md",
            "signals_subdir": "Signals/",
            "signals_config_md": "Signals_Config.md",
            "signals_config_yaml": "Signals_Config.yaml",
            "signals_history_md": "Signals_History.md",
            "signals_stats_md": "Charts/Signals/signals_stats.md",
        },
    }
    (ROOT / "config" / "vault_paths.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("AGENT_LOCALE", "en")
    yield tmp_path
    vp = ROOT / "config" / "vault_paths.yaml"
    if vp.is_file():
        vp.unlink()


def test_migrate_routines_layout(vault_env):
    from planning_bot.services.routines_config import section_config_header
    from planning_bot.services.routines_layout import ensure_routines_layout
    from shared.routines_paths import routines_stats_path, routines_today_json_path, routines_today_legacy_path

    legacy = routines_today_legacy_path(vault_env)
    legacy.write_text(
        f"{section_config_header('evening')}\n\n- [x] Brush teeth\n\n---\n\n**Date:** 2099-01-01\n",
        encoding="utf-8",
    )
    actions = ensure_routines_layout(vault_env, scaffold_stats=False)
    assert any("migrated" in a or "moved" in a for a in actions)
    assert routines_stats_path(vault_env).is_file()
    assert not (vault_env / "400_Routines" / "Routine_statistics.md").is_file()
    assert not routines_today_legacy_path(vault_env).is_file()
    payload = json.loads(routines_today_json_path(vault_env).read_text(encoding="utf-8"))
    assert payload["date"] == "2099-01-01"
    assert payload["status"]["evening"]["Brush teeth"] is True


def test_routines_scaffold_dataviewjs_has_no_markdown_artifacts(vault_env):
    from shared.capabilities.vault_routines_scaffold import scaffold_vault_routines
    from shared.routines_paths import routines_stats_path, signals_stats_path

    written = scaffold_vault_routines(vault_root=vault_env, force=True, locale="en")

    assert written
    for path in (routines_stats_path(vault_env), signals_stats_path(vault_env)):
        text = path.read_text(encoding="utf-8")
        assert "```dataviewjs" in text
        assert "{**" not in text
        assert "if (f) {" in text
