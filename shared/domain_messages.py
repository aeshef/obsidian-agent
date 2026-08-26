"""Non-UI domain strings — config/domain_messages/{locale}/*.yaml.example packages.

Optional local overlays: gitignored ``domain_messages.{locale}.yaml``.
Legacy monolith ``domain_messages.{locale}.yaml.example`` is no longer shipped;
``_load_monolith`` remains only for older checkouts that still have those files.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.capabilities.ui_bindings import message_allowed
from shared.locale import agent_locale
from shared.yaml_config import deep_merge, load_yaml

_REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"
_PACKAGE_ORDER = ("shared", "finance", "planning", "knowledge")


def _overlay_yaml(merged: dict, path: Path) -> dict:
    if not path.is_file():
        return merged
    over = load_yaml(path)
    return deep_merge(merged, over) if over else merged


def load_domain_packages(locale: str) -> dict:
    """Merge per-domain packages under config/domain_messages/{locale}/ (public helper)."""
    return _load_packages(locale)


def _load_packages(locale: str) -> dict:
    """Merge per-domain packages under config/domain_messages/{locale}/."""
    pkg_dir = _REPO_CONFIG / "domain_messages" / locale
    if not pkg_dir.is_dir():
        return {}
    merged: dict = {}
    for name in _PACKAGE_ORDER:
        example = pkg_dir / f"{name}.yaml.example"
        local = pkg_dir / f"{name}.yaml"
        if example.is_file():
            merged = deep_merge(merged, load_yaml(example, default={}))
        if local.is_file():
            merged = _overlay_yaml(merged, local)
    return merged


def _load_monolith(locale: str) -> dict:
    base = _REPO_CONFIG
    if locale.startswith("en"):
        merged = load_yaml(base / "domain_messages.en.yaml.example", default={})
        return _overlay_yaml(merged, base / "domain_messages.en.yaml")
    merged = load_yaml(base / "domain_messages.ru.yaml.example", default={})
    merged = _overlay_yaml(merged, base / "domain_messages.yaml")
    return _overlay_yaml(merged, base / "domain_messages.ru.yaml")


def _ru_domain() -> dict:
    packages = _load_packages("ru")
    if packages:
        # Local monolith overlays still win for author overrides.
        packages = _overlay_yaml(packages, _REPO_CONFIG / "domain_messages.yaml")
        return _overlay_yaml(packages, _REPO_CONFIG / "domain_messages.ru.yaml")
    return _load_monolith("ru")


def _en_domain() -> dict:
    packages = _load_packages("en")
    if packages:
        return _overlay_yaml(packages, _REPO_CONFIG / "domain_messages.en.yaml")
    return _load_monolith("en")


@lru_cache(maxsize=2)
def _domain(_locale: str) -> dict:
    if _locale.startswith("en"):
        ru = _ru_domain()
        en = _en_domain()
        if ru and en:
            return deep_merge(ru, en)
        return en or ru
    return _ru_domain()


def _active_domain() -> dict:
    return _domain(agent_locale())


def clear_domain_messages_cache() -> None:
    _domain.cache_clear()


def dmsg(*keys: str, default: str = "", cap: str | None = None, **kwargs: object) -> str:
    if not message_allowed(*keys, explicit_cap=cap):
        return default
    node: object = _active_domain()
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k)
    template = str(node).strip() if node is not None else default
    if kwargs and template:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template
    return template
