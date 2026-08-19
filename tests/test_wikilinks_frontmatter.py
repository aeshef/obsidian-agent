from knowledge_bot.services.wikilinks import _apply_wikilinks, split_frontmatter


def test_split_frontmatter_keeps_yaml_block():
    text = "---\ntags:\n- domain/life\n---\n# Title\n\nlife goes on\n"
    prefix, body = split_frontmatter(text)
    assert prefix.startswith("---")
    assert "domain/life" in prefix
    assert body.startswith("# Title")


def test_apply_wikilinks_does_not_rewrite_frontmatter_tags():
    content = (
        "---\n"
        'tags:\n'
        '- "domain/life"\n'
        '- "topic/music"\n'
        "---\n"
        "# Note\n"
        "\n"
        "life after the concert\n"
    )
    out = _apply_wikilinks(
        content,
        {"life": "700_База_Данных/Цитаты/Цель_пустяки"},
    )
    prefix, body = split_frontmatter(out)
    assert '- "domain/life"' in prefix
    assert "domain/[[" not in prefix
    assert "[[700_База_Данных/Цитаты/Цель_пустяки]]" in body
