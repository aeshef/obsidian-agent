"""Vault-relative paths from config/agent/platform.yaml or env (no personal defaults in code)."""
from __future__ import annotations

import os
import re


def _strip_slashes(rel: str) -> str:
    return rel.strip().strip("/")


def knowledge_subdir() -> str:
    """Knowledge base directory relative to VAULT_PATH (e.g. Knowledge or 700_…)."""
    from shared.agent.platform_config import platform_value

    return _strip_slashes(
        platform_value(
            "vault",
            "knowledge_subdir",
            env="VAULT_REL_KNOWLEDGE",
            default="Knowledge",
        )
    )


def knowledge_attachments_subdir() -> str:
    """Attachments folder under knowledge_subdir (config/vault_paths.yaml)."""
    from shared.vault_paths_config import vault_rel_path

    return vault_rel_path("knowledge_attachments")


def knowledge_index_prefix() -> str:
    """rel_path prefix in note index (with trailing /)."""
    d = knowledge_subdir()
    return f"{d}/" if d else ""


def knowledge_path_pattern() -> re.Pattern[str]:
    """For JSON salvage: optional knowledge directory prefix in path strings."""
    sub = re.escape(knowledge_subdir())
    tail = r'[^"\],]{2,240})(?:"|,|\]|\s*$)'
    if sub:
        return re.compile('"((?:' + sub + r'/)?' + tail)
    return re.compile(r'"(' + tail)
