from pathlib import Path
from shared.locale import agent_locale
from shared.yaml_config import load_catalog_config


def ui_config():
    locale = "ru" if agent_locale().startswith("ru") else "en"
    return load_catalog_config(str(Path(__file__).resolve().parents[2] / "config"), f"obsidian_ui.{locale}")
