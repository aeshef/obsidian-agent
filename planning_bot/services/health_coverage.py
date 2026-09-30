"""Latest actual measurement per group, for source status reports."""
from shared.agent.platform_config import platform_int

def health_coverage():
    from planning_bot.core.config import IPHONE_CONTEXT_DIR
    from planning_bot.services.iphone_context_parser import get_snapshots
    from planning_bot.services.snapshot_query import latest_per_calendar_day
    from planning_bot.services.health_backfill import groups
    days=platform_int("data_status", "coverage_days", default=90)
    daily=latest_per_calendar_day(get_snapshots(IPHONE_CONTEXT_DIR, days=days))
    return {group:max((str(day) for day,row in daily.items() if any(row.get(field) is not None for field in fields)),default=None)
            for group,fields in groups().items()}


