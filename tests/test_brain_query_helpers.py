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
