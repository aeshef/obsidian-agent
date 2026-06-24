"""Host keyboard and mode labels — from config/messages.ru.yaml."""
from __future__ import annotations

from functools import lru_cache

from shared.i18n import msg


def back_home() -> str:
    return msg("host", "back_home")


def mode_auto() -> str:
    return msg("host", "mode_auto")


def mode_finance() -> str:
    return msg("host", "mode_finance")


def mode_planning() -> str:
    return msg("host", "mode_planning")


def mode_knowledge() -> str:
    return msg("host", "mode_knowledge")


def memory_menu() -> str:
    return msg("host", "memory_menu")


@lru_cache(maxsize=1)
def mode_button_labels() -> frozenset[str]:
    return frozenset(
        {
            back_home(),
            mode_auto(),
            mode_finance(),
            mode_planning(),
            mode_knowledge(),
            memory_menu(),
        }
    )


def clear_label_cache() -> None:
    mode_button_labels.cache_clear()
    from shared.telegram import navigation

    navigation.clear_navigation_cache()
