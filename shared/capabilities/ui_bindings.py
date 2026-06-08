"""Map UI/domain message paths to capability specs (config/ui_capabilities.yaml)."""
from __future__ import annotations

import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import Optional

from shared.capabilities.features import feature_enabled
from shared.capabilities.prompt_filter import capability_active
from shared.capabilities.profile import CapabilityProfile, get_capabilities
from shared.yaml_config import load_merged_config

_REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


@lru_cache(maxsize=1)
def _binding_map() -> dict[str, str]:
    raw = load_merged_config(str(_REPO_CONFIG), "ui_capabilities")
    strings = raw.get("strings")
    if not isinstance(strings, dict):
        return {}
    out: dict[str, str] = {}
    for path, spec in strings.items():
        if isinstance(path, str) and isinstance(spec, str) and path.strip() and spec.strip():
            out[path.strip()] = spec.strip()
    return out


@lru_cache(maxsize=1)
def _pattern_map() -> tuple[tuple[str, str], ...]:
    raw = load_merged_config(str(_REPO_CONFIG), "ui_capabilities")
    patterns = raw.get("patterns")
    if not isinstance(patterns, dict):
        return ()
    items: list[tuple[str, str]] = []
    for pat, spec in patterns.items():
        if isinstance(pat, str) and isinstance(spec, str) and pat.strip() and spec.strip():
            items.append((pat.strip(), spec.strip()))
    return tuple(sorted(items, key=lambda x: -len(x[0])))


def message_path(*keys: str) -> str:
    return ".".join(keys)


def cap_spec_for_path(path: str) -> str | None:
    exact = _binding_map().get(path)
    if exact is not None:
        return exact
    for pat, spec in _pattern_map():
        if fnmatch.fnmatch(path, pat):
            return spec
    return None


def cap_spec_for_keys(*keys: str) -> str | None:
    return cap_spec_for_path(message_path(*keys))


def cap_satisfied(spec: str, profile: Optional[CapabilityProfile] = None) -> bool:
    """Evaluate binding spec; unknown specs fall back to capability_active."""
    prof = profile or get_capabilities()
    s = (spec or "").strip()
    if not s:
        return True
    if s.startswith("any:"):
        parts = [p.strip() for p in s[4:].split(",") if p.strip()]
        return any(cap_satisfied(p, prof) for p in parts)
    if s.startswith("feature:"):
        return feature_enabled(s[8:].strip(), prof)
    if s == "gate:broker":
        from shared.capabilities.finance_gates import broker_sync_enabled

        return broker_sync_enabled()
    if s == "gate:badge":
        from shared.capabilities.registry import corporate_badge_runtime_enabled

        return corporate_badge_runtime_enabled()
    return capability_active(s, prof)


def message_allowed(
    *keys: str,
    explicit_cap: str | None = None,
    profile: Optional[CapabilityProfile] = None,
) -> bool:
    spec = explicit_cap if explicit_cap is not None else cap_spec_for_keys(*keys)
    if spec is None:
        return True
    return cap_satisfied(spec, profile)


def clear_ui_bindings_cache() -> None:
    _binding_map.cache_clear()
    _pattern_map.cache_clear()


def clear_all_message_caches() -> None:
    clear_ui_bindings_cache()
    from shared.i18n import clear_messages_cache

    clear_messages_cache()
    from shared.domain_messages import clear_domain_messages_cache

    clear_domain_messages_cache()
    from shared.telegram.host.domain_routing import clear_domain_routing_cache
    from shared.telegram.host.menu_detection import clear_menu_detection_cache

    clear_domain_routing_cache()
    clear_menu_detection_cache()
