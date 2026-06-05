"""Finance dashboard helpers (re-export split modules)."""
from bot.services.dashboard.badge import build_badge_section
from bot.services.dashboard.charts import plot_lines_png, plot_stacked_bar_categories_png
from bot.services.dashboard.data import (
    acc_balance,
    ensure_account_balance_snapshots_table,
    external_rub_non_portfolio_total,
    load_data,
    parse_datetime,
)
from bot.services.dashboard.format import fmt_num, pie_with_pct, safe_comment

__all__ = [
    "acc_balance",
    "build_badge_section",
    "ensure_account_balance_snapshots_table",
    "external_rub_non_portfolio_total",
    "fmt_num",
    "load_data",
    "parse_datetime",
    "pie_with_pct",
    "plot_lines_png",
    "plot_stacked_bar_categories_png",
    "safe_comment",
]
