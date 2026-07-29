from knowledge_bot.app import kb_labels as kb_lbl
from shared.capabilities.profile import clear_capabilities_cache
from shared.capabilities.ui_bindings import clear_ui_bindings_cache
from shared.i18n import clear_messages_cache
from shared.telegram.host.keyboards import knowledge_keyboard


def _enable_knowledge(monkeypatch) -> None:
    # CI has no capabilities.yaml → OSS starter (knowledge off). This test
    # asserts the knowledge reply keyboard when the module is enabled.
    monkeypatch.setenv("CAP_MODULE_KNOWLEDGE", "1")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()


def test_knowledge_keyboard_has_bulk_and_query(monkeypatch):
    _enable_knowledge(monkeypatch)
    kb = knowledge_keyboard(bulk_active=False)
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert kb_lbl.bulk_on()
    assert kb_lbl.bulk_on() in labels
    assert kb_lbl.query_button() in labels

    kb_on = knowledge_keyboard(bulk_active=True)
    labels_on = {btn.text for row in kb_on.keyboard for btn in row}
    assert kb_lbl.bulk_off() in labels_on
