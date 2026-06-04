"""vault_paths.yaml must override locale examples when present."""
from __future__ import annotations

from pathlib import Path

from shared import vault_paths_config as vp


def test_local_vault_paths_yaml_overrides_en_default(monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "en")
    vp.vault_paths_config.cache_clear()
    local = Path(__file__).resolve().parents[1] / "config" / "vault_paths.yaml"
    if not local.is_file():
        return
    assert vp.folder("tasks") == "100_Задачи"
    vp.vault_paths_config.cache_clear()
