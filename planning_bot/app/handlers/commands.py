"""Command and text message handlers."""
from planning_bot.core.pdmsg import pdmsg
import logging
import traceback
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from shared.telegram.agent_delivery import deliver_agent_answer
from shared.telegram.messaging import send_long_message
from planning_bot.app import keyboards
from planning_bot.app.chatid_store import save_chat_id
from shared.agent.llm_classify import LLMClassificationError, classify_host_domain_llm, classify_planning_intent_llm, map_general_domain
logger = logging.getLogger(__name__)

async def start(self, message: Message, state: FSMContext):
    chat_id = message.chat.id
    if self.chat_id != chat_id:
        save_chat_id(self.chat_id_file, chat_id)
        self.chat_id = chat_id
        logger.info(pdmsg("auto_d115c89bf2"), chat_id)  # log
    welcome_text = pdmsg("auto_36b91eccd8")
    await message.answer(welcome_text, reply_markup=keyboards.get_main_keyboard())

async def cmd_reset_context(self, message: Message, state: FSMContext):
    from shared.memory import clear_history
    chat_id = message.chat.id
    clear_history(chat_id, 'planning')
    ok = True
    await state.clear()
    if ok:
        text = pdmsg("auto_1f1234de12")
    else:
        text = pdmsg("auto_ce717860c4")
    await message.answer(text, reply_markup=keyboards.get_main_keyboard())

async def handle_text_message(self, message: Message, state: FSMContext):
    try:
        user_message = message.text.strip()
        await process_user_text(self, message, state, user_message)
    except Exception as e:
        logger.error(pdmsg("auto_08b2df1cfd"), e)  # log
        logger.error('Traceback: %s', traceback.format_exc())
        await message.answer(pdmsg("auto_8ea5aae503"), reply_markup=keyboards.get_main_keyboard())

async def process_user_text(self, message: Message, state: FSMContext, user_message: str, agent_app=None):
    try:
        chat_id = message.chat.id
        logger.info(pdmsg("auto_b1e0a2e96e"), chat_id, user_message[:100])  # log
        from planning_bot.app.menu_dispatch import dispatch_planning_menu

        if await dispatch_planning_menu(self, message, state, user_message):
            return
        if agent_app is not None:
            routed = await _maybe_answer_other_domain(message, user_message, agent_app)
            if routed:
                return
        intent = await classify_planning_intent_llm(user_message)
        logger.info("Router intent for '%s': %s", user_message[:60], intent)
        if intent == 'task':
            from planning_bot.services.kanban_parse import is_substantive_task_text
            if not is_substantive_task_text(user_message):
                await message.answer(pdmsg("auto_e184960639"), reply_markup=keyboards.get_main_keyboard())
                return
            if agent_app is not None:
                await _answer_planning_agent(message, user_message, agent_app)
                return
            await tasks.process_task_message(self, message, user_message)
        elif agent_app is not None:
            await _answer_planning_agent(message, user_message, agent_app)
        else:
            await handle_chat_message(self, message, user_message)
    except LLMClassificationError as e:
        logger.error('LLM routing in process_user_text: %s', e, exc_info=True)
        await message.answer(pdmsg("auto_1bd726250e", e={e}), reply_markup=keyboards.get_main_keyboard())
    except Exception as e:
        logger.error(pdmsg("auto_7dbfc07fcf"), e)  # log
        logger.error('Traceback: %s', traceback.format_exc())
        await message.answer(pdmsg("auto_8ea5aae503"), reply_markup=keyboards.get_main_keyboard())

async def _answer_planning_agent(message: Message, user_message: str, agent_app) -> None:
    await deliver_agent_answer(message.bot, message.chat.id, agent_app, user_message, domain='planning', reply_markup=keyboards.get_main_keyboard())

async def _maybe_answer_other_domain(message: Message, user_message: str, agent_app) -> bool:
    """Planning bot module."""
    from shared.telegram_utils import strip_telegram_markdown
    enabled = [d for d in ('finance', 'planning', 'knowledge') if agent_app.has_domain(d)]
    dom = await classify_host_domain_llm(user_message, enabled=enabled or ['planning'], chat_id=message.chat.id, ui_mode='planning')
    name = map_general_domain(dom)
    if name in ('planning', 'general'):
        return False
    if not agent_app.has_domain(name):
        raise LLMClassificationError(f'cross-domain route: {name!r} not registered')
    await deliver_agent_answer(message.bot, message.chat.id, agent_app, user_message, domain=name, reply_markup=keyboards.get_main_keyboard())
    return True

async def handle_chat_message(self, message: Message, user_message: str):
    chat_id = message.chat.id
    try:
        from shared.agent.app import build_app
        from shared.llm import LLMClient
        from shared.telegram_utils import strip_telegram_markdown
        from planning_bot.app.agent_tools import PLANNING_DOMAIN, PlanningAdapter
        app = build_app(LLMClient(), PlanningAdapter(self))
        reply = await app.answer(PLANNING_DOMAIN, chat_id, user_message)
        await send_long_message(message.bot, chat_id, strip_telegram_markdown(reply), reply_markup=keyboards.get_main_keyboard())
    except LLMClassificationError as e:
        logger.error('LLM error in handle_chat_message: %s', e, exc_info=True)
        await message.answer(pdmsg("auto_1bd726250e", e={e}), reply_markup=keyboards.get_main_keyboard())
    except Exception as e:
        logger.error(pdmsg("auto_081837d14d"), e, traceback.format_exc())  # log
        await message.answer(pdmsg("auto_c57cc79aba"), reply_markup=keyboards.get_main_keyboard())