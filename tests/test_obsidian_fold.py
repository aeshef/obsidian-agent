"""Tests for foldable Obsidian sections (details vs callout)."""
from shared.obsidian_fold import fold_section


def test_fold_text_uses_callout():
    lines = fold_section("List", ["- a", "- b"])
    assert lines[0].startswith("> [!note]- List")
    assert "> - a" in lines


def test_fold_table_uses_details():
    lines = fold_section(
        "Big spends",
        ["![[chart.png]]", "", "| A | B |", "|---|---|", "| 1 | 2 |"],
    )
    text = "\n".join(lines)
    assert "<details>" in text
    assert "<summary>Big spends</summary>" in text
    assert "![[chart.png]]" in text
    assert "| A | B |" in text
    assert "> [!note]" not in text


def test_fold_force_details():
    lines = fold_section("X", ["just text"], force_details=True)
    assert lines[0] == "<details>"
