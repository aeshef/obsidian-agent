import yaml

from knowledge_bot.core.settings import EnumsConfig
from knowledge_bot.services.tag_normalize import normalize_tags
from knowledge_bot.services.tag_remap import (
    TAXONOMY_ASCII_MAP,
    apply_taxonomy_ascii,
    canonicalize_tags,
)


def test_canonicalize_tags_maps_cyrillic_category_and_dedupes_tech():
    assert canonicalize_tags(["category/еда", "domain/travel"]) == [
        "category/food",
        "domain/travel",
    ]
    assert canonicalize_tags(["topic/technology", "domain/tech"]) == ["domain/tech"]
    assert canonicalize_tags(["topic/tech", "topic/ml"]) == ["domain/tech", "topic/ml"]


def test_normalize_tags_maps_category_eda_via_synonyms():
    enums = EnumsConfig(
        namespaces_controlled=frozenset({"category"}),
        common={},
        per_type={"место": {"category": ["culture", "food", "nature"]}},
        synonyms={"category": {"еда": "food", "культура": "culture"}},
    )
    assert normalize_tags(["category/еда", "domain/travel"], enums, "место") == [
        "category/food",
        "domain/travel",
    ]


def test_normalize_tags_maps_topic_technology_to_domain_tech():
    enums = EnumsConfig(
        namespaces_controlled=frozenset({"category"}),
        common={},
        per_type={},
        synonyms={},
    )
    tags = normalize_tags(
        ["topic/technology", "domain/tech", "topic/ml"], enums, "знание"
    )
    assert "topic/technology" not in tags
    assert "topic/tech" not in tags
    assert "domain/tech" in tags
    assert "topic/ml" in tags


def test_apply_taxonomy_ascii_rewrites_tags_and_category_field(tmp_path):
    note = tmp_path / "700_База_Данных" / "Места" / "Cafe.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "type: место\n"
        "title: Cafe\n"
        "tags:\n"
        "  - domain/travel\n"
        "  - category/еда\n"
        "attachments:\n"
        "  files:\n"
        "    - Export/a.jpg\n"
        "  links: []\n"
        "category: еда\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    dry = apply_taxonomy_ascii(tmp_path, dry_run=True)
    assert dry["notes_touched"] == 1
    assert "category: еда" in note.read_text(encoding="utf-8")

    written = apply_taxonomy_ascii(tmp_path, dry_run=False)
    assert written["notes_touched"] == 1
    assert written["tag_changes"] >= 1
    assert written["field_changes"] == 1
    fm = yaml.safe_load(note.read_text(encoding="utf-8").split("---", 2)[1])
    assert fm["tags"] == ["category/food", "domain/travel"]
    assert fm["category"] == "food"
    assert "attachments" not in fm
    assert fm["files"] == ["Export/a.jpg"]

    again = apply_taxonomy_ascii(tmp_path, dry_run=False)
    assert again["notes_touched"] == 0


def test_taxonomy_map_never_collapses_gadgets_into_domain_tech():
    assert TAXONOMY_ASCII_MAP["category/техника"] == "category/gadgets"
    assert "category/техника" not in {
        k for k, v in TAXONOMY_ASCII_MAP.items() if v == "domain/tech"
    }
