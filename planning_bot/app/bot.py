"""Planning bot services container (handlers receive `planning` via middleware)."""
from __future__ import annotations
from planning_bot.core.pdmsg import pdmsg
import logging
from pathlib import Path
from aiogram.fsm.storage.base import BaseStorage
from shared.logging_setup import add_rotating_file_handler, setup_logging
from planning_bot.app.chatid_store import load_chat_id
from planning_bot.app.handlers import (
    callbacks,
    commands,
    daily_checkin,
    menus,
    recommendations,
    reflection,
    tasks,
    voice,
)
from planning_bot.core.config import ACTION_LOGS_DIR, CHAT_ID_FILE, LOG_DIR
from planning_bot.core.llm import DeepSeekClient
from planning_bot.core.settings import get_config_path
from planning_bot.services.action_logger import ActionLogger
from planning_bot.services.goals import GoalsManager
from planning_bot.services.goals_analyzer import GoalsAnalyzer
from planning_bot.services.goals_mapper import GoalsMapper
from planning_bot.services.kanban import KanbanBoard
from planning_bot.services.kanban_monitor import KanbanMonitor
from planning_bot.services.reflection import ReflectionManager
logger = logging.getLogger(__name__)

def configure_logging() -> None:
    log_dir = LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(logging.DEBUG)
    add_rotating_file_handler(log_dir, filename='bot.log', max_bytes=10 * 1024 * 1024, backup_count=5)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logger.info('=' * 50)
    logger.info(pdmsg("auto_0a4f9871d3"))  # log
    logger.info('=' * 50)

class PlanningBot:
    """Facade wiring handlers and services for the planning Telegram bot."""
    start = commands.start
    cmd_reset_context = commands.cmd_reset_context
    handle_text_message = commands.handle_text_message
    handle_chat_message = commands.handle_chat_message
    handle_voice_message = voice.handle_voice_message
    button_callback = callbacks.button_callback
    process_task_message = tasks.process_task_message
    show_tasks_by_status = tasks.show_tasks_by_status
    show_tasks = tasks.show_tasks
    show_statistics = tasks.show_statistics
    show_tasks_menu = menus.show_tasks_menu
    show_categories_menu = menus.show_categories_menu
    show_priorities_menu = menus.show_priorities_menu
    show_statuses_menu = menus.show_statuses_menu
    show_routines_menu = menus.show_routines_menu
    show_routines_statistics = menus.show_routines_statistics
    show_pending_routines = menus.show_pending_routines
    show_goals_progress = menus.show_goals_progress
    send_morning_brief = menus.send_morning_brief
    send_morning_routine_reminder = menus.send_morning_routine_reminder
    send_evening_routine_reminder = menus.send_evening_routine_reminder
    send_daily_checkin_prompt = menus.send_daily_checkin_prompt
    start_daily_checkin = daily_checkin.start_daily_checkin
    send_goals_alerts = menus.send_goals_alerts
    send_deadlines_alerts = menus.send_deadlines_alerts
    send_stuck_alerts = menus.send_stuck_alerts
    get_recommendations = recommendations.get_recommendations
    get_routines_recommendations = recommendations.get_routines_recommendations
    start_reflection = reflection.start_reflection
    handle_reflection_response = reflection.handle_reflection_response
    schedule_weekly_review = reflection.schedule_weekly_review

    def __init__(self) -> None:
        self.llm = DeepSeekClient()
        self.kanban = KanbanBoard()
        self.goals_manager = GoalsManager()
        self.logger = ActionLogger(logs_dir=ACTION_LOGS_DIR)
        self.reflection_manager = ReflectionManager()
        self.kanban_monitor = KanbanMonitor()
        self.goals_mapper = GoalsMapper()
        self.goals_analyzer = GoalsAnalyzer()
        self._bot_dir = Path(__file__).resolve().parent.parent
        self.chat_id_file = CHAT_ID_FILE
        self.chat_id = load_chat_id(self.chat_id_file)
        self.pending_tasks: dict = {}
        self._fsm_storage: BaseStorage | None = None
        self.config_path = get_config_path()

    def bind_fsm(self, storage: BaseStorage) -> None:
        self._fsm_storage = storage

    @property
    def fsm_storage(self) -> BaseStorage:
        if self._fsm_storage is None:
            raise RuntimeError('FSM storage not bound — call bind_fsm() from main()')
        return self._fsm_storage