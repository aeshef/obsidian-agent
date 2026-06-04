"""Knowledge bot runtime configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from shared.agent.config import agent_config_dir
from shared.constants import deepseek_chat_completions_url
from shared.paths import vault_root


@dataclass(frozen=True)
class AppConfig:
    vault_path: Path
    agent_config_path: Path
    templates_path: Path
    deepseek_api_key: str
    deepseek_base_url: str
    telegram_bot_token: str
    telegram_user_id: int | None
    telegram_api_base: str


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    kb_root = Path(__file__).resolve().parent.parent
    uid_raw = (os.environ.get("TELEGRAM_USER_ID") or "").strip()
    uid = int(uid_raw) if uid_raw.isdigit() else None
    agent_path = agent_config_dir()
    return AppConfig(
        vault_path=vault_root(),
        agent_config_path=agent_path,
        templates_path=kb_root / "templates",
        deepseek_api_key=(
            os.environ.get("DEEPSEEK_API_TOKEN")
            or os.environ.get("DEEPSEEK_API_KEY")
            or ""
        ),
        deepseek_base_url=deepseek_chat_completions_url(),
        telegram_bot_token=(
            os.environ.get("TELEGRAM_KNOWLEDGE_BOT_TOKEN")
            or os.environ.get("TELEGRAM_BOT_TOKEN")
            or ""
        ),
        telegram_user_id=uid,
        telegram_api_base=os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org"),
    )
