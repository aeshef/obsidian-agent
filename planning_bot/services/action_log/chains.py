"""Action log event-chain formatters for chat / agent history."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from planning_bot.core.pdmsg import pdmsg

_log = logging.getLogger(__name__)


class ActionLogChains:
    def get_events_chain_for_calendar_day(self, day: date) -> str:
        'Operation implementation.'
        return self.get_recent_events_chain(
            hours=None,
            max_events=None,
            calendar_day=day,
        )

    def _format_event_chain(
        self,
        matched: List[Dict],
        display: List[Dict],
        *,
        requested_start: Optional[datetime],
        requested_end: Optional[datetime],
        title: str,
        extras: List[str],
    ) -> str:
        from planning_bot.services.activity_log_query import format_task_event_dump

        body = format_task_event_dump(
            display,
            matched,
            requested_start=requested_start,
            requested_end=requested_end,
            title=title,
            extras=extras,
            slice_kind="tail" if len(display) < len(matched) else "all",
        )
        footer = pdmsg("auto_6123f35713")
        return body + "\n\n" + footer if footer else body

    def get_events_chain_for_date_range(
        self,
        from_date: date,
        to_date: date,
        *,
        limit: int = 0,
    ) -> str:
        """Task event chain for inclusive calendar-day range."""
        from shared.agent.platform_config import platform_int

        _SAFETY_MAX = platform_int(
            "planning_action_log", "safety_max_events", default=10000
        )
        matched, n_raw = self.query_task_events(
            from_date=from_date,
            to_date=to_date,
            limit=0,
            safety_max=_SAFETY_MAX,
        )
        if not matched:
            return pdmsg(
                "agent_action_log_range_empty",
                start=from_date.isoformat(),
                end=to_date.isoformat(),
            )
        display = matched[-limit:] if limit and limit > 0 and len(matched) > limit else matched
        extras = [
            pdmsg(
                "agent_action_log_chain_period",
                start=from_date.isoformat(),
                end=to_date.isoformat(),
                count=len(display),
                raw=n_raw,
            )
        ]
        return self._format_event_chain(
            matched,
            display,
            requested_start=datetime.combine(from_date, datetime.min.time()),
            requested_end=datetime.combine(to_date, datetime.max.time()).replace(microsecond=0),
            title=pdmsg("auto_6b600fff04"),
            extras=extras,
        )

    def get_recent_events_chain(
        self,
        hours: Optional[float] = None,
        max_events: Optional[int] = None,
        calendar_day: Optional[date] = None,
    ) -> str:
        'Operation implementation.'
        from shared.agent.platform_config import platform_float, platform_int

        _SAFETY_MAX = platform_int(
            "planning_action_log", "safety_max_events", default=10000
        )

        if calendar_day is not None:
            hours = 0.0
            max_events = max_events if max_events is not None else 0
        else:
            if hours is None:
                hours = platform_float(
                    "planning_action_log",
                    "chain_hours",
                    env="PLANNING_CHAT_LOG_CHAIN_HOURS",
                    default=48.0,
                )
            if max_events is None:
                max_events = platform_int(
                    "planning_action_log",
                    "chain_max_events",
                    env="PLANNING_CHAT_LOG_CHAIN_MAX_EVENTS",
                    default=0,
                )

        now = datetime.now()
        cutoff = now - timedelta(hours=hours) if calendar_day is None else None

        if calendar_day is not None:
            matched, n_raw = self.query_task_events(
                calendar_day=calendar_day,
                limit=0,
                safety_max=_SAFETY_MAX,
            )
        else:
            matched, n_raw = self.query_task_events(
                hours=hours,
                limit=0,
                safety_max=_SAFETY_MAX,
            )

        lim = max_events if max_events and max_events > 0 else 0
        display = matched[-lim:] if lim and len(matched) > lim else matched
        truncated = n_raw > len(matched) or len(display) < len(matched)

        _log.debug(
            "get_recent_events_chain: window=%.1fh raw_events=%d after_cap=%d truncated=%s",
            hours,
            n_raw,
            len(display),
            truncated,
        )

        if not matched:
            if calendar_day is not None:
                return (
                    pdmsg("auto_cee6069b3a", _p1=calendar_day.isoformat(), _p3=self.logs_dir)
                )
            return pdmsg(
                "history_hours_empty",
                hours=f"{hours:.0f}",
                logs_dir=self.logs_dir,
            )

        if calendar_day is not None:
            header = pdmsg("auto_6b600fff04")
            extras = [
                pdmsg("auto_76473f45d3", _p1=calendar_day.isoformat(), _p3=len(display), _p5=n_raw)
            ]
            req_start = datetime.combine(calendar_day, datetime.min.time())
            req_end = datetime.combine(calendar_day, datetime.max.time()).replace(microsecond=0)
        else:
            header = pdmsg("auto_5a1c921e96")
            extras = [
                pdmsg(
                    "history_window_line",
                    start=cutoff.strftime("%Y-%m-%d %H:%M"),
                    end=now.strftime("%Y-%m-%d %H:%M"),
                    hours=f"{hours:.0f}",
                    count=len(display),
                    raw=n_raw,
                )
            ]
            req_start = cutoff
            req_end = now

        return self._format_event_chain(
            matched,
            display,
            requested_start=req_start,
            requested_end=req_end,
            title=header,
            extras=extras,
        )

