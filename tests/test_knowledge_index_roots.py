"""Multi-root knowledge note index (knowledge_subdir + extra folder keys)."""
from __future__ import annotations

from pathlib import Path


def test_knowledge_index_roots_includes_extra_folder(monkeypatch):
    import shared.vault_layout as vl

    monkeypatch.setattr(vl, "knowledge_subdir", lambda: "Knowledge")
    monkeypatch.setattr(
        "shared.agent.platform_config.platform_value",
        lambda section, key, env=None, default=None: (
            ["handwritten"] if key == "knowledge_index_extra_folders" else default
        ),
    )
    monkeypatch.setattr(
        "shared.vault_paths_config.folder",
        lambda key: {"handwritten": "Handwritten"}[key],
    )

    assert vl.knowledge_index_roots() == ["Knowledge", "Handwritten"]


def test_knowledge_index_roots_skips_bad_folder_key(monkeypatch):
    import shared.vault_layout as vl

    monkeypatch.setattr(vl, "knowledge_subdir", lambda: "Knowledge")
    monkeypatch.setattr(
        "shared.agent.platform_config.platform_value",
        lambda section, key, env=None, default=None: (
            ["nope", "handwritten"] if key == "knowledge_index_extra_folders" else default
        ),
    )

    def _folder(key: str) -> str:
        if key == "handwritten":
            return "Handwritten"
        raise KeyError(key)

    monkeypatch.setattr("shared.vault_paths_config.folder", _folder)
    assert vl.knowledge_index_roots() == ["Knowledge", "Handwritten"]


def test_build_index_scans_multiple_roots(tmp_path: Path, monkeypatch):
    from knowledge_bot.services.query.index_builder import build_index

    kb = tmp_path / "Knowledge"
    hand = tmp_path / "Handwritten"
    kb.mkdir()
    hand.mkdir()
    (kb / "a.md").write_text("---\ntitle: Alpha\n---\nkb body\n", encoding="utf-8")
    (hand / "b.md").write_text("---\ntitle: Bravo\n---\nhand body\n", encoding="utf-8")

    monkeypatch.setattr(
        "shared.vault_layout.knowledge_index_roots",
        lambda: ["Knowledge", "Handwritten"],
    )

    data = build_index(tmp_path)
    paths = {e["rel_path"] for e in data["entries"]}
    titles = {e["title"] for e in data["entries"]}
    assert paths == {"Knowledge/a.md", "Handwritten/b.md"}
    assert titles == {"Alpha", "Bravo"}
    assert data["index_roots"] == ["Knowledge", "Handwritten"]
    assert data["count"] == 2


def test_index_needs_refresh_when_roots_change(tmp_path: Path, monkeypatch):
    import json

    from knowledge_bot.services.query import index_builder as ib

    idx = tmp_path / "notes_index.json"
    idx.write_text(
        json.dumps(
            {
                "vault": str(tmp_path.resolve()),
                "index_roots": ["Knowledge"],
                "count": 0,
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ib, "index_json_path", lambda: idx)
    monkeypatch.setattr(ib, "index_max_age", lambda: 999999)
    monkeypatch.setattr(
        "shared.vault_layout.knowledge_index_roots",
        lambda: ["Knowledge", "Handwritten"],
    )

    assert ib.index_needs_refresh(tmp_path) is True
