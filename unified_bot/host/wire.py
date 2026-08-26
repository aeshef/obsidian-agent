"""Wire domain FSM routers into host dispatcher (no /start, no reply-menu — host owns those)."""
from __future__ import annotations

import logging

from aiogram import Dispatcher, F, Router
from aiogram.filters import BaseFilter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, Message

from planning_bot.app.states import ReflectionState

log = logging.getLogger("unified_bot.host.wire")


def include_finance_routers(dp: Dispatcher) -> None:
    """Finance FSM + inline callbacks. Reply buttons — via bot.reply_menu in host router."""
    from bot.handlers.badge import router as badge_router
    from bot.handlers.debts import router as debts_router
    from bot.handlers.integrations import router as integrations_router
    from bot.handlers.investments import router as investments_router
    from bot.handlers.planning import router as finance_planning_router
    from bot.handlers.recent import router as recent_router
    from bot.handlers.start import menu_callbacks_router
    from bot.handlers.summary import router as summary_router
    from bot.handlers.transactions import router as transactions_router
    from bot.handlers.transactions_confirm import router as transactions_confirm_router
    from bot.handlers.transfers import router as transfers_router

    for r in (
        menu_callbacks_router,
        integrations_router,
        transfers_router,
        debts_router,
        investments_router,
        recent_router,
        summary_router,
        finance_planning_router,
        badge_router,
        transactions_confirm_router,
        transactions_router,
    ):
        dp.include_router(r)


def include_knowledge_ingest(dp: Dispatcher) -> None:
    """Media ingest + inline save/type in knowledge mode (and when bulk upload active)."""
    try:
        from knowledge_bot.app.register_handlers import register_knowledge_callbacks
    except ImportError as e:
        log.error(
            "knowledge ingest DISABLED — photo/video in bulk mode not handled: %s. "
            "On VPS: finance_bot/.venv + pip install -r knowledge_bot/requirements.txt, restart unified.",
            e,
        )
        return

    from unified_bot.host.constants import DOMAIN_KNOWLEDGE, UI_MODE_AUTO
    from unified_bot.host.knowledge_dispatch import handle_knowledge_media

    register_knowledge_callbacks(dp)

    class _KnowledgeIngestFilter(BaseFilter):
        async def __call__(self, message: Message, state: FSMContext) -> bool:
            data = await state.get_data()
            uid = message.from_user.id if message.from_user else 0
            from knowledge_bot.app.state import activate_bulk_ingest, is_bulk_ingest

            if data.get("bulk_ingest"):
                activate_bulk_ingest(uid)
            if is_bulk_ingest(uid):
                return True
            cur = await state.get_state()
            if cur is not None:
                return False
            ui_mode = data.get("ui_mode", UI_MODE_AUTO)
            if message.voice:
                return ui_mode == DOMAIN_KNOWLEDGE
            if ui_mode in (DOMAIN_KNOWLEDGE, UI_MODE_AUTO):
                return True
            log.debug(
                "knowledge ingest skip uid=%s ui_mode=%s bulk=%s fsm=%s",
                uid,
                ui_mode,
                is_bulk_ingest(uid),
                cur,
            )
            return False

    filt = _KnowledgeIngestFilter()
    r = Router(name="knowledge_ingest")

    @r.message(
        filt,
        F.document | F.photo | F.video | F.video_note | F.audio | F.voice,
    )
    async def _kb_media(message: Message) -> None:
        await handle_knowledge_media(message)

    dp.include_router(r)


