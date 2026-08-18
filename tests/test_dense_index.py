from __future__ import annotations

import numpy as np

from knowledge_bot.services.query.dense_index import (
    clean_preview,
    clear_dense_cache,
    passage_text,
    search_notes,
    sync_from_index,
)
from knowledge_bot.services.query import dense_index as di


def test_clean_preview_drops_noise():
    out = clean_preview(
        "субтитры\nreal thesis about running\nРедактор субтитров",
        noise={"субтитры", "редактор субтитров"},
        max_chars=4000,
    )
    assert "running" in out
    assert "субтитры" not in out.casefold()


def test_passage_includes_title_tags_city():
    text = passage_text(
        {
            "title": "Xiaomi",
            "type": "вишлист",
            "tags": ["category/gadgets"],
            "city": "Moscow",
            "summary": "",
            "preview": "dumbbells",
        },
        max_chars=400,
    )
    assert "Xiaomi" in text
    assert "category/gadgets" in text
    assert "Moscow" in text


def test_sync_embeds_only_changed_notes(tmp_path, monkeypatch):
    clear_dense_cache()
    monkeypatch.setattr(di, "cache_path", lambda: tmp_path / "dense_index.npz")
    monkeypatch.setattr(di, "_sync_max_notes", lambda: 100)
    calls: list[list[str]] = []

    def fake_embed(texts: list[str]):
        calls.append(list(texts))
        n = len(texts)
        mat = np.zeros((n, 4), dtype=np.float32)
        for i in range(n):
            mat[i, i % 4] = 1.0
        return di._l2_normalize(mat)

    monkeypatch.setattr(di, "embed_texts", fake_embed)

    entries = [
        {"rel_path": "a.md", "title": "A", "type": "note", "tags": [], "preview": "alpha"},
        {"rel_path": "b.md", "title": "B", "type": "note", "tags": [], "preview": "beta"},
    ]
    idx = sync_from_index({"entries": entries}, blocking=True)
    assert idx is not None and idx.available
    assert len(calls) == 1 and len(calls[0]) == 2

    idx2 = sync_from_index({"entries": entries}, blocking=True)
    assert idx2 is not None
    assert len(calls) == 1

    entries[1] = {
        "rel_path": "b.md",
        "title": "B",
        "type": "note",
        "tags": [],
        "preview": "beta changed",
    }
    idx3 = sync_from_index({"entries": entries}, blocking=True)
    assert idx3 is not None
    assert len(calls) == 2
    assert len(calls[1]) == 1
    assert "beta changed" in calls[1][0]
    clear_dense_cache()


def test_gold_skips_needs_label(tmp_path):
    from eval.retrieval.gold import load_gold

    p = tmp_path / "g.yaml"
    p.write_text(
        "queries:\n"
        "  - id: a\n    bucket: how-to\n    status: seed\n    query: foo\n"
        "    relevant_paths: [x.md]\n"
        "  - id: b\n    bucket: overview\n    status: needs_label\n    query: bar\n"
        "    relevant_paths: [y.md]\n",
        encoding="utf-8",
    )
    rows = load_gold(p)
    assert [r["id"] for r in rows] == ["a"]


def test_search_ranks_similar_passage_first(tmp_path, monkeypatch):
    clear_dense_cache()
    monkeypatch.setattr(di, "cache_path", lambda: tmp_path / "dense_index.npz")
    monkeypatch.setattr(di, "_sync_max_notes", lambda: 100)
    monkeypatch.setattr(di, "_query_cache_size", lambda: 0)

    def fake_embed(texts: list[str]):
        mat = np.zeros((len(texts), 2), dtype=np.float32)
        for i, t in enumerate(texts):
            low = t.casefold()
            if "detox" in low or "liver" in low:
                mat[i, 0] = 1.0
            else:
                mat[i, 1] = 1.0
        return di._l2_normalize(mat)

    monkeypatch.setattr(di, "embed_texts", fake_embed)
    entries = [
        {
            "rel_path": "noise.md",
            "title": "Tennis",
            "type": "place",
            "tags": [],
            "preview": "courts and rackets",
        },
        {
            "rel_path": "hit.md",
            "title": "Liver cleanse",
            "type": "note",
            "tags": [],
            "preview": "detox protocol",
        },
    ]
    hits = search_notes("liver detox", entries, top_n=2)
    assert hits[0] == "hit.md"
    clear_dense_cache()
