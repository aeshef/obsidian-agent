"""Config-driven free-text → planning menu action (daily_checkin.yaml text_triggers)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from planning_bot.app.ui import pmsg
from planning_bot.core.settings import get_config_path
from shared.capabilities.features import feature_enabled
from shared.yaml_config import load_merged_config


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().casefold().split())


@lru_cache(maxsize=1)
def _text_triggers() -> list[dict[str, Any]]:
    cfg = load_merged_config(str(get_config_path()), "daily_checkin")
    raw = cfg.get("text_triggers")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("action"):
            out.append(dict(item))
    return out


def _feature_ok(spec: dict[str, Any]) -> bool:
    feat = spec.get("feature")
    if not feat:
        return True
    return feature_enabled(str(feat))


def _phrases_for_spec(spec: dict[str, Any]) -> list[str]:
    keys = spec.get("phrase_keys")
    if not isinstance(keys, list):
        return []
    out: list[str] = []
    for key in keys:
        phrase = pmsg(str(key).strip())
        norm = _normalize(phrase)
        if norm:
            out.append(norm)
    return out


def match_planning_text_trigger(text: str) -> str | None:
    """Return menu action id (e.g. start_daily_checkin) or None."""
    norm = _normalize(text)
    if not norm:
        return None
    for spec in _text_triggers():
        if not _feature_ok(spec):
            continue
        if norm in _phrases_for_spec(spec):
            return str(spec["action"])
    return None


def planning_trigger_phrases() -> frozenset[str]:
    """All normalized trigger phrases (for auto-mode planning routing)."""
    found: set[str] = set()
    for spec in _text_triggers():
        if not _feature_ok(spec):
            continue
        found.update(_phrases_for_spec(spec))
    return frozenset(found)


def clear_planning_text_triggers_cache() -> None:
    _text_triggers.cache_clear()
