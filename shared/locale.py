"""Runtime UI locale (AGENT_LOCALE). Default: en for OSS clones; infer ru from vault_paths."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


_env_loaded = False


def _load_dotenv_once() -> None:
    global _env_loaded
    if _env_loaded:
        return
    root = Path(__file__).resolve().parents[1]
    env_file = root / ".env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    _env_loaded = True


@lru_cache(maxsize=1)
def _infer_locale_from_vault_paths() -> str | None:
    try:
        from shared.vault_paths_config import vault_paths_config

        cfg = vault_paths_config()
        blob = str(cfg.get("folders") or {}) + str(cfg.get("files") or {})
        cyr_start, cyr_end = 0x0400, 0x04FF
        if any(cyr_start <= ord(c) <= cyr_end for c in blob):
            return "ru"
    except Exception:
        return None
    return None


def agent_locale() -> str:
    _load_dotenv_once()
    explicit = os.environ.get("AGENT_LOCALE", "").strip().lower()
    if explicit:
        return "ru" if explicit.startswith("ru") else "en"
    inferred = _infer_locale_from_vault_paths()
    if inferred:
        return inferred
    return "en"


def is_english() -> bool:
    return agent_locale().startswith("en")


def messages_stem() -> str:
    return "messages.en" if is_english() else "messages.ru"


def domain_messages_stem() -> str:
    return "domain_messages.en" if is_english() else "domain_messages.ru"
