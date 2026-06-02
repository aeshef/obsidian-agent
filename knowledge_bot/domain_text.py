"""Knowledge domain strings from YAML config (no Cyrillic literals in .py)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.domain_messages import dmsg
from shared.yaml_config import load_yaml

_KB_CONFIG = Path(__file__).resolve().parent.parent / "config"


def llm_default_type() -> str:
    return dmsg("knowledge_llm", "default_type")


def llm_default_title() -> str:
    return dmsg("knowledge_llm", "default_title")


def llm_type_link() -> str:
    return dmsg("knowledge_llm", "type_link")


def render(key: str, **kwargs: object) -> str:
    return dmsg("knowledge_render", key, **kwargs)


def brain(key: str, **kwargs: object) -> str:
    return dmsg("knowledge_brain_query", key, **kwargs)


def billing(key: str, **kwargs: object) -> str:
    return dmsg("knowledge_billing", key, **kwargs)


def ocr(key: str, **kwargs: object) -> str:
    return dmsg("knowledge_ocr", key, **kwargs)


def vision(key: str, **kwargs: object) -> str:
    return dmsg("knowledge_vision", key, **kwargs)


def tags_inv(key: str, **kwargs: object) -> str:
    return dmsg("knowledge_tags_inventory", key, **kwargs)


def maintenance(key: str, **kwargs: object) -> str:
    return dmsg("knowledge_maintenance", key, **kwargs)


def serendipity(key: str, **kwargs: object) -> str:
    return dmsg("knowledge_serendipity", key, **kwargs)


def routing_author_line(ctx: str) -> str:
    if not ctx:
        return ""
    return dmsg("knowledge_routing", "author_context_line", context=ctx)


@lru_cache(maxsize=1)
def translit_table() -> dict[int, str]:
    path = _KB_CONFIG / "tag_translit.yaml"
    if not path.is_file():
        path = _KB_CONFIG / "tag_translit.yaml.example"
    data = load_yaml(path, default={})
    raw = data.get("map") if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        return {}
    return {ord(str(k)): str(v) for k, v in raw.items() if k and v}


def translit_ru(s: str) -> str:
    table = translit_table()
    if not table:
        return s
    return s.translate(str.maketrans(table))


@lru_cache(maxsize=1)
def wikilink_noise_tokens() -> frozenset[str]:
    path = _KB_CONFIG / "wikilink_noise.yaml"
    if not path.is_file():
        path = _KB_CONFIG / "wikilink_noise.yaml.example"
    data = load_yaml(path, default={})
    tokens = data.get("tokens") if isinstance(data, dict) else []
    if not isinstance(tokens, list):
        return frozenset()
    return frozenset(str(x).lower() for x in tokens)


def cyrillic_ocr_whitelist() -> str:
    upper = [chr(c) for c in range(0x410, 0x430)] + [chr(0x401)]
    lower = [chr(c) for c in range(0x430, 0x450)] + [chr(0x451)]
    return "".join(upper + lower)
