from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.ui import fmsg

from ..services.summary_generator import FinanceSummaryGenerator
from ..handlers.start import main_menu_inline

router = Router()


def summary_period_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=fmsg("summary_week"), callback_data="summary:week"),
                InlineKeyboardButton(text=fmsg("summary_month"), callback_data="summary:month"),
            ],
            [
                InlineKeyboardButton(text=fmsg("summary_back"), callback_data="action:menu"),
            ],
        ]
    )


@router.callback_query(F.data == "action:summary")
async def cmd_summary(callback: CallbackQuery) -> None:
    """Show period picker for summary."""
    text = fmsg("summary_period_prompt")
    kb = summary_period_kb()
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception as e:
        # Fallback to new message if edit fails
        import logging
        log = logging.getLogger("finance.summary")
        log.warning("Failed to edit message in cmd_summary: %s", e)
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("summary:"))
async def generate_summary(callback: CallbackQuery) -> None:
    """Generate summary for selected period."""
    period = callback.data.split(":")[-1]  # week or month
    
    await callback.message.edit_text(fmsg("summary_progress"))
    
    try:
        generator = FinanceSummaryGenerator()
        # Pass telegram_id; service resolves user_id
        summary = await generator.generate(callback.from_user.id, period)
        
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=fmsg("summary_back"), callback_data="action:menu")],
            ]
        )
        
        await callback.message.edit_text(summary, reply_markup=kb)
    except Exception as e:
        import logging
        log = logging.getLogger("finance.summary")
        log.error("Summary generation failed: %s", e, exc_info=True)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=fmsg("summary_back"), callback_data="action:menu")],
            ]
        )
        await callback.message.edit_text(fmsg("summary_error", error=e), reply_markup=kb)
    await callback.answer()
