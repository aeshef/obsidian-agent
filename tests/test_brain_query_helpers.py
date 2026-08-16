from __future__ import annotations

from knowledge_bot.services.query.brain_query import (
    _build_compact_catalog,
    _parse_preselect,
)

from tests.conftest import knowledge_rel


def test_parse_preselect_object_candidates():
    full = knowledge_rel("_Хабы/hub.md")
    short_to_full = {"_Хабы/hub.md": full}
    raw = {"candidates": [{"path": "_Хабы/hub.md"}]}
    assert _parse_preselect(raw, short_to_full) == [full]


def test_compact_catalog_includes_snippet():
    entries = [
        {
            "rel_path": knowledge_rel("Знания/Норма_белка.md"),
            "title": "Норма белка",
            "tags": ["topic/fitness"],
            "summary": "",
            "preview": "уезжаю в качалку на весь день",
        },
    ]
    text, short_map = _build_compact_catalog(entries)
    assert "качалку" in text
    assert short_map


def test_compact_catalog_keeps_extra_roots_under_char_cap(monkeypatch):
    """Handwritten/extra roots must not be starved when primary KB fills the cap."""
    from knowledge_bot.services.query import brain_query as bq

    monkeypatch.setattr(bq, "_compact_catalog_max_chars", lambda: 400)
    monkeypatch.setattr(bq, "_catalog_snippet_chars", lambda: 20)
    monkeypatch.setattr(bq, "_base_prefix", lambda: "700_База_Данных/")
    monkeypatch.setattr(
        "shared.vault_layout.knowledge_subdir", lambda: "700_База_Данных"
    )
    monkeypatch.setattr(
        "shared.vault_layout.knowledge_index_roots",
        lambda: ["700_База_Данных", "600_Рукописное"],
    )

    entries = [
        {
            "rel_path": f"700_База_Данных/n{i}.md",
            "title": f"Note {i}",
            "tags": [],
            "summary": "",
            "preview": "x" * 80,
        }
        for i in range(50)
    ] + [
        {
            "rel_path": "600_Рукописное/Шляпа.md",
            "title": "Шляпа",
            "tags": ["шляпа"],
            "summary": "",
            "preview": "сайд-квесты из шляпы",
        }
    ]
    text, short_map = bq._build_compact_catalog(entries)
    assert "Шляпа" in text
    assert short_map.get("600_Рукописное/Шляпа.md") == "600_Рукописное/Шляпа.md"
