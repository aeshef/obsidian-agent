"""Shell exports for vault folder names (config/vault_paths.yaml)."""
from __future__ import annotations

from shared.vault_paths_config import dashboards_sub, finance_sub, folder, vault_file, vault_rel_path


def _sh_quote(val: str) -> str:
    s = str(val).replace("'", "'\"'\"'")
    return f"'{s}'"


def export_shell_env() -> str:
    """Emit export VAULT_FOLDER_* / VAULT_PATH_* for obsidian_sync.sh."""
    lines = [
        f"export VAULT_FOLDER_TASKS={_sh_quote(folder('tasks'))}",
        f"export VAULT_FOLDER_GOALS={_sh_quote(folder('goals'))}",
        f"export VAULT_FOLDER_DASHBOARDS={_sh_quote(folder('dashboards'))}",
        f"export VAULT_FOLDER_ROUTINES={_sh_quote(folder('routines'))}",
        f"export VAULT_FOLDER_HANDWRITTEN={_sh_quote(folder('handwritten'))}",
        f"export VAULT_DASH_LOGS={_sh_quote(dashboards_sub('logs'))}",
        f"export VAULT_DASH_CHARTS={_sh_quote(dashboards_sub('charts'))}",
        f"export VAULT_DASH_DATA={_sh_quote(dashboards_sub('data'))}",
        f"export VAULT_PATH_ACTIONS_MAC={_sh_quote(vault_rel_path('actions_mac'))}",
        f"export VAULT_PATH_ACTIONS_IPHONE={_sh_quote(vault_rel_path('actions_iphone'))}",
        f"export VAULT_PATH_CONTEXT_TODAY={_sh_quote(vault_rel_path('context_today_json'))}",
        f"export VAULT_PATH_CONTEXT_WEEK={_sh_quote(vault_rel_path('context_week_json'))}",
        f"export VAULT_PATH_IPHONE_TODAY={_sh_quote(vault_rel_path('iphone_today_json'))}",
        f"export VAULT_PATH_IPHONE_WEEK={_sh_quote(vault_rel_path('iphone_week_json'))}",
        f"export VAULT_FILE_CALENDAR_JSON={_sh_quote(vault_file('calendar_json'))}",
        f"export VAULT_FILE_CHART_DAILY_ACTIVITY={_sh_quote(vault_file('chart_daily_activity_png'))}",
        f"export VAULT_FILE_CHART_CALENDAR_WEEK_PNG={_sh_quote(vault_file('chart_calendar_week_png'))}",
        f"export VAULT_FILE_CHART_NUTRITION_PNG={_sh_quote(vault_file('chart_nutrition_png'))}",
        f"export VAULT_FILE_AUDIT_SYSTEM={_sh_quote(vault_file('system_audit_report_md'))}",
        f"export VAULT_FILE_AUDIT_VAULT={_sh_quote(vault_file('vault_audit_report_md'))}",
        f"export VAULT_FIN_CHART_DAILY_CATEGORIES_PNG={_sh_quote(finance_sub('chart_daily_categories_png'))}",
    ]
    try:
        from shared.vault_layout import knowledge_subdir

        lines.append(f"export VAULT_REL_KNOWLEDGE={_sh_quote(knowledge_subdir())}")
    except Exception:
        lines.append("export VAULT_REL_KNOWLEDGE='Knowledge'")
    return "\n".join(lines) + "\n"