def include_planning_aux(dp: Dispatcher) -> None:
    from unified_bot.host.constants import DOMAIN_PLANNING, UI_MODE_AUTO

    class _PlanningMode(BaseFilter):
        async def __call__(self, message: Message, state: FSMContext) -> bool:
            data = await state.get_data()
            return data.get("ui_mode", UI_MODE_AUTO) == DOMAIN_PLANNING

    aux = Router(name="planning_aux")

    # Planning callback_data only — otherwise finance txn:* callbacks are silently swallowed
    _planning_cb = (
        F.data.startswith("confirm_task")
        | F.data.startswith("edit_task")
        | F.data.startswith("cancel_task")
        | F.data.startswith("chk:")
    )

    @aux.callback_query(_planning_cb)
    async def _cb(callback: CallbackQuery, state: FSMContext, planning=None):
        data = callback.data or ""
        if data.startswith("chk:"):
            from shared.capabilities.planning_gates import planning_daily_checkin_enabled

            if not planning_daily_checkin_enabled():
                from shared.i18n import msg

                await callback.answer(msg("finance", "connector_unavailable"), show_alert=True)
                return
            from planning_bot.app.handlers.daily_checkin import handle_checkin_callback

            await handle_checkin_callback(callback, state)
            return
        if planning is None:
            from shared.i18n import msg

            await callback.answer(msg("host", "planning_callback_unavailable"), show_alert=True)
            return
        await planning.button_callback(callback, state)

    @aux.message(_PlanningMode(), F.voice)
    async def _voice(message: Message, state: FSMContext, planning=None, agent_app=None):
        if planning is None:
            from shared.i18n import msg

            await message.answer(msg("host", "planning_unavailable_short"))
            return
        await planning.handle_voice_message(message, state, agent_app=agent_app)

    @aux.message(StateFilter(ReflectionState.waiting), F.text)
    async def _reflection(message: Message, state: FSMContext, planning=None):
        from shared.capabilities.planning_gates import planning_weekly_review_enabled

        if not planning_weekly_review_enabled():
            await state.clear()
            from shared.i18n import msg

            await message.answer(msg("finance", "connector_unavailable"))
            return
        if planning is None:
            from shared.i18n import msg

            await message.answer(msg("host", "planning_unavailable_short"))
            return
        await planning.handle_reflection_response(message, state)

    dp.include_router(aux)


def include_host_voice(dp: Dispatcher) -> None:
    """Voice in auto and finance modes — same routing as text."""
    from shared.agent.llm_classify import LLMClassificationError
    from shared.agent.platform_config import platform_int
    from shared.i18n import msg, msgf
    from unified_bot.host.constants import DOMAIN_FINANCE, UI_MODE_AUTO
    from shared.telegram.voice import safe_edit_status, transcribe_voice_message

    class _HostVoiceFilter(BaseFilter):
        async def __call__(self, message: Message, state: FSMContext) -> bool:
            if not message.voice:
                return False
            if await state.get_state() is not None:
                return False
            data = await state.get_data()
            ui_mode = data.get("ui_mode", UI_MODE_AUTO)
            return ui_mode in (UI_MODE_AUTO, DOMAIN_FINANCE)

    r = Router(name="host_voice")

    @r.message(_HostVoiceFilter(), F.voice)
    async def _host_voice(message: Message, state: FSMContext, agent_app) -> None:
        data = await state.get_data()
        ui_mode = data.get("ui_mode", UI_MODE_AUTO)
        preview_max = platform_int("telegram", "voice_preview_chars", default=400)
        status = await message.answer(msg("wire", "voice_transcribing"))
        try:
            text = await transcribe_voice_message(message)
            if not text:
                await safe_edit_status(status, msg("wire", "voice_failed"))
                return
            preview = text if len(text) <= preview_max else text[:preview_max] + "…"
            await safe_edit_status(status, msgf("wire", "voice_preview", preview=preview))
            log.info("host voice ui_mode=%s len=%d", ui_mode, len(text))

            from unified_bot.host.auto_dispatch import dispatch_auto_free_text

            # Same path as typed free text: txn/save gates → unified agent.
            await dispatch_auto_free_text(message, state, agent_app, text)
            # Don't leave ASR preview in history — agent answer is the one bubble.
            try:
                await status.delete()
            except Exception:
                pass
        except LLMClassificationError as e:
            log.error("host voice LLM routing failed: %s", e, exc_info=True)
            err = msgf("wire", "voice_llm_failed", error=e)
            await safe_edit_status(status, err[:preview_max])
        except Exception as e:
            log.error("host voice failed: %s", e, exc_info=True)
            err = msgf("wire", "voice_error", error=e)
            await safe_edit_status(status, err[:preview_max])

    dp.include_router(r)
