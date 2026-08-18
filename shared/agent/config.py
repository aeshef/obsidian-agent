"""Load config/agent/*.yaml from monorepo root."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from shared.yaml_config import load_yaml

_AGENT_DIR = Path(__file__).resolve().parent


def agent_config_dir() -> Path:
    root = os.environ.get("AGENT_ROOT", "").strip()
    if root:
        return Path(root) / "config" / "agent"
    return _AGENT_DIR.parents[1] / "config" / "agent"


@lru_cache(maxsize=1)
def load_models_config() -> dict:
    cfg = load_yaml(agent_config_dir() / "models.yaml")
    roles = cfg.get("roles") or {}
    defaults = {
        "parse": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "analyze": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "chat": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
    }
    for key, val in roles.items():
        if isinstance(val, dict) and val.get("model"):
            defaults[key] = str(val["model"])
    defaults_block = cfg.get("defaults") if isinstance(cfg.get("defaults"), dict) else {}
    cascade = cfg.get("cascade") if isinstance(cfg.get("cascade"), dict) else {}
    return {
        "roles": roles,
        "model_map": defaults,
        "defaults": defaults_block,
        "cascade": cascade,
    }


@lru_cache(maxsize=1)
def load_tools_config() -> dict:
    return load_yaml(
        agent_config_dir() / "tools.yaml",
        default={"categories": {}, "fallback_threshold": 4},
    )


@lru_cache(maxsize=1)
def load_health_parse_config() -> dict:
    cfg_dir = agent_config_dir()
    path = cfg_dir / "health_parse.yaml"
    if not path.is_file():
        path = cfg_dir / "health_parse.yaml.example"
    return load_yaml(path, default={})


@lru_cache(maxsize=1)
def load_goals_parse_config() -> dict:
    cfg_dir = agent_config_dir()
    path = cfg_dir / "goals_parse.yaml"
    if not path.is_file():
        path = cfg_dir / "goals_parse.yaml.example"
    return load_yaml(path, default={})


@lru_cache(maxsize=1)
def goal_context_key_aliases() -> dict[str, str]:
    """Map Obsidian inline-field labels → context|include|exclude|success."""
    defaults: dict[str, str] = {
        "context": "context",
        "meaning": "context",
        "include": "include",
        "includes": "include",
        "exclude": "exclude",
        "excludes": "exclude",
        "success": "success",
        "success criteria": "success",
    }
    raw = load_goals_parse_config().get("context_key_aliases") or {}
    merged = dict(defaults)
    for key, val in raw.items():
        norm = re.sub(r"\s+", " ", str(key).strip().lower())
        if norm and val:
            merged[norm] = str(val)
    return merged


@lru_cache(maxsize=1)
def load_routing_config() -> dict:
    from shared.yaml_config import load_merged_config

    merged = load_merged_config(str(agent_config_dir()), "routing")
    if merged:
        return merged
    return {
        "domain_rules": {},
        "default_intents": {
            "finance": "add_transaction",
            "planning": "add_task",
            "knowledge": "new_note",
        },
        "agent": {
            "tools_first_iter_domains": [
                "finance",
                "planning",
                "knowledge",
                "unified",
            ],
        },
    }


def tools_first_iter_domains() -> frozenset[str]:
    cfg = load_routing_config().get("agent") or {}
    raw = cfg.get("tools_first_iter_domains")
    if isinstance(raw, list) and raw:
        return frozenset(str(d).strip() for d in raw if str(d).strip())
    return frozenset({"finance", "planning", "knowledge", "unified"})
