"""Knowledge bot config loaders: types, enums, prompts, media extensions."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from shared.prompts import load_prompt as _load_prompt
from shared.yaml_config import load_merged_config, load_yaml

_log = logging.getLogger("kb.settings")
_KB_ROOT = Path(__file__).resolve().parent.parent


def get_config_path() -> Path:
    """Directory with types.yaml, enums.yaml, prompts/, hubs_registry.yaml."""
    return _resolve_config_dir()


def _resolve_config_dir(explicit: Path | str | None = None) -> Path:
    if explicit is not None:
        p = Path(explicit).expanduser()
        if p.is_dir():
            return p.resolve()
    raw = (os.environ.get("AGENT_CONFIG_PATH") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if p.is_dir():
            return p.resolve()
        _log.warning("AGENT_CONFIG_PATH is not a directory: %s", raw)
    return (_KB_ROOT / "config").resolve()


def load_prompt(
    config_dir: Path | str,
    name: str,
    *,
    required: bool = False,
    subdir: str = "prompts",
) -> str:
    return _load_prompt(Path(config_dir), name, required=required, subdir=subdir)


@lru_cache(maxsize=1)
def get_asr_config() -> dict:
    return load_merged_config(str(_KB_ROOT / "config"), "asr_config")


@dataclass(frozen=True)
class TypesConfig:
    default_template: str
    default_type: str
    types: dict[str, dict[str, str]]

    def dir_for(self, type_name: str) -> str:
        entry = self.types.get(type_name)
        if entry and entry.get("dir"):
            return str(entry["dir"])
        fallback = self.types.get(self.default_type) or {}
        return str(fallback.get("dir") or "")

    def template_for(self, type_name: str) -> str:
        entry = self.types.get(type_name)
        if entry and entry.get("template"):
            return str(entry["template"])
        return self.default_template


@lru_cache(maxsize=8)
def load_types_config(config_dir: Path | str) -> TypesConfig:
    base = _resolve_config_dir(config_dir)
    data = load_merged_config(str(base), "types")
    raw_types = data.get("types") or {}
    types: dict[str, dict[str, str]] = {}
    if isinstance(raw_types, dict):
        for key, val in raw_types.items():
            types[str(key)] = val if isinstance(val, dict) else {}
    return TypesConfig(
        default_template=str(data.get("default_template") or "Знание.j2.md"),
        default_type=str(data.get("default_type") or "знание"),
        types=types,
    )


@dataclass(frozen=True)
class EnumsConfig:
    namespaces_controlled: frozenset[str]
    common: dict[str, list[str]]
    per_type: dict[str, dict[str, list[str]]]
    synonyms: dict[str, dict[str, str]]


@lru_cache(maxsize=8)
def load_enums_config(config_dir: Path | str) -> EnumsConfig:
    base = _resolve_config_dir(config_dir)
    data = load_merged_config(str(base), "enums")
    ns_block = data.get("namespaces")
    controlled = None
    if isinstance(ns_block, dict):
        controlled = ns_block.get("controlled")
    if controlled is None:
        controlled = data.get("namespaces_controlled")
    namespaces_controlled = (
        frozenset(str(x) for x in controlled)
        if isinstance(controlled, list)
        else frozenset()
    )
    common_raw = data.get("common") or {}
    per_type_raw = data.get("per_type") or {}
    synonyms_raw = data.get("synonyms") or {}
    return EnumsConfig(
        namespaces_controlled=namespaces_controlled,
        common={
            str(k): [str(x) for x in v]
            for k, v in common_raw.items()
            if isinstance(v, list)
        },
        per_type={
            str(t): {
                str(k): [str(x) for x in vals]
                for k, vals in fields.items()
                if isinstance(vals, list)
            }
            for t, fields in per_type_raw.items()
            if isinstance(fields, dict)
        },
        synonyms={
            str(ns): {str(a): str(b) for a, b in mapping.items()}
            for ns, mapping in synonyms_raw.items()
            if isinstance(mapping, dict)
        },
    )


@lru_cache(maxsize=8)
def load_media_extensions(config_dir: Path | str) -> dict[str, list[str]]:
    base = _resolve_config_dir(config_dir)
    path = base / "media_extensions.yaml"
    if not path.is_file():
        path = base / "media_extensions.yaml.example"
    return load_yaml(
        path,
        default={
            "image": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
            "video": [".mp4", ".mov", ".avi", ".mkv"],
            "document": [".pdf", ".doc", ".docx", ".txt"],
        },
    )


def get_author_context(config_dir: Path | str) -> str:
    base = _resolve_config_dir(config_dir)
    for candidate in (
        base / "author_context.txt",
        _KB_ROOT / "config" / "author_context.txt",
    ):
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8", errors="replace").strip()
            lines = [
                ln
                for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            if lines:
                return "\n".join(lines)
    env_ctx = (os.environ.get("AUTHOR_CONTEXT") or "").strip()
    return env_ctx
