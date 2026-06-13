"""Untagged note detection for vault audit and maintenance."""
from __future__ import annotations

from pathlib import Path

import yaml

from knowledge_bot.services.untagged_notes import find_untagged_note_paths


def _write_note(vault: Path, rel: str, tags: list[str]) -> None:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "## Body\n"
    fm = {"type": "knowledge", "title": "Test", "tags": tags}
    text = "---\n" + yaml.dump(fm, allow_unicode=True, default_flow_style=False) + "---\n" + body
    path.write_text(text, encoding="utf-8")


def test_find_untagged_skips_tagged_and_hubs(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    vault = tmp_path / "vault"
    vault.mkdir()
    kb = vault / "700_База_Данных"
    kb.mkdir()
    _write_note(vault, "700_База_Данных/tagged.md", ["domain/life"])
    _write_note(vault, "700_База_Данных/empty_tags.md", [])
    _write_note(vault, "700_База_Данных/no_tags_field.md", [])
    (kb / "no_tags_field.md").write_text(
        "---\n"
        + yaml.dump({"type": "knowledge", "title": "X"}, allow_unicode=True)
        + "---\nbody\n",
        encoding="utf-8",
    )
    (kb / "🗺️ Hub.md").write_text("---\ntags: []\n---\n", encoding="utf-8")

    found = find_untagged_note_paths(vault)
    names = {p.name for p in found}
    assert "tagged.md" not in names
    assert "🗺️ Hub.md" not in names
    assert "empty_tags.md" in names
    assert "no_tags_field.md" in names


def test_extract_retag_untagged_metrics(monkeypatch):
    monkeypatch.setenv("AGENT_LOCALE", "ru")
    from knowledge_bot.services.maintenance_metrics import extract_step_metrics

    stdout = "Итого: затронуто=3, пропущено=1, llm_fallback=0"
    m = extract_step_metrics("retag_untagged", stdout)
    assert m["retag_touched"] == 3
    assert m["retag_skipped"] == 1
