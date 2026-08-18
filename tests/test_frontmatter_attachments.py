from knowledge_bot.services.frontmatter_attachments import (
    attachment_files,
    attachment_links,
    flatten_attachment_fields,
)


def test_flatten_nested_attachments_to_lists():
    fm = {
        "type": "мысль",
        "title": "x",
        "attachments": {
            "links": [],
            "files": ["700_База_Данных/Export/2026/08/a.jpg"],
        },
        "source": "telegram",
    }
    out = flatten_attachment_fields(fm)
    assert "attachments" not in out
    assert out["files"] == ["700_База_Данных/Export/2026/08/a.jpg"]
    assert "links" not in out
    assert out["source"] == "telegram"


def test_attachment_readers_merge_flat_and_nested():
    fm = {
        "files": ["a.jpg"],
        "attachments": {"files": ["a.jpg", "b.jpg"], "links": ["https://x.test"]},
    }
    assert attachment_files(fm) == ["a.jpg", "b.jpg"]
    assert attachment_links(fm) == ["https://x.test"]


def test_attachment_json_string_from_obsidian_properties():
    fm = {
        "attachments": '{"links": [], "files": ["Export/x.jpg"]}',
    }
    assert attachment_files(fm) == ["Export/x.jpg"]
    assert flatten_attachment_fields(fm)["files"] == ["Export/x.jpg"]
