"""Load config/agent/*.yaml from monorepo root."""
from __future__ import annotations

import os
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
    return {"roles": roles, "model_map": defaults}


@lru_cache(maxsize=1)
def load_tools_config() -> dict:
    return load_yaml(
        agent_config_dir() / "tools.yaml",
        default={"categories": {}, "fallback_threshold": 4},
    )


@lru_cache(maxsize=1)
def load_routing_config() -> dict:
    return load_yaml(
        agent_config_dir() / "routing.yaml",
        default={
            "domain_rules": {},
            "default_intents": {
                "finance": "add_transaction",
                "planning": "add_task",
                "knowledge": "new_note",
            },
        },
    )
