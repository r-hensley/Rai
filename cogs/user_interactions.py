"""Record outbound user-to-user social events for later feature engineering."""

from __future__ import annotations

import asyncio
import re
import traceback
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands, tasks

from .database import create_social_interaction_tables, store_social_interaction_batch

if TYPE_CHECKING:
    from Rai import Rai


MENTION_RE = re.compile(r"<@!?(\d{17,22})>")
FLUSH_SECONDS = 5
FLUSH_MESSAGE_COUNT = 250


def timestamp_ms(value: Optional[datetime]) -> Optional[int]:
    return int(value.timestamp() * 1000) if value else None


def direct_mention_ids(content: str) -> set[int]:
    """Return only textual user mentions, excluding roles and implicit reply pings."""
    return {int(user_id) for user_id in MENTION_RE.findall(content)}


def reply_target(message: discord.Message, cached_messages) -> Optional[discord.abc.User]:
    """Resolve a reply target without issuing an API request for every reply."""
    reference = message.reference
    if not reference:
        return None

    for referenced_message in (getattr(reference, "resolved", None),
                               getattr(reference, "cached_message", None)):
        author = getattr(referenced_message, "author", None)
        if author:
            return author

    referenced_message_id = getattr(reference, "message_id", None)
    if not referenced_message_id:
        return None
    cached_message = discord.utils.get(cached_messages, id=referenced_message_id)
    return getattr(cached_message, "author", None)


class UserInteractions(commands.Cog):
    """Persist timestamped direct mentions and replies without retaining message content."""

    def __init__(self, bot: Rai):
        self.bot = bot
        self._pending_messages: list[tuple] = []
        self._pending_interactions: list[tuple] = []
        self._pending_arrivals: list[tuple] = []
        self._flush_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        await create_social_interaction_tables()
        self.flush_social_events.start()

    async def cog_unload(self) -> None:
        self.flush_social_events.cancel()
        await self.flush_pending()

    @staticmethod
    def _user_timestamps(user: Optional[discord.abc.User]) -> tuple[Optional[int], Optional[int]]:
        return timestamp_ms(getattr(user, "joined_at", None)), timestamp_ms(getattr(user, "created_at", None))

    def _target_user(self, guild: discord.Guild, user_id: int,
                     fallback: Optional[discord.abc.User] = None) -> Optional[discord.abc.User]:
        return guild.get_member(user_id) or fallback or self.bot.get_user(user_id)

    def _queue_interaction(self, message: discord.Message, interaction_type: str,
                           target_user_id: int, fallback: Optional[discord.abc.User] = None) -> None:
        if target_user_id == message.author.id:
            return

        target = self._target_user(message.guild, target_user_id, fallback)
        if target and target.bot:
            return

        target_joined_at_ms, target_account_created_at_ms = self._user_timestamps(target)
        self._pending_interactions.append((message.id, interaction_type, target_user_id,
                                           target_joined_at_ms, target_account_created_at_ms))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return

        joined_at_ms, account_created_at_ms = self._user_timestamps(member)
        if joined_at_ms is None:
            return
        self._pending_arrivals.append((member.guild.id, member.id, joined_at_ms,
                                       account_created_at_ms,
                                       timestamp_ms(discord.utils.utcnow())))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (not message.guild or message.webhook_id or message.author.bot
                or not isinstance(message.author, discord.Member)
                or message.type not in (discord.MessageType.default, discord.MessageType.reply)):
            return

        source_joined_at_ms, source_account_created_at_ms = self._user_timestamps(message.author)
        self._pending_messages.append((message.id, message.guild.id, message.channel.id,
                                       message.author.id, timestamp_ms(message.created_at),
                                       source_joined_at_ms, source_account_created_at_ms))

        reply_author = reply_target(message, self.bot.cached_messages)
        if reply_author:
            self._queue_interaction(message, "reply", reply_author.id, reply_author)

        for target_user_id in direct_mention_ids(message.content):
            self._queue_interaction(message, "mention", target_user_id)

        if len(self._pending_messages) == FLUSH_MESSAGE_COUNT:
            asyncio.create_task(self.flush_pending(), name="UserInteractions.flush_pending")

    async def flush_pending(self) -> None:
        async with self._flush_lock:
            if not (self._pending_messages or self._pending_interactions or self._pending_arrivals):
                return

            messages = self._pending_messages
            interactions = self._pending_interactions
            arrivals = self._pending_arrivals
            self._pending_messages = []
            self._pending_interactions = []
            self._pending_arrivals = []
            try:
                await store_social_interaction_batch(messages, interactions, arrivals)
            except Exception:
                self._pending_messages[0:0] = messages
                self._pending_interactions[0:0] = interactions
                self._pending_arrivals[0:0] = arrivals
                raise

    @tasks.loop(seconds=FLUSH_SECONDS)
    async def flush_social_events(self) -> None:
        try:
            await self.flush_pending()
        except Exception:
            print("Unable to save queued social interaction events:")
            traceback.print_exc()

    @flush_social_events.before_loop
    async def wait_until_ready(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Rai) -> None:
    await bot.add_cog(UserInteractions(bot))
