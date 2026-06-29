from __future__ import annotations

import json
from pathlib import Path

from shared.goals.mapping_files import (
    promote_mapping_file,
    staging_mapping_file,
    write_json_atomic,
)


def test_staging_mapping_file_under_vault_sync(tmp_path: Path):
    assert staging_mapping_file(tmp_path) == tmp_path / ".sync" / "goals_task_mapping.staging.json"


def test_promote_mapping_replaces_production(tmp_path: Path):
    staging = tmp_path / ".sync" / "goals_task_mapping.staging.json"
    production = tmp_path / "300_Дашборды" / "goals_task_mapping.json"
    write_json_atomic(staging, {"task_to_goals": {"a": ["g1"]}, "task_titles": {}, "readable_mapping": {}})
    production.parent.mkdir(parents=True, exist_ok=True)
    production.write_text('{"old": true}', encoding="utf-8")

    promote_mapping_file(staging, production)

    data = json.loads(production.read_text(encoding="utf-8"))
    assert data["task_to_goals"] == {"a": ["g1"]}
    assert not production.with_suffix(production.suffix + ".tmp").exists()


def test_write_json_atomic_leaves_no_tmp(tmp_path: Path):
    target = tmp_path / "out.json"
    write_json_atomic(target, {"ok": 1})
    assert target.read_text(encoding="utf-8").startswith("{")
    assert not target.with_name(target.name + ".tmp").exists()
