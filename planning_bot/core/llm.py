"""DeepSeek API: retry and domain helpers (parse_task, weekly review, recommendations)."""
import re
import requests
import json
import logging
import traceback
from typing import Dict, List, Optional
from time import sleep

from shared.constants import deepseek_base_url
from shared.llm import LLMClient as _SharedLLMClient

from .config import DEEPSEEK_API_TOKEN, DEEPSEEK_API_URL, DEEPSEEK_MODEL
from .llm_params import planning_chat_timeout_sec, planning_llm_temperature
from .settings import load_prompt, get_config_path
from .llm_context import lctx
from .config import (
    BACKLOG_COLUMN,
    BLOCKED_COLUMN,
    DEFAULT_CATEGORY,
    DEFAULT_PRIORITY,
    IN_WORK_COLUMN,
    POSTPONED_COLUMN,
    WAITING_DATE_COLUMN,
)
from planning_bot.core.pdmsg import pdmsg

logger = logging.getLogger(__name__)


def _strip_telegram_markdown_facade(text: str) -> str:
    """  Markdown,    Telegram    (**  )."""
    if not text:
        return text
    out = text.replace("**", "").replace("__", "")
    out = re.sub(r"(?m)^#{1,6}\s+", "", out)
    out = out.replace("`", "")
    return out


def _append_mac_iphone_context_for_recommendations(context: str) -> str:
    """  ,    ()     (): Mac + iPhone."""
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
        logger.debug("recommendations Mac today: %s", e)

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
        logger.debug("recommendations iPhone latest: %s", e)

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
        logger.debug("recommendations Mac week: %s", e)

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
        logger.debug("recommendations iPhone week: %s", e)

    if not parts:
        return context
    block = lctx("mac_iphone_header") + "\n\n".join(parts)
    return context + "\n\n" + block


class APITimeoutError(Exception):
    """   - API"""
    pass


