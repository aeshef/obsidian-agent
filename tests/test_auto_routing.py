"""MessageWithText proxy lives under host.message_proxy (auto_routing removed)."""
from __future__ import annotations

from shared.telegram.host.message_proxy import MessageWithText


def test_message_with_text_hides_voice():
    class _Msg:
        voice = object()
        audio = object()
        chat = type("C", (), {"id": 1})()

        def __getattr__(self, name):
            raise AttributeError(name)

    proxy = MessageWithText(_Msg(), "hello")
    assert proxy.text == "hello"
    assert proxy.voice is None
    assert proxy.audio is None
    assert proxy.chat.id == 1
