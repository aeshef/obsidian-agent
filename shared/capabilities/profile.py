"""Load config/agent/capabilities.yaml — missing file uses OSS starter unless OBSIDIAN_AGENT_FULL_INSTALL=1."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Mapping

from shared.agent.config import agent_config_dir
from shared.yaml_config import deep_merge, load_yaml

MODULE_FINANCE = "finance"
MODULE_PLANNING = "planning"
MODULE_KNOWLEDGE = "knowledge"

CONNECTOR_CORPORATE_BADGE = "corporate_badge"
CONNECTOR_BROKER_SYNC = "broker_sync"
CONNECTOR_APPLE_HEALTH = "apple_health"
CONNECTOR_GMAIL_HEALTH = "gmail_health_pipeline"
CONNECTOR_APPLE_CALENDAR = "apple_calendar"
CONNECTOR_MAC_CONTEXT = "mac_context"
CONNECTOR_KB_SERENDIPITY = "knowledge_serendipity"
CONNECTOR_DOMESTIC_BANK_CARDS = "domestic_bank_cards"
CONNECTOR_MANUAL_BROKER = "manual_broker"

SYNC_PROFILE_FULL = "full"
SYNC_PROFILE_FINANCE_ONLY = "finance_only"
SYNC_PROFILE_PLANNING_LIGHT = "planning_light"
SYNC_PROFILE_PLANNING_KANBAN = "planning_kanban"
SYNC_PROFILE_MINIMAL = "minimal"

_ALL_MODULES = (MODULE_FINANCE, MODULE_PLANNING, MODULE_KNOWLEDGE)
_ALL_CONNECTORS = (
    CONNECTOR_CORPORATE_BADGE,
    CONNECTOR_BROKER_SYNC,
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_GMAIL_HEALTH,
    CONNECTOR_APPLE_CALENDAR,
    CONNECTOR_MAC_CONTEXT,
    CONNECTOR_KB_SERENDIPITY,
    CONNECTOR_DOMESTIC_BANK_CARDS,
    CONNECTOR_MANUAL_BROKER,
)

_ENV_MODULE = {
    MODULE_FINANCE: "CAP_MODULE_FINANCE",
    MODULE_PLANNING: "CAP_MODULE_PLANNING",
    MODULE_KNOWLEDGE: "CAP_MODULE_KNOWLEDGE",
}

_ENV_CONNECTOR = {c: f"CAP_CONNECTOR_{c.upper()}" for c in _ALL_CONNECTORS}


def _as_bool(val: Any, default: bool = True) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


_CONNECTOR_YAML_ALIASES: dict[str, str] = {
    "manual_broker_accounts": CONNECTOR_MANUAL_BROKER,
}


def _normalize_connectors_block(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    merged = dict(raw)
    for alias, canonical in _CONNECTOR_YAML_ALIASES.items():
        if alias in merged and canonical not in merged:
            merged[canonical] = merged[alias]
    return merged


def _parse_bool_map(raw: Any, keys: tuple[str, ...], *, default: bool) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return {k: default for k in keys}
    out: dict[str, bool] = {}
    for key in keys:
        out[key] = _as_bool(raw.get(key), default)
    return out


@dataclass(frozen=True)
class CapabilityProfile:
    """Resolved capability flags for one deployment."""

    modules: Mapping[str, bool]
    connectors: Mapping[str, bool]
    sync_profile: str
    feature_overrides: Mapping[str, bool] = field(default_factory=dict)

    def module(self, name: str) -> bool:
        return bool(self.modules.get(name, True))

    def connector(self, name: str) -> bool:
        return bool(self.connectors.get(name, True))

    def enabled_modules(self) -> list[str]:
        return [m for m in _ALL_MODULES if self.module(m)]

    def any_module(self, *names: str) -> bool:
        return any(self.module(n) for n in names)

    def feature(self, name: str) -> bool:
        from shared.capabilities.features import feature_enabled

        return feature_enabled(name, self)


def _full_install_default() -> bool:
    v = (os.environ.get("OBSIDIAN_AGENT_FULL_INSTALL") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _starter_document() -> dict:
    base = agent_config_dir()
    starter = base / "capabilities.starter.yaml.example"
    if not starter.is_file():
        return {}
    data = load_yaml(starter, default={}) or {}
    return data if isinstance(data, dict) else {}


def _default_document() -> dict:
    return {
        "modules": {m: True for m in _ALL_MODULES},
        "connectors": {c: True for c in _ALL_CONNECTORS},
        "sync": {"profile": SYNC_PROFILE_FULL},
    }


def _capabilities_paths() -> tuple[Any, ...]:
    # Explicit CAPABILITIES_PATH is exclusive: a missing override must not
    # silently fall through to the author vault's full-install manifest.
    env_path = (os.environ.get("CAPABILITIES_PATH") or "").strip()
    if env_path:
        return (env_path,)
    base = agent_config_dir()
    return (base / "capabilities.yaml",)


def _load_yaml_document() -> dict:
    for path in _capabilities_paths():
        p = path if hasattr(path, "is_file") else __import__("pathlib").Path(path)
        if p.is_file():
            data = load_yaml(p, default={}) or {}
            return data if isinstance(data, dict) else {}
    return {}


def _apply_env_overrides(modules: dict[str, bool], connectors: dict[str, bool]) -> None:
    for key, env_name in _ENV_MODULE.items():
        raw = os.environ.get(env_name)
        if raw is not None and str(raw).strip() != "":
            modules[key] = _as_bool(raw, modules[key])
    for key, env_name in _ENV_CONNECTOR.items():
        raw = os.environ.get(env_name)
        if raw is not None and str(raw).strip() != "":
            connectors[key] = _as_bool(raw, connectors[key])
    # Legacy env name from capabilities.yaml.example (manual_broker_accounts).
    legacy_manual = os.environ.get("CAP_CONNECTOR_MANUAL_BROKER_ACCOUNTS")
    if legacy_manual is not None and str(legacy_manual).strip() != "":
        connectors[CONNECTOR_MANUAL_BROKER] = _as_bool(
            legacy_manual, connectors[CONNECTOR_MANUAL_BROKER]
        )


def profile_from_document(doc: dict[str, Any]) -> CapabilityProfile:
    """Build profile from a manifest dict (tests, onboarding checks). No env overrides."""
    defaults = _default_document()
    merged = deep_merge(defaults, doc) if isinstance(doc, dict) and doc else defaults
    modules = _parse_bool_map(merged.get("modules"), _ALL_MODULES, default=True)
    connectors = _parse_bool_map(
        _normalize_connectors_block(merged.get("connectors")),
        _ALL_CONNECTORS,
        default=True,
    )
    sync_block = merged.get("sync") if isinstance(merged.get("sync"), dict) else {}
    profile = str((sync_block or {}).get("profile") or SYNC_PROFILE_FULL).strip() or SYNC_PROFILE_FULL
    feature_overrides: dict[str, bool] = {}
    feat_raw = merged.get("features")
    if isinstance(feat_raw, dict):
        for key, val in feat_raw.items():
            feature_overrides[str(key)] = _as_bool(val, True)
    return CapabilityProfile(
        modules=modules,
        connectors=connectors,
        sync_profile=profile,
        feature_overrides=feature_overrides,
    )


def load_capabilities() -> CapabilityProfile:
    defaults = _default_document()
    raw = _load_yaml_document()
    if raw:
        doc = deep_merge(defaults, raw)
    elif _full_install_default():
        doc = defaults
    else:
        starter = _starter_document()
        doc = deep_merge(defaults, starter) if starter else defaults
    base = profile_from_document(doc)
    modules = dict(base.modules)
    connectors = dict(base.connectors)
    _apply_env_overrides(modules, connectors)
    profile = base.sync_profile
    if os.environ.get("CAPABILITIES_SYNC_PROFILE", "").strip():
        profile = os.environ["CAPABILITIES_SYNC_PROFILE"].strip()
    feature_overrides = dict(base.feature_overrides)
    from shared.capabilities.features import apply_feature_env_overrides

    apply_feature_env_overrides(feature_overrides)
    return CapabilityProfile(
        modules=modules,
        connectors=connectors,
        sync_profile=profile,
        feature_overrides=feature_overrides,
    )


@lru_cache(maxsize=1)
def get_capabilities() -> CapabilityProfile:
    return load_capabilities()


def clear_capabilities_cache() -> None:
    get_capabilities.cache_clear()


def module_enabled(name: str) -> bool:
    return get_capabilities().module(name)
