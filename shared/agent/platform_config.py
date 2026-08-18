"""config/agent/platform.yaml (+ env overrides). Numbers and limits — not in code."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from shared.agent.config import agent_config_dir
from shared.yaml_config import load_yaml


def _coerce_int(val: Any, default: int) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _coerce_float(val: Any, default: float) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=1)
def load_platform_config() -> dict:
    base = agent_config_dir()
    path = base / "platform.yaml"
    if not path.is_file():
        path = base / "platform.yaml.example"
    return load_yaml(path, default={}) or {}


def platform_value(
    section: str,
    key: str,
    *,
    env: str | None = None,
    default: Any = None,
) -> Any:
    if env:
        raw = os.environ.get(env)
        if raw is not None and str(raw).strip() != "":
            return raw.strip()
    block = load_platform_config().get(section) or {}
    if isinstance(block, dict) and key in block:
        return block[key]
    return default


def platform_int(
    section: str,
    key: str,
    *,
    env: str | None = None,
    default: int = 0,
) -> int:
    return _coerce_int(platform_value(section, key, env=env, default=default), default)


def platform_float(
    section: str,
    key: str,
    *,
    env: str | None = None,
    default: float = 0.0,
) -> float:
    return _coerce_float(platform_value(section, key, env=env, default=default), default)


def platform_bool(
    section: str,
    key: str,
    *,
    env: str | None = None,
    default: bool = False,
) -> bool:
    raw = platform_value(section, key, env=env, default=default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(int(raw))
    s = str(raw or "").strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return default


def platform_str(
    section: str,
    key: str,
    *,
    env: str | None = None,
    default: str = "",
) -> str:
    raw = platform_value(section, key, env=env, default=default)
    if raw is None:
        return default
    return str(raw).strip()


def platform_str_list(
    section: str,
    key: str,
    *,
    env: str | None = None,
    default: list[str] | None = None,
) -> list[str]:
    fallback = list(default or [])
    raw = platform_value(section, key, env=env, default=None)
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        return [p.strip() for p in raw.split(",") if p.strip()]
    return fallback


def platform_section(section: str) -> dict:
    block = load_platform_config().get(section) or {}
    return block if isinstance(block, dict) else {}
