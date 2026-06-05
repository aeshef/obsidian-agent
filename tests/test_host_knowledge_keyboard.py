from knowledge_bot.app import kb_labels as kb_lbl
from shared.telegram.host.keyboards import knowledge_keyboard


def test_knowledge_keyboard_has_bulk_and_query():
    kb = knowledge_keyboard(bulk_active=False)
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert kb_lbl.bulk_on() in labels
    assert kb_lbl.query_button() in labels

    kb_on = knowledge_keyboard(bulk_active=True)
    labels_on = {btn.text for row in kb_on.keyboard for btn in row}
    assert kb_lbl.bulk_off() in labels_on
