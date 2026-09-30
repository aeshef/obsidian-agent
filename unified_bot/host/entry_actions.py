"""Small navigation shell; user content always goes through the unified agent."""
from shared.i18n import msg


async def handle_entry_action(message, text):
    from unified_bot.host.keyboards import root_keyboard, more_keyboard
    if text == msg("host", "more_button"):
        await message.answer(msg("host", "more_hint"), reply_markup=more_keyboard())
        return True
    for button, hint in (("capture_button", "capture_hint"), ("find_button", "find_hint")):
        if text == msg("host", button):
            await message.answer(msg("host", hint), reply_markup=root_keyboard())
            return True
    if text == msg("host", "data_status_button"):
        from shared.agent.data_status import render_status
        await message.answer(render_status(), parse_mode=None, reply_markup=root_keyboard())
        return True
    return False
