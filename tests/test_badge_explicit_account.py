from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.badge import resolve_account_from_user_text, transaction_uses_badge


@pytest.mark.asyncio
async def test_resolve_account_from_user_text():
    parsed = {"type": "expense", "amount": 650, "account": "Meal Badge"}
    source = "650 lunch cafe main bank"

    class _Acc:
        def __init__(self, name: str):
            self.name = name

    mock_user = MagicMock(id=1)

    with patch("bot.handlers.badge.BadgeTracker") as BT, patch(
        "bot.handlers.badge.AsyncSessionLocal"
    ) as sess_cls, patch("bot.handlers.badge.get_badge_config", return_value={}):
        BT.return_value.account_name = "Meal Badge"

        session = AsyncMock()
        sess_cls.return_value.__aenter__.return_value = session
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user)),
                MagicMock(
                    scalars=MagicMock(
                        return_value=MagicMock(
                            all=lambda: [_Acc("Main Bank"), _Acc("Meal Badge")]
                        )
                    )
                ),
            ]
        )

        assert await resolve_account_from_user_text(parsed, telegram_id=42, source_text=source)
        assert parsed["account"] == "Main Bank"
        assert parsed["_force_non_badge"] is True
        assert transaction_uses_badge(parsed, badge_mode=True) is False
