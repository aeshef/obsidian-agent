"""English docstring; user strings live in YAML configs."""
from __future__ import annotations

from shared.i18n import clear_messages_cache, msg
from unified_bot.host import labels as L


def test_host_labels_non_empty() -> None:
    clear_messages_cache()
    L.clear_label_cache()
    assert L.back_home()
    assert L.mode_finance()
    assert msg("host", "start_welcome")
    assert msg("agent", "no_answer")
