"""Shell scripts.* messages resolve via shared/i18n."""
from __future__ import annotations

from pathlib import Path

from shared.i18n import clear_messages_cache, msg
from shared.yaml_config import load_yaml


def test_messages_example_has_scripts_section():
    raw = load_yaml(
        Path(__file__).resolve().parent.parent / "config/messages.en.yaml.example",
        default={},
    )
    assert "scripts" in raw
    assert raw["scripts"]["obsidian_sync"]["done"] == "obsidian_sync: done."


def test_sh_msg_resolves_en_default(monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "en")
    clear_messages_cache()
    assert msg("scripts", "deploy", "shared_no_restart") == "shared does not require restart"
