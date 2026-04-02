"""YAML/text config loaders for the finance bot."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Union

from shared.prompts import load_text
from shared.yaml_config import load_merged_config, load_yaml

log = logging.getLogger("finance.config")

[REDACTED]
_config_cache: Dict[str, Union[dict, str]] = {}


def load_yaml_config(filename: str) -> dict:
    path = CONFIG_DIR / filename
    if not path.exists():
        log.warning("Config file not found: %s, using defaults", path)
    return load_yaml(path)


def load_text_config(filename: str) -> str:
    """Load prompt from config/prompts/{name}.txt or {name}.example.txt."""
    from shared.prompts import load_prompt

    name = filename.replace(".txt", "")
    text = load_prompt(CONFIG_DIR, name, subdir="prompts")
    if not text:
        log.warning("Prompt not found: config/prompts/%s.txt (nor .example.txt)", name)
    return text


def get_llm_config() -> dict:
    if "llm" not in _config_cache:
        _config_cache["llm"] = load_merged_config(str(CONFIG_DIR), "llm_config")
    return _config_cache["llm"]


def get_asr_config() -> dict:
    if "asr" not in _config_cache:
        _config_cache["asr"] = load_merged_config(str(CONFIG_DIR), "asr_config")
    return _config_cache["asr"]


def get_nlu_config() -> dict:
    """NLU: nlu_config.yaml merged over nlu_config.yaml.example."""
    if "nlu" not in _config_cache:
        from shared.yaml_config import load_merged_config

        _config_cache["nlu"] = load_merged_config(str(CONFIG_DIR), "nlu_config")
    return _config_cache["nlu"]


def nlu_menu_buttons(cfg: Optional[dict] = None) -> set[str]:
    """Reply keyboard labels: nlu_config.menu_buttons or finance.menu in messages.ru.yaml."""
    cfg = cfg or get_nlu_config()
    raw = cfg.get("menu_buttons")
    if raw:
        return set(raw)
    from bot.menu_labels import finance_menu_texts

    t = finance_menu_texts()
    return {
        t["invest"],
        t["balance"],
        t["last_ops"],
        t["plan"],
    }


def nlu_exact_commands(cfg: Optional[dict] = None) -> set[str]:
    cfg = cfg or get_nlu_config()
    from shared.capabilities.finance_gates import filter_finance_exact_commands

    return filter_finance_exact_commands(set(cfg.get("exact_commands") or []))


def get_summary_config() -> dict:
    if "summary" not in _config_cache:
        _config_cache["summary"] = load_merged_config(str(CONFIG_DIR), "summary_config")
    return _config_cache["summary"]


def get_amount_extract_prompt() -> str:
    from shared.prompts import load_prompt

    return load_prompt(CONFIG_DIR, "amount_extract_prompt", subdir="prompts")


def get_nlu_prompt() -> str:
    if "nlu_prompt" not in _config_cache:
        _config_cache["nlu_prompt"] = load_text_config("nlu_prompt.txt")
    return _config_cache["nlu_prompt"]


def get_summary_prompt() -> str:
    if "summary_prompt" not in _config_cache:
        _config_cache["summary_prompt"] = load_text_config("summary_prompt.txt")
    return _config_cache["summary_prompt"]


def get_plan_parse_prompt() -> str:
    if "plan_parse_prompt" not in _config_cache:
        from shared.prompts import load_prompt

        _config_cache["plan_parse_prompt"] = load_prompt(
            CONFIG_DIR, "plan_parse", subdir="prompts", required=True
        )
    return _config_cache["plan_parse_prompt"]


def get_badge_config() -> dict:
    if "badge" not in _config_cache:
        path = CONFIG_DIR / "badge.yaml"
        if not path.exists():
            path = CONFIG_DIR / "badge.yaml.example"
        _config_cache["badge"] = load_yaml(path)
    return _config_cache["badge"]


def badge_yaml_enabled() -> bool:
    """badge.yaml enabled flag only (ignores capabilities manifest)."""
    return bool(get_badge_config().get("enabled"))


def is_badge_enabled() -> bool:
    """Corporate badge UI/tools/schedulers — manifest connector + badge.yaml."""
    from shared.capabilities.profile import CONNECTOR_CORPORATE_BADGE, get_capabilities

    if not get_capabilities().connector(CONNECTOR_CORPORATE_BADGE):
        return False
    return badge_yaml_enabled()


def get_user_context() -> str:
    path = CONFIG_DIR / "user_context.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception as e:
        log.error("Failed to read user_context.md: %s", e)
        return ""
