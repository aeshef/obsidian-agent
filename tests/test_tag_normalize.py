from knowledge_bot.services.tag_normalize import (
    clean_existing_tags,
    fallback_tags_for_type,
    is_malformed_tag,
    normalize_tags,
    parse_tag_llm_response,
)


def test_parse_tag_llm_response_tags_key():
    assert parse_tag_llm_response({"tags": ["domain/life", "topic/foo"]}) == [
        "domain/life",
        "topic/foo",
    ]


def test_parse_tag_llm_response_paths_wrapper():
    assert parse_tag_llm_response({"paths": ["domain/study"]}) == ["domain/study"]


def test_parse_tag_llm_response_bare_list():
    assert parse_tag_llm_response(["domain/tech"]) == ["domain/tech"]


def test_parse_tag_llm_response_llm_error():
    assert parse_tag_llm_response({"_llm_error": "json_parse"}) == []


def test_fallback_tags_for_znanie():
    tags = fallback_tags_for_type("знание")
    assert tags == ["domain/life"]


def test_fallback_tags_for_video_reels():
    tags = fallback_tags_for_type("видео", source="reels")
    assert "domain/entertainment" in tags
    assert "topic/video" in tags
    assert "source/reels" in tags


class _Enums:
    common = {"domain": ["tech", "life"]}
    per_type = {}
    synonyms = {}
    namespaces_controlled = {"domain"}


def test_normalize_tags_drops_wikilink_tags():
    tags = normalize_tags(
        [
            "domain/tech",
            "topic/[[700_База_Данных/Видео/Балет_кино]]",
            "domain/[[700_База_Данных/Песни/Динамичная_музыка]]",
        ],
        _Enums(),
        "video",
    )

    assert tags == ["domain/tech"]


def test_clean_existing_tags_removes_malformed_frontmatter_tags():
    assert is_malformed_tag("topic/[[700_База_Данных/Видео/Балет_кино]]")
    assert clean_existing_tags(
        ["domain/life", "topic/[[700_База_Данных/Видео/Балет_кино]]", "topic/music"]
    ) == ["domain/life", "topic/music"]


def test_sanitize_malformed_tags_in_vault(tmp_path):
    import yaml

    from knowledge_bot.services.tag_cleanup import sanitize_malformed_tags

    vault = tmp_path
    note = vault / "700_База_Данных" / "Видео" / "Bad.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "type: видео\n"
        "tags:\n"
        "  - domain/entertainment\n"
        "  - topic/[[700_База_Данных/Видео/Балет_кино]]\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )

    agent_config = tmp_path / "config"
    changed = sanitize_malformed_tags(vault, agent_config, apply=True)
    assert len(changed) == 1

    text = note.read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---", 2)[1])
    assert fm["tags"] == ["domain/entertainment"]
