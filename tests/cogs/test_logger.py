import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from cogs.logger import Logger, _audit_entry_starts_active_timeout
from tests.discord_fakes import make_bot, make_channel, make_guild


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
