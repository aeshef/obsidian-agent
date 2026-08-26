"""Planning LLM domain helpers (parse_task, reviews, recommendations, goals mapping)."""
from __future__ import annotations

import json
import logging
import re
import traceback
from typing import Dict, List, Optional, Protocol

from planning_bot.core.pdmsg import pdmsg

from .config import (
    BACKLOG_COLUMN,
    BLOCKED_COLUMN,
    DEFAULT_CATEGORY,
    DEFAULT_PRIORITY,
    IN_WORK_COLUMN,
    POSTPONED_COLUMN,
    WAITING_DATE_COLUMN,
)
from .llm_context import lctx
from .llm_params import planning_llm_temperature
from .settings import get_config_path, load_prompt

logger = logging.getLogger(__name__)


class _ChatClient(Protocol):
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float | None = None,
        max_retries: int = 3,
    ) -> str: ...


def strip_telegram_markdown(text: str) -> str:
    """Strip Markdown that Telegram reply keyboards cannot render."""
    if not text:
        return text
    out = text.replace("**", "").replace("__", "")
    out = re.sub(r"(?m)^#{1,6}\s+", "", out)
    out = out.replace("`", "")
    return out


def append_mac_iphone_context_for_recommendations(context: str) -> str:
    """Append Mac + iPhone focus snapshots to recommendations context."""
    parts: List[str] = []

    try:
        from planning_bot.core.config import CONTEXT_MAC_DIR, CONTEXT_TODAY_JSON
        from planning_bot.services.context_parser import (
            format_for_llm,
            get_today_snapshot,
            load_chat_snapshot_from_json,
        )

        snap = load_chat_snapshot_from_json(CONTEXT_TODAY_JSON)
        if not snap:
            snap = get_today_snapshot(CONTEXT_MAC_DIR, logging_window_only=True)
        mac_today = format_for_llm(snap)
        if mac_today:
            parts.append(mac_today)
    except Exception as e:
        logger.debug("recommendations mac today: %s", e)

    try:
        from planning_bot.core.config import IPHONE_CONTEXT_DIR
        from planning_bot.services.iphone_context_parser import (
            format_for_llm as iphone_format_for_llm,
            get_latest_snapshot,
        )

        iphone_snap = get_latest_snapshot(IPHONE_CONTEXT_DIR)
        iphone_str = iphone_format_for_llm(iphone_snap)
        if iphone_str:
            parts.append(iphone_str)
    except Exception as e:
        logger.debug("recommendations iphone latest: %s", e)

    try:
        from planning_bot.core.config import CONTEXT_MAC_DIR, CONTEXT_WEEK_JSON
        from planning_bot.services.context_parser import format_week_stats_for_llm, get_snapshots

        mac_snaps = get_snapshots(CONTEXT_MAC_DIR, days=7, logging_window_only=True)
        if not mac_snaps and CONTEXT_WEEK_JSON.exists():
            raw = json.loads(CONTEXT_WEEK_JSON.read_text(encoding="utf-8"))
            mac_snaps = raw.get("snapshots") or []
        mac_week = format_week_stats_for_llm(mac_snaps)
        if mac_week:
            parts.append(mac_week)
    except Exception as e:
        logger.debug("recommendations mac week: %s", e)

    try:
        from planning_bot.core.config import IPHONE_CONTEXT_DIR
        from planning_bot.services.iphone_context_parser import (
            format_week_stats_for_llm as iphone_week_stats,
            get_week_snapshots,
        )

        iphone_snaps = get_week_snapshots(IPHONE_CONTEXT_DIR)
        iphone_week = iphone_week_stats(iphone_snaps)
        if iphone_week:
            parts.append(iphone_week)
    except Exception as e:
        logger.debug("recommendations iphone week: %s", e)

    if not parts:
        return context
    block = lctx("mac_iphone_header") + "\n\n".join(parts)
    return context + "\n\n" + block


