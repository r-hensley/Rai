import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from cogs.questions import Questions


class TestQuestions(unittest.IsolatedAsyncioTestCase):
    async def test_list_removes_stale_question_from_its_own_channel(self):
        response = SimpleNamespace(status=404, reason="Not Found")
        not_found = discord.NotFound(response, {"code": 10008, "message": "Unknown Message"})
        author = SimpleNamespace(id=20, mention="<@20>", name="asker")
        current_channel = SimpleNamespace(id=30, name="current", mention="<#30>")
        stale_channel = SimpleNamespace(id=31, name="stale", mention="<#31>")
        current_message = SimpleNamespace(
            id=40,
            content="Current question",
            author=author,
            channel=current_channel,
            jump_url="https://discord.com/channels/10/30/40",
            attachments=[],
        )
        current_channel.fetch_message = AsyncMock(return_value=current_message)
        stale_channel.fetch_message = AsyncMock(side_effect=not_found)
        stale_log_message = SimpleNamespace(delete=AsyncMock())
        log_channel = SimpleNamespace(id=50, fetch_message=AsyncMock(return_value=stale_log_message))
        current_question = {"question_message": 40, "log_message": 60, "thread": None}
        stale_question = {"question_message": 41, "log_message": 61, "thread": None}
        config = {
            "30": {"questions": {"1": current_question}, "log_channel": 50},
            "31": {"questions": {"1": stale_question}, "log_channel": 50},
        }
        channels = {30: current_channel, 31: stale_channel, 50: log_channel}
        guild = SimpleNamespace(
            id=10,
            get_channel_or_thread=lambda channel_id: channels.get(channel_id),
        )
        ctx = SimpleNamespace(guild=guild, channel=current_channel)
        questions = Questions.__new__(Questions)
        questions.bot = SimpleNamespace(db={"questions": {"10": config}})

        with patch("cogs.questions.utils.safe_send", AsyncMock()):
            await Questions.question_list.callback(questions, ctx, target_channel=log_channel)

        self.assertIs(config["30"]["questions"]["1"], current_question)
        self.assertEqual(config["31"]["questions"], {})
        stale_log_message.delete.assert_awaited_once()

    async def test_add_question_tolerates_cleanup_during_log_refresh(self):
        config = {"questions": {}, "log_channel": 50, "threads": False}
        log_channel = SimpleNamespace(id=50)
        guild = SimpleNamespace(
            id=10,
            get_channel_or_thread=lambda channel_id: log_channel if channel_id == 50 else None,
        )
        author = SimpleNamespace(id=20, mention="<@20>", name="asker")
        channel = SimpleNamespace(id=30, guild=guild, mention="<#30>")
        target_message = SimpleNamespace(
            id=40,
            content="A question",
            author=author,
            channel=channel,
            jump_url="https://discord.com/channels/10/30/40",
            add_reaction=AsyncMock(),
        )
        ctx = SimpleNamespace(
            guild=guild,
            channel=channel,
            author=author,
            message=SimpleNamespace(attachments=[]),
        )
        questions = Questions.__new__(Questions)
        questions.bot = SimpleNamespace(db={"questions": {"10": {"30": config}}})
        questions.get_color_from_name = lambda _ctx: 0x123456
        questions._delete_log = AsyncMock()

        async def remove_question(_ctx):
            config["questions"].pop("1")

        questions._post_log = remove_question
        safe_send = AsyncMock(return_value=SimpleNamespace(id=60))

        with patch("cogs.questions.utils.safe_send", safe_send):
            await questions.add_question(ctx, target_message)

        self.assertEqual(config["questions"], {})
        target_message.add_reaction.assert_not_awaited()
