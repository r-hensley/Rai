import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from cogs.logger import Logger, _audit_entry_starts_active_timeout
from tests.discord_fakes import discord_not_found, make_bot, make_channel, make_guild, make_thread


class _GuardedQueue:
    def __init__(self, oldest_created_at: datetime):
        self._oldest = SimpleNamespace(created_at=oldest_created_at)
        self.find_calls = 0

    def __bool__(self):
        return True

    def __getitem__(self, index: int):
        if index != 0:
            raise IndexError(index)
        return self._oldest

    def find(self, *_args, **_kwargs):
        self.find_calls += 1
        return []


class TestLogger(unittest.IsolatedAsyncioTestCase):
    def make_raw_edit(self, *, cached=True):
        guild = make_guild(guild_id=123456789012345678)
        logging_channel = make_channel(channel_id=345678901234567890, guild=guild)
        source = make_thread(thread_id=234567890123456789)
        if cached:
            guild.threads.append(source)
        guild.fetch_channel = AsyncMock(return_value=source)
        source.fetch_message = AsyncMock(return_value=SimpleNamespace(content="edited text"))
        old_message = SimpleNamespace(content="old text", to_discord_message=Mock())
        queue = _GuardedQueue(datetime.now(timezone.utc) - timedelta(minutes=5))
        queue.find = Mock(return_value=[old_message])
        logger = Logger.__new__(Logger)
        logger.bot = make_bot(
            guilds=[guild],
            db={"edits": {str(guild.id): {"enable": True, "channel": logging_channel.id}}},
            message_queue=queue, cached_messages=[], bot_message_queue=None,
        )
        logger.log_edit_event = AsyncMock()
        now = datetime.now(timezone.utc)
        payload = Mock(
            spec=discord.RawMessageUpdateEvent,
            message_id=discord.utils.time_snowflake(now - timedelta(minutes=1)),
            channel_id=source.id, guild_id=guild.id,
            data={"edited_timestamp": now.isoformat()},
        )
        return logger, payload, guild, source, logging_channel, old_message

    async def test_raw_edit_uses_cached_thread(self):
        logger, payload, guild, source, logging_channel, old_message = self.make_raw_edit()

        await logger.on_raw_message_edit(payload)

        guild.fetch_channel.assert_not_awaited()
        source.fetch_message.assert_awaited_once_with(payload.message_id)
        logger.log_edit_event.assert_awaited_once()
        self.assertIs(logger.log_edit_event.await_args.args[0], old_message.to_discord_message.return_value)
        self.assertIs(logger.log_edit_event.await_args.args[3], logging_channel)

    async def test_raw_edit_fetches_uncached_thread_and_logs_message(self):
        logger, payload, guild, source, logging_channel, old_message = self.make_raw_edit(cached=False)

        await logger.on_raw_message_edit(payload)

        guild.fetch_channel.assert_awaited_once_with(source.id)
        source.fetch_message.assert_awaited_once_with(payload.message_id)
        logger.log_edit_event.assert_awaited_once()
        self.assertIs(logger.log_edit_event.await_args.args[1], source.fetch_message.return_value)
        self.assertIs(logger.log_edit_event.await_args.args[3], logging_channel)

    async def test_raw_edit_skips_unavailable_channel_or_message(self):
        for stage in ("channel", "message"):
            for status in (403, 404):
                with self.subTest(stage=stage, status=status):
                    logger, payload, guild, source, _, _ = self.make_raw_edit(cached=False)
                    if status == 404:
                        error = discord_not_found()
                    else:
                        error = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Missing Access")
                    operation = guild.fetch_channel if stage == "channel" else source.fetch_message
                    operation.side_effect = error

                    await logger.on_raw_message_edit(payload)

                    logger.log_edit_event.assert_not_awaited()
                    if stage == "channel":
                        source.fetch_message.assert_not_awaited()

    async def test_raw_edit_skips_missing_guild(self):
        logger, payload, guild, source, _, _ = self.make_raw_edit()
        logger.bot.get_guild = Mock(return_value=None)

        await logger.on_raw_message_edit(payload)

        guild.fetch_channel.assert_not_awaited()
        source.fetch_message.assert_not_awaited()
        logger.log_edit_event.assert_not_awaited()

    def test_timeout_audit_entry_accepts_expired_previous_timeout(self):
        now = datetime(2026, 9, 1, 1, 59, 32, tzinfo=timezone.utc)
        entry = SimpleNamespace(
            before=SimpleNamespace(
                timed_out_until=datetime(2026, 8, 17, 20, 42, 47, tzinfo=timezone.utc),
            ),
            after=SimpleNamespace(
                timed_out_until=datetime(2026, 9, 1, 2, 9, 32, tzinfo=timezone.utc),
            ),
        )

        self.assertTrue(_audit_entry_starts_active_timeout(entry, now))

    def test_timeout_audit_entry_rejects_active_previous_timeout(self):
        now = datetime(2026, 9, 1, 1, 59, 32, tzinfo=timezone.utc)
        entry = SimpleNamespace(
            before=SimpleNamespace(
                timed_out_until=datetime(2026, 9, 1, 2, 4, 32, tzinfo=timezone.utc),
            ),
            after=SimpleNamespace(
                timed_out_until=datetime(2026, 9, 1, 2, 9, 32, tzinfo=timezone.utc),
            ),
        )

        self.assertFalse(_audit_entry_starts_active_timeout(entry, now))

    def test_timeout_audit_entry_rejects_timeout_removal(self):
        now = datetime(2026, 9, 1, 1, 59, 32, tzinfo=timezone.utc)
        entry = SimpleNamespace(
            before=SimpleNamespace(
                timed_out_until=datetime(2026, 9, 1, 2, 4, 32, tzinfo=timezone.utc),
            ),
            after=SimpleNamespace(timed_out_until=None),
        )

        self.assertFalse(_audit_entry_starts_active_timeout(entry, now))

    def test_timeout_audit_entry_rejects_unrelated_member_update(self):
        now = datetime(2026, 9, 1, 1, 59, 32, tzinfo=timezone.utc)
        entry = SimpleNamespace(before=SimpleNamespace(), after=SimpleNamespace())

        self.assertFalse(_audit_entry_starts_active_timeout(entry, now))

    async def test_voice_log_rate_limit_starts_channel_cooldown(self):
        logger = Logger.__new__(Logger)
        logger.voice_log_cooldowns = {}
        channel = make_channel(channel_id=345678901234567890)
        response = SimpleNamespace(status=429, reason="Too Many Requests")
        error = discord.HTTPException(response, {"code": 0, "message": "You are being rate limited."})
        safe_send = AsyncMock(side_effect=error)

        with patch("cogs.logger.utils.safe_send", safe_send):
            await logger._send_voice_log(channel, discord.Embed())
            await logger._send_voice_log(channel, discord.Embed())

        self.assertEqual(safe_send.await_count, 1)
        self.assertIn(channel.id, logger.voice_log_cooldowns)

    async def test_raw_delete_skips_queue_scan_for_messages_older_than_queue_window(self):
        guild_id = 123456789012345678
        source_channel_id = 234567890123456789
        logging_channel_id = 345678901234567890

        guild = make_guild(guild_id=guild_id)
        logging_channel = make_channel(
            channel_id=logging_channel_id,
            guild=guild,
        )
        queue = _GuardedQueue(oldest_created_at=datetime.now(timezone.utc) - timedelta(minutes=5))
        bot = make_bot(
            db={
                "deletes": {
                    str(guild_id): {
                        "enable": True,
                        "channel": logging_channel.id,
                    },
                },
                "edits": {},
            },
            channels=[logging_channel],
            message_queue=queue,
            cached_messages=[],
            bot_message_queue=None,
        )

        logger = Logger.__new__(Logger)
        logger.bot = bot
        logger.delete_log_queue = {}

        old_timestamp = datetime.now(timezone.utc) - timedelta(days=30)
        old_message_id = discord.utils.time_snowflake(old_timestamp)
        payload = discord.RawMessageDeleteEvent(
            {
                "id": str(old_message_id),
                "channel_id": str(source_channel_id),
                "guild_id": str(guild_id),
            }
        )

        await logger.log_raw_payload(payload)

        self.assertEqual(queue.find_calls, 0)
        self.assertIn(logging_channel_id, logger.delete_log_queue)
        self.assertEqual(len(logger.delete_log_queue[logging_channel_id]), 1)
