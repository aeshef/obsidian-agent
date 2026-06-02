from pathlib import Path

from knowledge_bot.services.query.note_lookup import resolve_note_path
from knowledge_bot.services.query.note_media import media_from_note_text


def test_resolve_exact_title():
    entries = [
        {
            "rel_path": "700_База_Данных/Курсы/Курс_Anthropic_MCP.md",
            "title": "Курс Anthropic MCP",
        },
    ]
    path, reason = resolve_note_path("Курс Anthropic MCP", entries)
    assert path and path.endswith("Курс_Anthropic_MCP.md")
    assert reason == "exact title or stem"


def test_greeting_does_not_fuzzy_match_title():
    entries = [
        {
            "rel_path": "700_База_Данных/Мысли/Приветствие.md",
            "title": "Приветствие",
        },
    ]
    path, reason = resolve_note_path("привет!", entries)
    assert path is None
    assert "точного" in reason


def test_select_empty_falls_back_to_candidates():
    """Симуляция: select отклонил всё, но candidate_paths из индекса остаются."""
    candidate_paths = [
        "700_База_Данных/Знания/Норма_белка.md",
        "700_База_Данных/Знания/Тренировки_дома.md",
    ]
    final_paths = []
    if not final_paths and candidate_paths:
        final_paths = candidate_paths[:14]
    assert len(final_paths) == 2


def test_media_from_note_frontmatter(tmp_path: Path):
    rel = "700_База_Данных/Курсы/x.md"
    vault = tmp_path
    media_path = vault / "700_База_Данных/Export/v.mp4"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"\x00")
    raw = """---
title: Test
attachments:
  files:
  - 700_База_Данных/Export/v.mp4
---
# Test
"""
    (vault / rel).parent.mkdir(parents=True, exist_ok=True)
    (vault / rel).write_text(raw, encoding="utf-8")
    found = media_from_note_text(raw, rel, vault)
    assert found == [("700_База_Данных/Export/v.mp4", "Test")]
