"""Runtime UI locale (AGENT_LOCALE). Default: en for OSS clones."""
from __future__ import annotations

import os


def agent_locale() -> str:
    return os.environ.get("AGENT_LOCALE", "en").strip().lower()


def is_english() -> bool:
    return agent_locale().startswith("en")


def messages_stem() -> str:
    return "messages.en" if is_english() else "messages.ru"


def domain_messages_stem() -> str:
    return "domain_messages.en" if is_english() else "domain_messages.ru"
