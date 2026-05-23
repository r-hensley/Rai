import asyncio
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs.events import Events


class FakeHTTPException(discord.HTTPException):
    def __init__(self, code: int, status: int = 429):
        self.code = code
        self.status = status
        self.text = "fake http exception"
        self.response = Mock()
        self.args = (self.text,)


def test_edit_message_with_old_message_fallback_resends_old_messages():
    message = Mock()
    replacement = Mock()
    message.edit = AsyncMock(side_effect=FakeHTTPException(30046))
    message.delete = AsyncMock()
    message.channel = Mock()
    message.channel.send = AsyncMock(return_value=replacement)

    result = asyncio.run(Events.edit_message_with_old_message_fallback(message, content="updated"))

    message.edit.assert_awaited_once_with(content="updated")
    message.delete.assert_awaited_once()
    message.channel.send.assert_awaited_once_with(content="updated")
    assert result is replacement


def test_edit_message_with_old_message_fallback_reraises_other_http_errors():
    message = Mock()
    message.edit = AsyncMock(side_effect=FakeHTTPException(50035, status=400))
    message.delete = AsyncMock()
    message.channel = Mock()
    message.channel.send = AsyncMock()

    with pytest.raises(FakeHTTPException):
        asyncio.run(Events.edit_message_with_old_message_fallback(message, content="updated"))

    message.delete.assert_not_called()
    message.channel.send.assert_not_called()
