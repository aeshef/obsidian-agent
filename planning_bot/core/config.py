"""Planning bot configuration — vault paths and constants."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from shared.constants import deepseek_chat_completions_url, deepseek_model, goals_year
from shared.paths import vault_root_optional
from shared.vault_paths_config import dashboards_sub, folder, vault_file, vault_rel_path
from shared.yaml_config import load_merged_config

_PLANNING_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

VAULT_PATH_ENV = os.getenv("VAULT_PATH")
_auto_vault = Path(__file__).resolve().parent.parent.parent.parent.parent
_resolved = vault_root_optional()
if _resolved is not None:
    VAULT_PATH = _resolved
elif VAULT_PATH_ENV:
    _from_env = Path(VAULT_PATH_ENV).expanduser().resolve()
    VAULT_PATH = _from_env if _from_env.is_dir() else _auto_vault
else:
    VAULT_PATH = _auto_vault

GOALS_YEAR = goals_year()
BOT_DIR = Path(__file__).resolve().parent.parent

_dash = VAULT_PATH / folder("dashboards")
_data = _dash / dashboards_sub("data")
_logs = _dash / dashboards_sub("logs")
_graphics = _dash / dashboards_sub("charts")

KANBAN_FILE = VAULT_PATH / folder("tasks") / vault_file("kanban_board")
GOALS_FILE = VAULT_PATH / folder("goals") / vault_file("goals_template", year=GOALS_YEAR)
QUARTERLY_FOCUS_FILE = (
    VAULT_PATH / folder("goals") / vault_file("quarterly_focus_template", year=GOALS_YEAR)
)
REFLECTION_DIR = VAULT_PATH / folder("handwritten") / vault_rel_path("reflection_subdir")
LOGS_DIR = _dash
ACTION_LOGS_DIR = _logs
assert ACTION_LOGS_DIR != LOGS_DIR and ACTION_LOGS_DIR.parent == LOGS_DIR
GRAPHICS_DIR = _graphics
COMPLETED_SOC_FILE = GRAPHICS_DIR / "completed_tasks_soc.json"
ACTION_LOG_PREFIX = vault_file("action_log_prefix")
MAPPING_FILE = _dash / vault_file("goals_mapping_json")

CALENDAR_TXT_FILE = _data / vault_file("calendar_txt")
CALENDAR_JSON_FILE = _data / vault_file("calendar_json")
CALENDAR_DASHBOARD_MD = _dash / vault_file("calendar_dashboard_md")
CALENDAR_ANALYTICS_JSON = _data / vault_file("calendar_week_analytics_json")
CALENDAR_INSIGHTS_CACHE = _data / vault_file("calendar_insights_cache_json")

CONTEXT_MAC_DIR = _data / vault_rel_path("actions_mac")
CONTEXT_TODAY_JSON = _data / vault_rel_path("context_today_json")
CONTEXT_WEEK_JSON = _data / vault_rel_path("context_week_json")

IPHONE_CONTEXT_DIR = _data / vault_rel_path("actions_iphone")
IPHONE_TODAY_JSON = _data / vault_rel_path("iphone_today_json")
IPHONE_WEEK_JSON = _data / vault_rel_path("iphone_week_json")

CHAT_ID_FILE = (
    Path(os.getenv("CHAT_ID_FILE", "")).resolve()
    if os.getenv("CHAT_ID_FILE")
    else (BOT_DIR / "CHAT_ID.txt")
)

_goals_ctx = (os.getenv("GOALS_CONTEXT_FILE") or "").strip()
GOALS_CONTEXT_FILE = (
    Path(_goals_ctx).expanduser().resolve() if _goals_ctx else (BOT_DIR / "goals_context.md")
)

LOG_DIR = (
    Path(os.getenv("PLANNING_BOT_LOG_DIR", "")).resolve()
    if os.getenv("PLANNING_BOT_LOG_DIR")
    else (BOT_DIR / "logs")
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_PLANNING_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_TOKEN = os.getenv("DEEPSEEK_API_TOKEN") or os.getenv("DEEPSEEK_API_KEY")

DEEPSEEK_API_URL = deepseek_chat_completions_url()
DEEPSEEK_MODEL = deepseek_model()


@lru_cache(maxsize=1)
def _kanban_schema() -> dict:
    return load_merged_config(str(_PLANNING_CONFIG_DIR), "kanban_schema")


def _schema_list(key: str) -> list:
    val = _kanban_schema().get(key)
    return list(val) if isinstance(val, list) else []


def _schema_order(key: str) -> dict:
    val = _kanban_schema().get(key)
    return dict(val) if isinstance(val, dict) else {}


_DEFAULT_KANBAN_COLUMNS = [
    "📋 Бэклог",
    "📅 Ждёт даты",
    "⏸ Отложено",
    "🔄 В работе",
    "🚫 Заблокировано",
    "✅ Сделано",
]
KANBAN_COLUMNS = _schema_list("columns") or list(_DEFAULT_KANBAN_COLUMNS)
BACKLOG_COLUMN = KANBAN_COLUMNS[0] if KANBAN_COLUMNS else ""
WAITING_DATE_COLUMN = KANBAN_COLUMNS[1] if len(KANBAN_COLUMNS) > 1 else ""
DONE_COLUMN = KANBAN_COLUMNS[-1] if KANBAN_COLUMNS else ""
IN_WORK_COLUMN = KANBAN_COLUMNS[3] if len(KANBAN_COLUMNS) > 3 else ""
BLOCKED_COLUMN = KANBAN_COLUMNS[4] if len(KANBAN_COLUMNS) > 4 else ""

CATEGORIES = _schema_list("categories")
PRIORITIES = _schema_list("priorities")
CATEGORY_ORDER = _schema_order("category_order")
PRIORITY_ORDER = _schema_order("priority_order")

DEFAULT_CATEGORY = CATEGORIES[0] if CATEGORIES else "прочее"
DEFAULT_PRIORITY = "средний" if "средний" in PRIORITIES else (PRIORITIES[1] if len(PRIORITIES) > 1 else "средний")


def validate_bot_tokens() -> None:
    if not DEEPSEEK_API_TOKEN:
        raise ValueError("DEEPSEEK_API_TOKEN is not set")
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_PLANNING_BOT_TOKEN or TELEGRAM_BOT_TOKEN is not set")
