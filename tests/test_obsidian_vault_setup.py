from __future__ import annotations

from pathlib import Path

from shared.capabilities.obsidian_vault_setup import install_obsidian_assets
from shared.capabilities.profile import MODULE_KNOWLEDGE, MODULE_PLANNING, CapabilityProfile


def _patch_vault_paths(monkeypatch, doc: dict) -> None:
    from functools import lru_cache

    from shared import vault_paths_config as vpc

    vpc.vault_paths_config.cache_clear()

    @lru_cache(maxsize=1)
    def _cfg() -> dict:
        return doc

    monkeypatch.setattr(vpc, "vault_paths_config", _cfg)


def test_install_obsidian_assets_copies_clones_and_add_task(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault))
    monkeypatch.setenv("AGENT_LOCALE", "en")
    _patch_vault_paths(
        monkeypatch,
        {
            "folders": {
                "tasks": "100_Tasks",
                "automation": "800_Automation",
            },
            "paths": {
                "templates_root": "Templates",
                "templates_v2": "Templates/v2",
                "templates_entities": "Templates/Entities",
                "templates_clones": "Templates/Clones",
            },
            "files": {
                "kanban_board": "Task_Board.md",
                "templater_add_task_md": "Add_Task.md",
            },
        },
    )
    monkeypatch.setattr(
        "shared.capabilities.obsidian_vault_setup._kanban_schema",
        lambda: {
            "columns": ["Backlog"],
            "categories": ["career"],
            "priorities": ["high"],
            "category_emojis": {"career": "💼"},
            "priority_emojis": {"high": "🔥"},
            "tag_prefixes": {"deadline": "deadline"},
            "task_meta_template": "\t#goal/{category} #priority/{priority}",
            "task_created_template": "\tCreated: {created_date}",
        },
    )
    prof = CapabilityProfile(
        modules={MODULE_PLANNING: True, MODULE_KNOWLEDGE: True},
        connectors={},
        sync_profile="full",
    )
    written = install_obsidian_assets(prof, vault, locale="en", force=True)
    assert written
    clones = vault / "800_Automation" / "Templates" / "Clones"
    assert clones.is_dir()
    assert any(clones.glob("*.j2.md"))
    add_task = vault / "800_Automation" / "Templates" / "v2" / "Add_Task.md"
    assert add_task.is_file()
    text = add_task.read_text(encoding="utf-8")
    assert "100_Tasks/Task_Board.md" in text
    assert "#goal/" in text or "goal" in text
    assert "const taskMeta = `\"" not in text
    assert 'const taskMeta = "' in text
