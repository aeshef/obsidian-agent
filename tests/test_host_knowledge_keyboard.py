from knowledge_bot.app import kb_labels as kb_lbl
from shared.agent import platform_config as pc
from shared.capabilities.profile import clear_capabilities_cache
from shared.capabilities.ui_bindings import clear_ui_bindings_cache
from shared.i18n import clear_messages_cache
from unified_bot.host.keyboards import knowledge_keyboard


def _enable_knowledge(monkeypatch) -> None:
    # CI has no capabilities.yaml → OSS starter (knowledge off). This test
    # asserts the knowledge reply keyboard when the module is enabled.
    monkeypatch.setenv("CAP_MODULE_KNOWLEDGE", "1")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()


def test_knowledge_keyboard_has_bulk_query_optional(monkeypatch, tmp_path):
    _enable_knowledge(monkeypatch)
    cfg = tmp_path / "platform.yaml"
    cfg.write_text("host_ui:\n  show_knowledge_query_button: 0\n", encoding="utf-8")
    monkeypatch.setattr(pc, "agent_config_dir", lambda: tmp_path)
    pc.load_platform_config.cache_clear()

    kb = knowledge_keyboard(bulk_active=False)
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert kb_lbl.bulk_on()
    assert kb_lbl.bulk_on() in labels
    assert kb_lbl.query_button() not in labels

    cfg.write_text("host_ui:\n  show_knowledge_query_button: 1\n", encoding="utf-8")
    pc.load_platform_config.cache_clear()
    kb_q = knowledge_keyboard(bulk_active=False)
    labels_q = {btn.text for row in kb_q.keyboard for btn in row}
    assert kb_lbl.query_button() in labels_q

    kb_on = knowledge_keyboard(bulk_active=True)
    labels_on = {btn.text for row in kb_on.keyboard for btn in row}
    assert kb_lbl.bulk_off() in labels_on
    pc.load_platform_config.cache_clear()