class PlanningLLMDomainMixin:
    """Domain LLM operations mixed into DeepSeekClient."""

    def parse_task(self: _ChatClient, user_message: str, context: Optional[Dict] = None) -> Dict[str, str]:
        logger.info("parse_task input: %s", user_message[:100])

        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "task_parsing")
            logger.debug("task_parsing prompt len=%d", len(system_prompt))

            context_text = ""
            if context:
                if context.get("recent_tasks"):
                    context_text += lctx("parse_recent_tasks")
                    for task in context["recent_tasks"][:5]:
                        context_text += f"- {task}\n"
                    logger.debug("parse_task recent_tasks=%d", len(context.get("recent_tasks", [])))
                if context.get("goals"):
                    context_text += lctx("parse_goals")
                    for goal in context["goals"][:5]:
                        context_text += f"- {goal}\n"
                    logger.debug("parse_task goals=%d", len(context.get("goals", [])))
                if context.get("upcoming_events"):
                    context_text += f"\n\n{context['upcoming_events']}"
                    logger.debug("parse_task upcoming_events=yes")

            messages = [
                {"role": "system", "content": system_prompt + context_text},
                {"role": "user", "content": user_message},
            ]

            response = self.chat(
                messages,
                temperature=planning_llm_temperature("task_parsing"),
            )
            logger.debug("parse_task llm response len=%d", len(response))

            try:
                original_response = response
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0].strip()

                result = json.loads(response)
                parsed = {
                    "title": result.get("title", user_message),
                    "category": result.get("category", DEFAULT_CATEGORY),
                    "priority": result.get("priority", DEFAULT_PRIORITY),
                }
                logger.info("parse_task result: %s", parsed)
                return parsed
            except json.JSONDecodeError as e:
                logger.warning("parse_task json decode failed: %s", e)
                logger.debug("parse_task raw llm: %s", original_response[:500])
                return {
                    "title": user_message,
                    "category": DEFAULT_CATEGORY,
                    "priority": DEFAULT_PRIORITY,
                }
        except Exception as e:
            logger.error("parse_task failed: %s", e)
            logger.error("traceback:\n%s", traceback.format_exc())
            raise

    def generate_weekly_review(
        self: _ChatClient,
        weekly_stats: Dict,
        goals: List[str],
        quarterly_focus: List[str],
        goals_context: Optional[str] = None,
        previous_reflections: Optional[str] = None,
        weekly_logs: Optional[str] = None,
        weekly_moves: Optional[List[Dict]] = None,
        calendar_events: Optional[str] = None,
    ) -> str:
        logger.info("generate_weekly_review start")
        logger.debug("weekly_stats=%s goals=%d quarterly=%d", weekly_stats, len(goals), len(quarterly_focus))

        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "weekly_review")
            logger.debug("weekly_review prompt len=%d", len(system_prompt))

            from datetime import datetime, timedelta

            now = datetime.now()
            today = now.date()
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)
            week_end = week_start + timedelta(days=6)
            week_start_str = week_start.strftime("%d.%m")
            week_end_str = week_end.strftime("%d.%m")
            formed_at_str = today.strftime("%d.%m.%Y")
            weekday_names = lctx("weekday_names").strip().split("|")
            weekday_str = weekday_names[today.weekday()]
            time_str = now.strftime("%H:%M")

            completed = weekly_stats.get("completed", 0)
            completed_list = weekly_stats.get("completed_this_week_list") or []
            backlog_only = weekly_stats.get("backlog_only", 0)
            in_work = weekly_stats.get("in_work", 0)
            total_active = weekly_stats.get("total_active", weekly_stats.get("backlog_size", 0))
            in_blocked = weekly_stats.get("in_blocked", 0)
            in_waiting_date = weekly_stats.get("in_waiting_date", 0)
            in_postponed = weekly_stats.get("in_postponed", 0)
            num_moves = len(weekly_moves) if weekly_moves else 0

            completed_titles_block = ""
            if completed_list:
                lines = []
                for t in completed_list[:80]:
                    title = (t.get("title") or "").strip()
                    if not title:
                        continue
                    cat = t.get("category") or ""
                    lines.append(f"- {title}" + (f" ({cat})" if cat else ""))
                completed_titles_block = lctx("weekly_completed_header") + "\n".join(lines)
                if len(completed_list) > 80:
                    completed_titles_block += lctx("weekly_completed_more").format(extra=len(completed_list) - 80)

            stats_text = lctx("weekly_review_stats").format(
                week_start_str=week_start_str,
                week_end_str=week_end_str,
                weekday_str=weekday_str,
                formed_at_str=formed_at_str,
                time_str=time_str,
                backlog_col=BACKLOG_COLUMN,
                waiting_col=WAITING_DATE_COLUMN,
                postponed_col=POSTPONED_COLUMN,
                in_work_col=IN_WORK_COLUMN,
                blocked_col=BLOCKED_COLUMN,
                backlog_only=backlog_only,
                in_waiting_date=in_waiting_date,
                in_postponed=in_postponed,
                in_work=in_work,
                in_blocked=in_blocked,
                total_active=total_active,
                completed=completed,
                num_moves=num_moves,
                by_category=weekly_stats.get("by_category", {}),
                by_priority=weekly_stats.get("by_priority", {}),
                completed_titles_block=completed_titles_block,
            )

            goals_text = lctx("weekly_goals_header") + "\n".join(f"- {goal}" for goal in goals[:10])
            focus_text = lctx("weekly_focus_header") + "\n".join(f"- {goal}" for goal in quarterly_focus[:10])
            context_text = stats_text + goals_text + focus_text

            if calendar_events:
                context_text += lctx("weekly_calendar_header") + calendar_events.strip()
                logger.debug("weekly_review calendar chars=%d", len(calendar_events))

            try:
                from planning_bot.core.config import CONTEXT_MAC_DIR, CONTEXT_WEEK_JSON
                from planning_bot.services.context_parser import format_week_stats_for_llm, get_snapshots

                mac_snaps = get_snapshots(CONTEXT_MAC_DIR, days=7, logging_window_only=True)
                if not mac_snaps and CONTEXT_WEEK_JSON.exists():
                    raw = json.loads(CONTEXT_WEEK_JSON.read_text(encoding="utf-8"))
                    mac_snaps = raw.get("snapshots") or []
                mac_week = format_week_stats_for_llm(mac_snaps)
                if mac_week:
                    context_text += "\n\n" + mac_week
                    logger.debug("weekly_review mac snapshots=%d", len(mac_snaps))
            except Exception as exc:
                logger.debug("weekly_review mac context: %s", exc)

            try:
                from planning_bot.core.config import IPHONE_CONTEXT_DIR
                from planning_bot.services.iphone_context_parser import (
                    format_week_stats_for_llm as iphone_week_stats,
                    get_week_snapshots,
                )

                iphone_snaps = get_week_snapshots(IPHONE_CONTEXT_DIR)
                iphone_week = iphone_week_stats(iphone_snaps)
                if iphone_week:
                    context_text += "\n\n" + iphone_week
                    logger.debug("weekly_review iphone snapshots=%d", len(iphone_snaps))
            except Exception as exc:
                logger.debug("weekly_review iphone context: %s", exc)

            if weekly_moves:
                max_moves = 400
                moves_block = lctx("weekly_moves_header")
                for ev in weekly_moves[:max_moves]:
                    moves_block += (
                        f"- {ev.get('timestamp', '')} | \"{ev.get('title', '')}\" | "
                        f"{ev.get('from', '')} → {ev.get('to', '')}\n"
                    )
                if len(weekly_moves) > max_moves:
                    moves_block += lctx("weekly_moves_more").format(
                        extra=len(weekly_moves) - max_moves, total=len(weekly_moves)
                    )
                context_text += moves_block
                logger.debug("weekly_review moves=%d", len(weekly_moves))

            if goals_context:
                context_text += lctx("weekly_goals_ctx") + goals_context
                logger.debug("weekly_review goals_context chars=%d", len(goals_context))

            if previous_reflections:
                context_text += lctx("weekly_reflections_ctx") + previous_reflections[:1000]
                logger.debug("weekly_review previous_reflections chars=%d", len(previous_reflections))

            if weekly_logs:
                context_text += lctx("weekly_logs_ctx") + weekly_logs
                logger.debug("weekly_review weekly_logs chars=%d", len(weekly_logs))

            user_content = lctx("weekly_user_prefix") + context_text
            logger.info(
                "weekly_review context: system=%d calendar=%s goals=%s reflections=%s logs=%s user=%d",
                len(system_prompt),
                "yes" if calendar_events else "no",
                "yes" if goals_context else "no",
                "yes" if previous_reflections else "no",
                "yes" if weekly_logs else "no",
                len(user_content),
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            review = self.chat(
                messages,
                temperature=planning_llm_temperature("weekly_review"),
            )
            logger.info("weekly_review done len=%d", len(review))
            return review
        except Exception as e:
            logger.error("generate_weekly_review failed: %s", e)
            logger.error("traceback:\n%s", traceback.format_exc())
            raise

    def generate_recommendations(
        self: _ChatClient,
        tasks: List[Dict],
        goals: List[str],
        weekly_stats: Dict,
        goals_context: Optional[str] = None,
        identity_summary: Optional[str] = None,
        weekly_logs: Optional[str] = None,
        tasks_mapping: Optional[Dict] = None,
        tasks_history: Optional[Dict[str, str]] = None,
        calendar_context: Optional[str] = None,
    ) -> str:
        from datetime import datetime, timezone, timedelta

        logger.info("generate_recommendations tasks=%d", len(tasks))
        _months_ru = ("",) + tuple(lctx("months_genitive").strip().split("|"))

        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "recommendations")

            try:
                from shared.tz import get_tz

                local_tz = get_tz()
            except Exception:
                from shared.constants import timezone_name
                from zoneinfo import ZoneInfo

                try:
                    local_tz = ZoneInfo(timezone_name())
                except Exception:
                    local_tz = timezone.utc
            now_local = datetime.now(local_tz)
            current_time_msk = now_local.strftime("%H:%M")  # legacy prompt slot name
            anchor_date = now_local.date()
            current_date_iso = anchor_date.isoformat()
            current_date_ru = f"{anchor_date.day} {_months_ru[anchor_date.month]} {anchor_date.year}"
            day_of_week = now_local.strftime("%A")
            day_names_ru = {
                k: v
                for k, v in zip(
                    "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split(),
                    lctx("weekday_names").strip().split("|"),
                )
            }
            day_of_week_ru = day_names_ru.get(day_of_week, day_of_week)
            is_weekend = lctx("weekend_label") if now_local.weekday() >= 5 else lctx("weekday_label")

            from shared.constants import timezone_name as _tz_name

            system_prompt = system_prompt.format(
                current_time_msk=current_time_msk,
                day_of_week=day_of_week_ru,
                is_weekend=is_weekend,
                current_date_iso=current_date_iso,
                current_date_ru=current_date_ru,
                tz=_tz_name(),
            )

            logger.debug("recommendations prompt len=%d", len(system_prompt))
            logger.debug(
                "recommendations anchor: time=%s date=%s day=%s %s",
                current_time_msk,
                current_date_iso,
                day_of_week_ru,
                is_weekend,
            )

            tasks_text: list[str] = []
            in_work_tasks: list[dict] = []
            backlog_tasks: list[dict] = []

            logger.debug("recommendations sample tasks (first 5 of %d)", len(tasks))
            for idx, t in enumerate(tasks[:5], 1):
                logger.debug(
                    "  %d title=%r column=%r id=%r",
                    idx,
                    (t.get("title", "") or "")[:50],
                    t.get("column", "None"),
                    t.get("task_id", ""),
                )

            for t in tasks:
                task_dict = {
                    "task": t,
                    "column": t.get("column", BACKLOG_COLUMN),
                    "title": t.get("title", ""),
                    "category": t.get("category", ""),
                    "priority": t.get("priority", ""),
                    "created_date": t.get("created_date", ""),
                    "deadline": t.get("deadline"),
                    "task_id": t.get("task_id"),
                }
                column = t.get("column") or BACKLOG_COLUMN
                if column == IN_WORK_COLUMN:
                    in_work_tasks.append(task_dict)
                else:
                    backlog_tasks.append(task_dict)

            logger.info("recommendations buckets: in_work=%d backlog=%d", len(in_work_tasks), len(backlog_tasks))

            if in_work_tasks:
                tasks_text.append(lctx("rec_tasks_in_work_header"))
                for td in in_work_tasks:
                    task_line = f"- {td['title']}"
                    task_line += lctx("rec_task_meta").format(category=td["category"], priority=td["priority"])
                    if td["created_date"]:
                        task_line += lctx("rec_task_created").format(created=td["created_date"])
                    if td.get("deadline"):
                        task_line += lctx("rec_task_deadline").format(deadline=td["deadline"])
                    if tasks_history and td["title"] in tasks_history:
                        task_line += lctx("rec_task_history").format(history=tasks_history[td["title"]])
                    task_id = td["task_id"]
                    if tasks_mapping and task_id and task_id in tasks_mapping:
                        related_goals = tasks_mapping[task_id]
                        if related_goals:
                            goals_text = ", ".join([g.get("text", "")[:40] for g in related_goals[:2]])
                            task_line += lctx("rec_task_goals").format(goals=goals_text)
                    tasks_text.append(task_line)
                tasks_text.append("")

            if backlog_tasks:
                tasks_text.append(lctx("rec_tasks_backlog_header"))
                for td in backlog_tasks:
                    task_line = f"- {td['title']}"
                    task_line += lctx("rec_task_meta").format(category=td["category"], priority=td["priority"])
                    if td["created_date"]:
                        task_line += lctx("rec_task_created").format(created=td["created_date"])
                    if td.get("deadline"):
                        task_line += lctx("rec_task_deadline").format(deadline=td["deadline"])
                    if tasks_history and td["title"] in tasks_history:
                        task_line += lctx("rec_task_history").format(history=tasks_history[td["title"]])
                    task_id = td["task_id"]
                    if tasks_mapping and task_id and task_id in tasks_mapping:
                        related_goals = tasks_mapping[task_id]
                        if related_goals:
                            goals_text = ", ".join([g.get("text", "")[:40] for g in related_goals[:2]])
                            task_line += lctx("rec_task_goals").format(goals=goals_text)
                    tasks_text.append(task_line)

            tasks_text_str = "\n".join(tasks_text)
            logger.debug("recommendations tasks block len=%d preview=%r", len(tasks_text_str), tasks_text_str[:500])

            stats_summary = lctx("rec_stats_summary").format(
                total=len(tasks), in_work=len(in_work_tasks), backlog=len(backlog_tasks)
            )
            context = lctx("rec_context_header").format(
                stats_summary=stats_summary,
                tasks_text_str=tasks_text_str,
                weekly_stats=weekly_stats,
                goals=", ".join(goals[:5]),
            )

            if goals_context:
                context += lctx("rec_goals_ctx") + goals_context
            if identity_summary:
                context += lctx("rec_identity_ctx") + identity_summary[:500]
            if weekly_logs:
                context += lctx("rec_weekly_logs") + weekly_logs
            if calendar_context:
                context += lctx("rec_calendar_ctx") + calendar_context

            context = append_mac_iphone_context_for_recommendations(context)
            anchor_hint = lctx("rec_anchor_hint").format(
                current_date_ru=current_date_ru,
                current_date_iso=current_date_iso,
                current_time_msk=current_time_msk,
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": anchor_hint + lctx("rec_user_suffix") + context},
            ]

            recommendations = self.chat(
                messages,
                temperature=planning_llm_temperature("recommendations"),
            )
            recommendations = strip_telegram_markdown((recommendations or "").strip())
            logger.info("generate_recommendations done len=%d", len(recommendations))
            return recommendations
        except Exception as e:
            logger.error("generate_recommendations failed: %s", e)
            logger.error("traceback:\n%s", traceback.format_exc())
            raise

    def map_task_to_goals(self: _ChatClient, task_title: str, task_category: str, goals_list: List[Dict]) -> Dict:
        logger.info("map_task_to_goals title=%r", task_title[:50])

        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "goals_mapping")

            goals_text = lctx("goals_list_header")
            for goal in goals_list:
                goal_id = goal.get("id", "")
                goal_text = goal.get("text", "")
                goal_quarter = goal.get("quarter", "")
                goal_category = goal.get("category", "")
                goal_priority = goal.get("priority", "")
                goal_context = goal.get("context", "")
                goal_include = goal.get("include", "")
                goal_exclude = goal.get("exclude", "")
                goal_success = goal.get("success", "")
                goals_text += lctx("goals_list_line").format(
                    goal_id=goal_id,
                    goal_text=goal_text,
                    goal_category=goal_category,
                    goal_quarter=goal_quarter,
                    goal_priority=goal_priority,
                    goal_context=goal_context,
                    goal_include=goal_include,
                    goal_exclude=goal_exclude,
                    goal_success=goal_success,
                )

            messages = [
                {"role": "system", "content": system_prompt + lctx("goals_map_system_suffix") + goals_text},
                {"role": "user", "content": lctx("goals_map_user").format(task_title=task_title, task_category=task_category)},
            ]

            response = self.chat(
                messages,
                temperature=planning_llm_temperature("goals_mapping"),
            )

            try:
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0].strip()

                result = json.loads(response)
                raw_ids = result.get("goal_ids", [])
                if not isinstance(raw_ids, list):
                    raw_ids = []
                valid_ids = {g.get("id") for g in goals_list if g.get("id")}
                goal_ids = [gid for gid in raw_ids if isinstance(gid, str) and gid in valid_ids][:1]
                return {
                    "goal_ids": goal_ids,
                    "reasoning": result.get("reasoning", ""),
                }
            except json.JSONDecodeError as e:
                logger.error("map_task_to_goals json decode failed: %s response=%r", e, response[:200])
                return {"goal_ids": [], "reasoning": lctx("parse_error_reasoning")}

        except Exception as e:
            logger.error("map_task_to_goals failed: %s", e)
            logger.error("traceback:\n%s", traceback.format_exc())
            return {"goal_ids": [], "reasoning": lctx("map_error_reasoning").format(error=e)}