class DeepSeekClient:
    def __init__(self):
        if not DEEPSEEK_API_TOKEN:
            raise ValueError("DEEPSEEK_API_TOKEN is not set")
        self.api_token = DEEPSEEK_API_TOKEN
        self.api_url = DEEPSEEK_API_URL
        self.model = DEEPSEEK_MODEL
        self._transport = _SharedLLMClient(
            api_key=DEEPSEEK_API_TOKEN,
            base_url=deepseek_base_url(override=DEEPSEEK_API_URL),
            model=DEEPSEEK_MODEL,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float | None = None,
        max_retries: int = 3,
    ) -> str:
        if temperature is None:
            temperature = planning_llm_temperature("recommendations", 0.7)
        """   DeepSeek API  retry  ( — shared.llm)."""
        logger.info("DeepSeek API request")
        logger.debug("Model: %s, Temperature: %s, messages: %s", self.model, temperature, len(messages))

        for attempt in range(1, max_retries + 1):
            try:
                logger.info("DeepSeek retry %s/%s", attempt, max_retries)
                content = self._transport.chat_messages(
                    messages,
                    temperature=temperature,
                    timeout=planning_chat_timeout_sec(),
                    raise_on_error=True,
                )
                logger.info("DeepSeek API ok (%s chars)", len(content))
                logger.debug("Response preview: %s...", content[:200])
                return content

            except requests.exceptions.Timeout as e:
                logger.error("DeepSeek timeout attempt %s/%s", attempt, max_retries)
                logger.error(f"Timeout error: {str(e)}")
                logger.error(f"URL: {self.api_url}")
                if attempt < max_retries:
                    wait_time = attempt * 2
                    logger.info(f"⏳  {wait_time}   ...")
                    sleep(wait_time)
                else:
                    logger.error(f"❌   .  : {traceback.format_exc()}")
                    raise APITimeoutError(f"DeepSeek API timeout after {max_retries} attempts")
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"❌     {attempt}/{max_retries}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {str(e)}")
                logger.error(f"URL: {self.api_url}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response length: {len(e.response.text)} chars (body not logged)")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                
                if attempt < max_retries:
                    wait_time = attempt * 2
                    logger.info(f"⏳  {wait_time}   ...")
                    sleep(wait_time)
                else:
                    raise Exception(f"DeepSeek API request failed after {max_retries} attempts: {e}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"❌   JSON ")
                logger.error(f"Response length: {len(response.text) if 'response' in locals() else 0} chars (body not logged)")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                raise Exception(f"DeepSeek API JSON parse error: {e}")
                
            except Exception as e:
                logger.error(f"❌     {attempt}/{max_retries}")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {str(e)}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
                if attempt < max_retries:
                    wait_time = attempt * 2
                    logger.info(f"⏳  {wait_time}   ...")
                    sleep(wait_time)
                else:
                    raise Exception(f"Unexpected DeepSeek API error: {e}")

    def parse_task(self, user_message: str, context: Optional[Dict] = None) -> Dict[str, str]:
        """       LLM"""
        logger.info(f"🔍  : {user_message[:100]}...")
        
        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "task_parsing")
            logger.debug(f"     (: {len(system_prompt)} )")

            context_text = ""
            if context:
                if context.get("recent_tasks"):
                    context_text += lctx("parse_recent_tasks")
                    for task in context["recent_tasks"][:5]:
                        context_text += f"- {task}\n"
                    logger.debug(f" : {len(context.get('recent_tasks', []))}  ")
                if context.get("goals"):
                    context_text += lctx("parse_goals")
                    for goal in context["goals"][:5]:
                        context_text += f"- {goal}\n"
                    logger.debug(f" : {len(context.get('goals', []))} ")
                if context.get("upcoming_events"):
                    context_text += f"\n\n{context['upcoming_events']}"
                    logger.debug("     ")

            messages = [
                {"role": "system", "content": system_prompt + context_text},
                {"role": "user", "content": user_message}
            ]

            response = self.chat(
                messages,
                temperature=planning_llm_temperature("task_parsing", 0.3),
            )
            logger.debug(f"   LLM   (: {len(response)} )")
            
            #  JSON  
            try:
                #  markdown    
                original_response = response
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0].strip()
                
                result = json.loads(response)
                parsed = {
                    "title": result.get("title", user_message),
                    "category": result.get("category", DEFAULT_CATEGORY),
                    "priority": result.get("priority", DEFAULT_PRIORITY)
                }
                logger.info(f"✅  : {parsed}")
                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️    JSON : {e}")
                logger.debug(f" LLM: {original_response[:500]}")
                logger.info(f"  ")
                #    ,   
                return {
                    "title": user_message,
                    "category": DEFAULT_CATEGORY,
                    "priority": DEFAULT_PRIORITY
                }
        except Exception as e:
            logger.error(f"❌    : {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise

    def generate_weekly_review(
        self,
        weekly_stats: Dict,
        goals: List[str],
        quarterly_focus: List[str],
        goals_context: Optional[str] = None,
        previous_reflections: Optional[str] = None,
        weekly_logs: Optional[str] = None,
        weekly_moves: Optional[List[Dict]] = None,
        calendar_events: Optional[str] = None,
    ) -> str:
        """  """
        logger.info("📝   ")
        logger.debug(f": {weekly_stats}")
        logger.debug(f": {len(goals)},  : {len(quarterly_focus)}")
        
        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "weekly_review")
            logger.debug(f"     (: {len(system_prompt)} )")

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
                by_category=weekly_stats.get('by_category', {}),
                by_priority=weekly_stats.get('by_priority', {}),
                completed_titles_block=completed_titles_block,
            )

            goals_text = lctx("weekly_goals_header") + "\n".join(f"- {goal}" for goal in goals[:10])
            
            focus_text = lctx("weekly_focus_header") + "\n".join(f"- {goal}" for goal in quarterly_focus[:10])

            context_text = stats_text + goals_text + focus_text

            if calendar_events:
                context_text += (
                    lctx("weekly_calendar_header")
                    + calendar_events.strip()
                )
                logger.debug("  :  (%d )", len(calendar_events))

            # Mac-   (, -);  10:00–02:00
            try:
                import json

                from planning_bot.core.config import CONTEXT_MAC_DIR, CONTEXT_WEEK_JSON
                from planning_bot.services.context_parser import format_week_stats_for_llm, get_snapshots

                mac_snaps = get_snapshots(CONTEXT_MAC_DIR, days=7, logging_window_only=True)
                if not mac_snaps and CONTEXT_WEEK_JSON.exists():
                    raw = json.loads(CONTEXT_WEEK_JSON.read_text(encoding="utf-8"))
                    mac_snaps = raw.get("snapshots") or []
                mac_week = format_week_stats_for_llm(mac_snaps)
                if mac_week:
                    context_text += "\n\n" + mac_week
                    logger.debug(" Mac  : %d ", len(mac_snaps))
            except Exception as _e:
                logger.debug(" Mac   : %s", _e)

            # iPhone-   (, , )
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
                    logger.debug("iPhone-  : %d ", len(iphone_snaps))
            except Exception as _e:
                logger.debug("iPhone-   : %s", _e)

            if weekly_moves:
                max_moves = 400
                moves_block = lctx("weekly_moves_header")
                for ev in weekly_moves[:max_moves]:
                    moves_block += f"- {ev.get('timestamp', '')} | \"{ev.get('title', '')}\" | {ev.get('from', '')} → {ev.get('to', '')}\n"
                if len(weekly_moves) > max_moves:
                    moves_block += lctx("weekly_moves_more").format(extra=len(weekly_moves) - max_moves, total=len(weekly_moves))
                context_text += moves_block
                logger.debug(f"   : {len(weekly_moves)} ")

            if goals_context:
                context_text += lctx("weekly_goals_ctx") + goals_context
                logger.debug(f"   ({len(goals_context)} )")
            
            if previous_reflections:
                context_text += lctx("weekly_reflections_ctx") + previous_reflections[:1000]
                logger.debug(f"   ({len(previous_reflections)} )")
            
            if weekly_logs:
                context_text += lctx("weekly_logs_ctx") + weekly_logs
                logger.debug(f"   ({len(weekly_logs)} )")

            logger.debug(f"  : {len(context_text)} ")
            #  :      (    ,   —  «»  )
            user_content = lctx("weekly_user_prefix") + context_text
            logger.info(
                "review context: system=%d calendar=%s goals=%s reflections=%s logs=%s user=%d chars",
                len(system_prompt),
                "yes" if calendar_events else "no",
                "yes" if goals_context else "no",
                "yes" if previous_reflections else "no",
                "yes" if weekly_logs else "no",
                len(user_content),
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]

            review = self.chat(
                messages,
                temperature=planning_llm_temperature("weekly_review", 0.8),
            )
            logger.info(f"✅    (: {len(review)} )")
            return review
        except Exception as e:
            logger.error(f"❌     : {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise

    def generate_recommendations(
        self,
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
        """  """
        from datetime import datetime, timezone, timedelta

        logger.info(f"💡    {len(tasks)} ")

        _months_ru = ("",) + tuple(lctx("months_genitive").strip().split("|"))

        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "recommendations")

            try:
                from zoneinfo import ZoneInfo

                msk_tz = ZoneInfo("Europe/Moscow")
            except Exception:
                msk_tz = timezone(timedelta(hours=3))
            now_msk = datetime.now(msk_tz)
            current_time_msk = now_msk.strftime("%H:%M")
            anchor_date = now_msk.date()
            current_date_iso = anchor_date.isoformat()
            current_date_ru = (
                f"{anchor_date.day} {_months_ru[anchor_date.month]} {anchor_date.year}"
            )
            day_of_week = now_msk.strftime("%A")
            day_names_ru = {k: v for k, v in zip("Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split(), lctx("weekday_names").strip().split("|"))}
            day_of_week_ru = day_names_ru.get(day_of_week, day_of_week)
            is_weekend = lctx("weekend_label") if now_msk.weekday() >= 5 else lctx("weekday_label")
            
            #  ,       
            system_prompt = system_prompt.format(
                current_time_msk=current_time_msk,
                day_of_week=day_of_week_ru,
                is_weekend=is_weekend,
                current_date_iso=current_date_iso,
                current_date_ru=current_date_ru,
            )

            logger.debug(f"    (: {len(system_prompt)} )")
            logger.debug(
                "MSK time: %s, anchor date: %s, day: %s, %s",
                current_time_msk,
                current_date_iso,
                day_of_week_ru,
                is_weekend,
            )

            #      
            tasks_text = []
            #    
            in_work_tasks = []
            backlog_tasks = []
            
            #    
            logger.info(f"📋   : {len(tasks)}")
            for idx, t in enumerate(tasks[:5], 1):
                logger.info(f"  {idx}. '{t.get('title', '')[:50]}...' | : '{t.get('column', 'None')}' | ID: {t.get('task_id', '')}")
            
            for t in tasks:
                task_dict = {
                    "task": t,
                    "column": t.get('column', BACKLOG_COLUMN),
                    "title": t.get('title', ''),
                    "category": t.get('category', ''),
                    "priority": t.get('priority', ''),
                    "created_date": t.get('created_date', ''),
                    "deadline": t.get('deadline'),
                    "task_id": t.get('task_id')
                }
                
                column = t.get('column') or BACKLOG_COLUMN
                logger.debug(f" '{t.get('title', '')[:40]}...'  : '{column}'")
                
                if column == IN_WORK_COLUMN:
                    in_work_tasks.append(task_dict)
                    logger.info(f"✅   ' ': '{t.get('title', '')[:50]}...'")
                else:
                    backlog_tasks.append(task_dict)
            
            logger.info(f"📊 : {len(in_work_tasks)}  ' ', {len(backlog_tasks)}   ")
            
            #     " " ( )
            if in_work_tasks:
                tasks_text.append(lctx("rec_tasks_in_work_header"))
                for td in in_work_tasks:
                    t = td["task"]
                    task_line = f"- {td['title']}"
                    task_line += lctx("rec_task_meta").format(category=td['category'], priority=td['priority'])
                    if td['created_date']:
                        task_line += lctx("rec_task_created").format(created=td['created_date'])
                    if td.get('deadline'):
                        task_line += lctx("rec_task_deadline").format(deadline=td['deadline'])
                    
                    #   
                    if tasks_history and td['title'] in tasks_history:
                        task_line += lctx("rec_task_history").format(history=tasks_history[td['title']])
                    
                    #   
                    task_id = td['task_id']
                    if tasks_mapping and task_id and task_id in tasks_mapping:
                        related_goals = tasks_mapping[task_id]
                        if related_goals:
                            goals_text = ", ".join([g.get('text', '')[:40] for g in related_goals[:2]])
                            task_line += lctx("rec_task_goals").format(goals=goals_text)
                    
                    tasks_text.append(task_line)
                tasks_text.append("")
            
            #      
            if backlog_tasks:
                tasks_text.append(lctx("rec_tasks_backlog_header"))
                for td in backlog_tasks:
                    t = td["task"]
                    task_line = f"- {td['title']}"
                    task_line += lctx("rec_task_meta").format(category=td['category'], priority=td['priority'])
                    if td['created_date']:
                        task_line += lctx("rec_task_created").format(created=td['created_date'])
                    if td.get('deadline'):
                        task_line += lctx("rec_task_deadline").format(deadline=td['deadline'])
                    
                    #   
                    if tasks_history and td['title'] in tasks_history:
                        task_line += lctx("rec_task_history").format(history=tasks_history[td['title']])
                    
                    #   
                    task_id = td['task_id']
                    if tasks_mapping and task_id and task_id in tasks_mapping:
                        related_goals = tasks_mapping[task_id]
                        if related_goals:
                            goals_text = ", ".join([g.get('text', '')[:40] for g in related_goals[:2]])
                            task_line += lctx("rec_task_goals").format(goals=goals_text)
                    
                    tasks_text.append(task_line)
            
            tasks_text_str = "\n".join(tasks_text)
            
            # ,    
            logger.info(f"📝     ({len(tasks_text)} ):")
            logger.info(f"---    ---")
            logger.info(tasks_text_str[:500] + "..." if len(tasks_text_str) > 500 else tasks_text_str)
            logger.info(f"---    ---")
            
            #    
            stats_summary = lctx("rec_stats_summary").format(total=len(tasks), in_work=len(in_work_tasks), backlog=len(backlog_tasks))
            logger.info(f"📊   : {stats_summary.strip()}")

            context = lctx("rec_context_header").format(stats_summary=stats_summary, tasks_text_str=tasks_text_str, weekly_stats=weekly_stats, goals=", ".join(goals[:5]))
            
            if goals_context:
                context += lctx("rec_goals_ctx") + goals_context
                logger.debug(f"   ({len(goals_context)} )")
            
            if identity_summary:
                context += lctx("rec_identity_ctx") + identity_summary[:500]
                logger.debug(f"   ({len(identity_summary)} )")
            
            if weekly_logs:
                context += lctx("rec_weekly_logs") + weekly_logs
                logger.debug(f"   ({len(weekly_logs)} )")

            if calendar_context:
                context += lctx("rec_calendar_ctx") + calendar_context
                logger.debug("    ")

            context = _append_mac_iphone_context_for_recommendations(context)

            logger.debug(f"  : {len(context)} ")

            anchor_hint = lctx("rec_anchor_hint").format(current_date_ru=current_date_ru, current_date_iso=current_date_iso, current_time_msk=current_time_msk)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": anchor_hint + lctx("rec_user_suffix") + context},
            ]

            recommendations = self.chat(
                messages,
                temperature=planning_llm_temperature("recommendations", 0.7),
            )
            recommendations = _strip_telegram_markdown_facade((recommendations or "").strip())
            logger.info(f"✅   (: {len(recommendations)} )")
            return recommendations
        except Exception as e:
            logger.error(f"❌    : {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            raise
    
    def map_task_to_goals(self, task_title: str, task_category: str, goals_list: List[Dict]) -> Dict:
        """      LLM"""
        logger.info(f"🔗    : {task_title[:50]}...")
        
        try:
            config_path = get_config_path()
            system_prompt = load_prompt(config_path, "goals_mapping")
            
            #    —   ( )
            goals_text = lctx("goals_list_header")
            for goal in goals_list:
                goal_id = goal.get("id", "")
                goal_text = goal.get("text", "")
                goal_quarter = goal.get("quarter", "")
                goal_category = goal.get("category", "")
                goal_priority = goal.get("priority", "")
                goals_text += lctx("goals_list_line").format(goal_id=goal_id, goal_text=goal_text, goal_category=goal_category, goal_quarter=goal_quarter, goal_priority=goal_priority)
            
            messages = [
                {"role": "system", "content": system_prompt + lctx("goals_map_system_suffix") + goals_text},
                {"role": "user", "content": lctx("goals_map_user").format(task_title=task_title, task_category=task_category)}
            ]
            
            response = self.chat(
                messages,
                temperature=planning_llm_temperature("goals_mapping", 0.3),
            )
            
            #  JSON
            try:
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0].strip()
                
                result = json.loads(response)
                return {
                    "goal_ids": result.get("goal_ids", []),
                    "reasoning": result.get("reasoning", "")
                }
            except json.JSONDecodeError as e:
                logger.error(f"   JSON : {e}")
                logger.error(f" LLM: {response}")
                return {"goal_ids": [], "reasoning": lctx("parse_error_reasoning")}
                
        except Exception as e:
            logger.error(f"     : {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"goal_ids": [], "reasoning": lctx("map_error_reasoning").format(error=e)}
