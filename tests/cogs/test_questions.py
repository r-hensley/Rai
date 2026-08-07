import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.questions import Questions


class TestQuestions(unittest.IsolatedAsyncioTestCase):
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
