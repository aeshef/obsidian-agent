from knowledge_bot.services.tag_normalize import (
    fallback_tags_for_type,
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
