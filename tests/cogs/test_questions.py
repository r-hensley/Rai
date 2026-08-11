import unittest
from unittest.mock import AsyncMock, patch

from cogs.questions import Questions
from tests.discord_fakes import (
    discord_not_found,
    make_bot,
    make_channel,
    make_context,
    make_guild,
    make_member,
    make_message,
)


class TestQuestions(unittest.IsolatedAsyncioTestCase):
    async def test_list_removes_stale_question_from_its_own_channel(self):
        not_found = discord_not_found()
        current_channel = make_channel(channel_id=30, name="current")
        stale_channel = make_channel(
            channel_id=31,
            name="stale",
            fetch_message=AsyncMock(side_effect=not_found),
        )
        log_channel = make_channel(channel_id=50)
        guild = make_guild(
            guild_id=10,
            channels=[current_channel, stale_channel, log_channel],
        )
        author = make_member(member_id=20, name="asker", guild=guild)
        current_message = make_message(
            message_id=40,
            content="Current question",
            author=author,
            channel=current_channel,
            guild=guild,
        )
        current_channel.fetch_message = AsyncMock(return_value=current_message)
        stale_log_message = make_message(
            message_id=61,
            channel=log_channel,
            guild=guild,
        )
        log_channel.fetch_message = AsyncMock(return_value=stale_log_message)
        current_question = {"question_message": 40, "log_message": 60, "thread": None}
        stale_question = {"question_message": 41, "log_message": 61, "thread": None}
        config = {
            "30": {"questions": {"1": current_question}, "log_channel": 50},
            "31": {"questions": {"1": stale_question}, "log_channel": 50},
        }
        ctx = make_context(guild=guild, channel=current_channel, author=author)
        questions = Questions.__new__(Questions)
        questions.bot = make_bot(db={"questions": {"10": config}})

        with patch("cogs.questions.utils.safe_send", AsyncMock()):
            await Questions.question_list.callback(questions, ctx, target_channel=log_channel)

        self.assertIs(config["30"]["questions"]["1"], current_question)
        self.assertEqual(config["31"]["questions"], {})
        stale_log_message.delete.assert_awaited_once()

    async def test_add_question_tolerates_cleanup_during_log_refresh(self):
        config = {"questions": {}, "log_channel": 50, "threads": False}
        log_channel = make_channel(channel_id=50)
        channel = make_channel(channel_id=30)
        guild = make_guild(
            guild_id=10,
            channels=[channel, log_channel],
        )
        author = make_member(member_id=20, name="asker", guild=guild)
        target_message = make_message(
            message_id=40,
            content="A question",
            author=author,
            channel=channel,
            guild=guild,
        )
        command_message = make_message(
            message_id=41,
            author=author,
            channel=channel,
            guild=guild,
        )
        ctx = make_context(
            guild=guild,
            channel=channel,
            author=author,
            message=command_message,
        )
        questions = Questions.__new__(Questions)
        questions.bot = make_bot(db={"questions": {"10": {"30": config}}})
        questions.get_color_from_name = lambda _ctx: 0x123456
        questions._delete_log = AsyncMock()

        async def remove_question(_ctx):
            config["questions"].pop("1")

        questions._post_log = remove_question
        log_message = make_message(
            message_id=60,
            channel=log_channel,
            guild=guild,
        )
        safe_send = AsyncMock(return_value=log_message)

        with patch("cogs.questions.utils.safe_send", safe_send):
            await questions.add_question(ctx, target_message)

        self.assertEqual(config["questions"], {})
        target_message.add_reaction.assert_not_awaited()
