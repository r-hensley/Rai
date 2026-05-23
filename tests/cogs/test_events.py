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


def test_edit_or_delete_temporary_notification_edits_latest_message():
    message = Mock()
    updated = Mock()
    message.id = 123
    message.edit = AsyncMock(return_value=updated)
    message.delete = AsyncMock()
    message.channel = Mock()
    message.channel.last_message_id = 123

    result = asyncio.run(Events.edit_or_delete_temporary_notification(message, content="updated"))

    message.edit.assert_awaited_once_with(content="updated")
    message.delete.assert_not_called()
    assert result is updated


def test_edit_or_delete_temporary_notification_deletes_non_latest_message_without_editing():
    message = Mock()
    message.id = 123
    message.edit = AsyncMock()
    message.delete = AsyncMock()
    message.channel = Mock()
    message.channel.last_message_id = 456

    result = asyncio.run(Events.edit_or_delete_temporary_notification(message, content="updated"))

    message.edit.assert_not_called()
    message.delete.assert_awaited_once()
    assert result is None


def test_edit_or_delete_temporary_notification_deletes_when_latest_message_is_too_old_to_edit():
    message = Mock()
    message.id = 123
    message.edit = AsyncMock(side_effect=FakeHTTPException(30046))
    message.delete = AsyncMock()
    message.channel = Mock()
    message.channel.last_message_id = 123

    result = asyncio.run(Events.edit_or_delete_temporary_notification(message, content="updated"))

    message.edit.assert_awaited_once_with(content="updated")
    message.delete.assert_awaited_once()
    assert result is None


def test_edit_or_delete_temporary_notification_reraises_other_http_errors():
    message = Mock()
    message.id = 123
    message.edit = AsyncMock(side_effect=FakeHTTPException(50035, status=400))
    message.delete = AsyncMock()
    message.channel = Mock()
    message.channel.last_message_id = 123

    with pytest.raises(FakeHTTPException):
        asyncio.run(Events.edit_or_delete_temporary_notification(message, content="updated"))

    message.delete.assert_not_called()
