"""Finance dashboard helpers (re-export split modules)."""
from bot.services.dashboard.assemble import (
    HERO_META_PLACEHOLDER,
    assemble_dashboard_markdown,
    fill_summary_hero,
    write_dashboard_md,
)
from bot.services.dashboard.badge import build_badge_section
from bot.services.dashboard.build import build_arg_parser, run_build
from bot.services.dashboard.charts import plot_lines_png, plot_stacked_bar_categories_png
from bot.services.dashboard.data import (
    acc_balance,
    ensure_account_balance_snapshots_table,
    external_rub_non_portfolio_total,
    load_data,
    parse_datetime,
)
from bot.services.dashboard.filters import (
    is_badge_expense,
    is_excluded_category,
    resolve_badge_account_name,
    resolve_badge_category,
    resolve_exclude_spending_categories,
    skip_badge_account,
)
from bot.services.dashboard.format import fmt_num, pie_with_pct, safe_comment
from bot.services.dashboard.series import (
    accumulate_daily_flow,
    accumulate_daily_spending,
    accumulate_weekly_flow,
    accumulate_weekly_regular_spending,
    ordered_top_categories,
    stacked_category_series,
    top_cats_by_total,
)
from bot.services.dashboard.windows import (
    chart_window_int,
    day_range,
    format_day_labels,
    series_floor,
    spending_axis_end,
    week_range,
)

from bot.services.dashboard.build import build_arg_parser, run_build

__all__ = [
    "HERO_META_PLACEHOLDER",
    "acc_balance",
    "accumulate_daily_flow",
    "accumulate_daily_spending",
    "accumulate_weekly_flow",
    "accumulate_weekly_regular_spending",
    "assemble_dashboard_markdown",
    "build_arg_parser",
    "build_badge_section",
    "chart_window_int",
    "day_range",
    "ensure_account_balance_snapshots_table",
    "external_rub_non_portfolio_total",
    "fill_summary_hero",
    "fmt_num",
    "format_day_labels",
    "is_badge_expense",
    "is_excluded_category",
    "load_data",
    "ordered_top_categories",
    "parse_datetime",
    "pie_with_pct",
    "plot_lines_png",
    "plot_stacked_bar_categories_png",
    "resolve_badge_account_name",
    "resolve_badge_category",
    "resolve_exclude_spending_categories",
    "run_build",
    "safe_comment",
    "series_floor",
    "skip_badge_account",
    "spending_axis_end",
    "stacked_category_series",
    "top_cats_by_total",
    "week_range",
    "write_dashboard_md",
]
