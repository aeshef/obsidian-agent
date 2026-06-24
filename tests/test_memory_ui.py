"""Memory panel UI (buttons, plain profile, reset)."""
from __future__ import annotations


def test_profile_excerpt_plain_strips_markdown(tmp_path, monkeypatch):
    from shared.memory import config as mem_cfg

    repo = tmp_path / "repo"
    agent_dir = repo / "config" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "memory.yaml").write_text(
        'global_profile: "user_profile.md"\n'
        'insights:\n  profile_excerpt_max: 500\n',
        encoding="utf-8",
    )
    (agent_dir / "user_profile.md").write_text(
        "# Заголовок\n\n## Секция\n\nТекст с **жирным** и [ссылкой](https://x.test).\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(repo))
    mem_cfg.load_memory_config.cache_clear()

    plain = mem_cfg.read_global_profile_excerpt_plain()
    assert "#" not in plain
    assert "**" not in plain
    assert "жирным" in plain
    assert "ссылкой" in plain
    assert "https://" not in plain


def test_main_panel_is_read_first_with_clear_submenu(tmp_path, monkeypatch):
    from shared.memory.insights import InsightsStore, get_store
    from shared.telegram.memory_ui import build_memory_panel

    db = tmp_path / "memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    get_store.cache_clear()
    store = InsightsStore(db)
    store.record_candidates(1, "planning", ["тест кандидат"])

    text, markup = build_memory_panel(1)
    assert "Сводка" in text or "Summary" in text
    assert "/memory" not in text
    callbacks = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "mem:view:clear" in callbacks
    assert "mem:reset:yes:session" not in callbacks
    assert all(not cb.startswith("mem:reset:yes:") for cb in callbacks)


def test_clear_menu_requires_confirm_step(tmp_path, monkeypatch):
    from shared.memory.insights import InsightsStore, get_store
    from shared.telegram.memory_ui import build_clear_menu_panel, build_reset_confirm_panel

    db = tmp_path / "memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    get_store.cache_clear()
    InsightsStore(db)

    _, clear_kb = build_clear_menu_panel(2)
    clear_cbs = [
        btn.callback_data
        for row in clear_kb.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "mem:reset:ask:session" in clear_cbs
    assert "mem:view:main" in clear_cbs

    _, confirm_kb = build_reset_confirm_panel(2, "session")
    confirm_cbs = [
        btn.callback_data
        for row in confirm_kb.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "mem:reset:yes:session" in confirm_cbs
    assert "mem:view:main" in confirm_cbs


def test_apply_memory_reset_session(tmp_path, monkeypatch):
    from shared.memory import session as sess
    from shared.memory.insights import InsightsStore, get_store
    from shared.telegram.memory_ui import apply_memory_reset

    db = tmp_path / "memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    get_store.cache_clear()
    sess.append_turn(9, "finance", "user", "hi")
    store = InsightsStore(db)
    store.record_candidates(9, "finance", ["x"])
    store.confirm(1)

    lines = apply_memory_reset(9, "all")
    assert len(lines) == 3
    assert store.list_pending(9) == []
    assert store.read_confirmed_records(9, "finance") == []
    assert sess.get_history(9, "finance") == []
