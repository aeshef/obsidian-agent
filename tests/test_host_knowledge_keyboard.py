from shared.telegram.host.keyboards import knowledge_keyboard
from knowledge_bot.app.state import BTN_BULK_ON, BTN_QUERY


def test_knowledge_keyboard_has_bulk_and_query():
    kb = knowledge_keyboard(bulk_active=False)
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert BTN_BULK_ON in labels
    assert BTN_QUERY in labels

    kb_on = knowledge_keyboard(bulk_active=True)
    labels_on = {btn.text for row in kb_on.keyboard for btn in row}
    assert "📤 Прогрузка ВЫКЛ" in labels_on
