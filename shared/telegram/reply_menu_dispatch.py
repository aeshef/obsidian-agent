"""Shared reply-keyboard dispatch: label → async handler."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Optional, TypeVar

T = TypeVar("T")
Handler = Callable[..., Awaitable[Any]]


async def dispatch_by_label_map(
    text: str,
    label_handlers: Mapping[str, Handler],
    *args: Any,
    normalize: Optional[Callable[[str], str]] = None,
    **kwargs: Any,
) -> bool:
    """Run handler when text matches a label key. True = consumed."""
    raw = (text or "").strip()
    if not raw:
        return False
    label = normalize(raw) if normalize else raw
    handler = label_handlers.get(label)
    if handler is None:
        return False
    await handler(*args, **kwargs)
    return True


async def dispatch_label_actions(
    text: str,
    label_actions: list[tuple[str, Callable[[], Awaitable[Any]]]],
) -> bool:
    """Match exact label and run zero-arg async action (planning menus)."""
    raw = (text or "").strip()
    if not raw:
        return False
    for label, action in label_actions:
        if raw == label:
            await action()
            return True
    return False
