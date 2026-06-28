"""Load config/vault_analytics.yaml (+ example merge)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.yaml_config import load_merged_config

_REPO_CONFIG = Path(__file__).resolve().parent.parent.parent / "config"


@lru_cache(maxsize=1)
def vault_analytics_config() -> dict:
    return load_merged_config(str(_REPO_CONFIG), "vault_analytics")
