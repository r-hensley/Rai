import unittest
from unittest.mock import AsyncMock, mock_open, patch

import aiohttp

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
    async def test_searchcompare_displays_unavailable_separately_from_zero(self):
        search = AsyncMock(side_effect=[{"searchInformation": {"totalResults": "0"}},
                                        {"error": {"message": "Search unavailable"}}])
        send = AsyncMock()
        questions = Questions(make_bot())
        term = "猫 & 犬"
        with patch("builtins.open", mock_open(read_data="test-key\n")), \
                patch("cogs.questions.utils.aiohttp_get_json", search), \
                patch("cogs.questions.utils.safe_send", send), \
                patch.object(questions, "get_massif_results", AsyncMock(return_value={
                    "hits": 35, "hits_limited": False,
                })):
            await Questions.searchcompare.callback(questions, make_context(), "site:example.com", term)

        description = send.await_args.kwargs["embed"].description
        self.assertIn("): 約0件\n", description)
        self.assertIn("): Unavailable\n", description)
        self.assertIn("): 35\n", description)
        self.assertEqual(search.await_args_list[0].kwargs["params"]["exactTerms"], term)
        self.assertEqual(search.await_args_list[0].kwargs["params"]["siteSearch"], "example.com")
        self.assertNotIn("test-key", description)

    async def test_google_results_handles_invalid_and_failed_responses(self):
        with patch("builtins.open", mock_open(read_data="test-key")):
            for result in (None, [], {"searchInformation": []},
                           {"searchInformation": {"totalResults": "invalid"}},
                           aiohttp.ClientConnectionError(), TimeoutError(), ValueError()):
                with self.subTest(result=result):
                    with patch("cogs.questions.utils.aiohttp_get_json", AsyncMock(side_effect=[result])):
                        self.assertIsNone(await Questions.get_number_google_results(None, "engine", "term"))

    async def test_add_question_releases_number_when_log_send_returns_none(self):
        channel = make_channel(channel_id=30)
        log_channel = make_channel(channel_id=50)
        guild = make_guild(guild_id=10, channels=[channel, log_channel])
        author = make_member(member_id=20, guild=guild)
        target = make_message(content="A question", author=author, channel=channel)
        ctx = make_context(guild=guild, channel=channel, author=author, message=target)
        config = {"questions": {}, "log_channel": log_channel.id, "threads": False}
        questions = Questions(make_bot(db={"questions": {"10": {"30": config}}}))
        questions.get_color_from_name = lambda _ctx: 0x123456
        send = AsyncMock(return_value=None)

        with patch("cogs.questions.utils.safe_send", send), \
                patch.object(questions, "_delete_log", AsyncMock()) as refresh:
            await questions.add_question(ctx, target)

        self.assertEqual(config["questions"], {})
        self.assertIs(send.await_args_list[0].args[0], log_channel)
        self.assertIn("wasn't saved", send.await_args.args[1])
        refresh.assert_not_awaited()
        target.add_reaction.assert_not_awaited()

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
