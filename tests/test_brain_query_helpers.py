from __future__ import annotations

from knowledge_bot.services.query.brain_query import (
    _build_compact_catalog,
    _parse_preselect,
)


def test_parse_preselect_object_candidates():
    short_to_full = {"_Хабы/hub.md": "700_База_Данных/_Хабы/hub.md"}
    raw = {"candidates": [{"path": "_Хабы/hub.md"}]}
    assert _parse_preselect(raw, short_to_full) == ["700_База_Данных/_Хабы/hub.md"]


def test_compact_catalog_includes_snippet():
    entries = [
        {
            "rel_path": "700_База_Данных/Знания/Норма_белка.md",
            "title": "Норма белка",
            "tags": ["topic/fitness"],
            "summary": "",
            "preview": "уезжаю в качалку на весь день",
        },
    ]
    text, short_map = _build_compact_catalog(entries)
    assert "качалку" in text
    assert short_map
