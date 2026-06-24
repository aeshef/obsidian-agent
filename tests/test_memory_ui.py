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


def test_build_memory_panel_has_reset_buttons_no_slash(tmp_path, monkeypatch):
    from shared.memory.insights import InsightsStore, get_store
    from shared.telegram.memory_ui import build_memory_panel

    db = tmp_path / "memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    get_store.cache_clear()
    store = InsightsStore(db)
    store.record_candidates(1, "planning", ["тест кандидат"])

    text, markup = build_memory_panel(1)
    assert "/memory" not in text
    assert "/reset_memory" not in text
    assert markup.inline_keyboard
    callbacks = [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert "mem:reset:session" in callbacks
    assert "mem:reset:all" in callbacks


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
