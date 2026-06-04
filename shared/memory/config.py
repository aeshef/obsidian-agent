"""Load config/agent/memory.yaml."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from shared.agent.config import agent_config_dir
from shared.yaml_config import load_yaml


@lru_cache(maxsize=1)
def load_memory_config() -> dict:
    base = agent_config_dir()
    path = base / "memory.yaml"
    if not path.is_file():
        path = base / "memory.yaml.example"
    return load_yaml(
        path,
        default={
            "global_profile": "user_profile.md",
            "headers": {
                "global_profile": "## Global profile",
                "domain_profile": {
                    "finance": "## Finance profile",
                    "planning": "## Goals context",
                },
            },
            "insights": {"global_limit": 8, "domain_limit": 10},
        },
    )


def global_profile_path() -> Path:
    cfg = load_memory_config()
    raw = os.environ.get("AGENT_USER_PROFILE", "").strip() or str(
        cfg.get("global_profile") or "user_profile.md"
    )
    p = Path(raw)
    if p.is_absolute():
        return p
    return agent_config_dir() / p


def domain_profile_path(domain: str) -> Path | None:
    if domain == "finance":
        try:
            from bot.config_loader import CONFIG_DIR
        except ImportError:
            from finance_bot.bot.config_loader import CONFIG_DIR

        return CONFIG_DIR / "user_context.md"
    if domain == "planning":
        from planning_bot.core.config import GOALS_CONTEXT_FILE

        return GOALS_CONTEXT_FILE
    return None


def profile_header(domain: str) -> str:
    cfg = load_memory_config()
    headers = cfg.get("headers") or {}
    if domain == "global":
        return str(headers.get("global_profile") or "## Global profile")
    domain_headers = headers.get("domain_profile") or {}
    return str(domain_headers.get(domain) or "## Profile")


def insight_limits() -> tuple[int, int]:
    cfg = load_memory_config()
    ins = cfg.get("insights") or {}
    try:
        g = max(0, int(ins.get("global_limit", 8)))
    except (TypeError, ValueError):
        g = 8
    try:
        d = max(0, int(ins.get("domain_limit", 10)))
    except (TypeError, ValueError):
        d = 10
    return g, d
