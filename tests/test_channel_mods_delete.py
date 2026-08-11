"""Tests for the queue-first message lookup used by ``;delete`` / ``;del``.

The production command normally receives large discord.py objects.  These tests
use the shared factories in ``tests.discord_fakes`` for common Discord object
graphs, then use ``SimpleNamespace`` only for small Rai-specific records such as
queue entries.  ``Mock`` represents synchronous cache/database
calls, while ``AsyncMock`` represents API calls that the bot must await.

The first group tests ``_fetch_message_from_queue()`` in isolation.  The final
two tests exercise the actual command callback so they can verify how queue
lookup interacts with the command's older lookup and deletion behavior.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

import cogs.channel_mods as channel_mods
from tests.discord_fakes import (
    discord_not_found,
    make_bot,
    make_channel,
    make_context,
    make_guild,
    make_member,
    make_message,
    make_thread,
)


# These IDs need to look like real 18-21 digit Discord snowflakes because the
# command rejects shorter dummy integers before attempting lookup.  Keeping
# them distinct also clarifies whether an assertion concerns the guild, thread,
# or message.
GUILD_ID = 243838819743432704
THREAD_ID = 1535553006481506357
MESSAGE_ID = 1535554006481506357


@pytest.mark.asyncio
@pytest.mark.parametrize("message_queue", [None, [], {"stale": True}])
async def test_queue_lookup_tolerates_unavailable_queue(message_queue):
    """An absent, empty, or incompatible queue should be treated as a miss.

    ``None`` models a bot without a loaded queue, ``[]`` models an empty/falsy
    queue, and the dictionary is truthy but does not provide the required
    callable ``find`` method.
    """
    # Both channel methods are mocks deliberately: they are tripwires proving
    # that an unusable queue exits before trying to resolve any channel.
    guild = make_guild(guild_id=GUILD_ID)
    bot = make_bot(message_queue=message_queue)
    cog = channel_mods.ChannelMods(bot)

    # Test the small lookup helper directly, without running the whole command.
    ctx = make_context(guild=guild, bot=bot)
    result = await cog._fetch_message_from_queue(ctx, MESSAGE_ID)

    # A queue miss is represented by None.  The caller can then continue with
    # its normal current-channel and cross-channel lookup paths.
    assert result is None
    # Most importantly, unavailable queue data must not trigger Discord cache
    # access or an HTTP request for a channel.
    guild.get_channel_or_thread.assert_not_called()
    guild.fetch_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_lookup_fetches_from_recorded_thread():
    """A queue entry should lead directly to its already-cached thread."""
    # The queue recorded THREAD_ID, and Discord's guild cache can resolve that
    # ID to this thread without making an API request.
    thread = make_thread(thread_id=THREAD_ID)

    # MessageQueue.find() returns queue records rather than Discord messages.
    # Only channel_id is required for the helper to locate the real message.
    queue = SimpleNamespace(
        find=Mock(return_value=[SimpleNamespace(channel_id=THREAD_ID)]),
    )
    guild = make_guild(
        guild_id=GUILD_ID,
        threads=[thread],
    )
    target_message = make_message(
        message_id=MESSAGE_ID,
        channel=thread,
        guild=guild,
    )
    thread.fetch_message = AsyncMock(return_value=target_message)
    bot = make_bot(message_queue=queue)
    cog = channel_mods.ChannelMods(bot)
    ctx = make_context(
        guild=guild,
        channel=thread,
        author=target_message.author,
        bot=bot,
    )

    # Ask the helper to turn the queue record into an actual message object.
    result = await cog._fetch_message_from_queue(ctx, MESSAGE_ID)

    # Use identity here to show the exact object returned by fetch_message()
    # propagates back to the command.
    assert result is target_message
    # Guild ID is part of the query so a matching snowflake recorded for some
    # other server cannot be selected.
    queue.find.assert_called_once_with(message_id=MESSAGE_ID, guild_id=GUILD_ID)
    guild.get_channel_or_thread.assert_called_once_with(THREAD_ID)
    thread.fetch_message.assert_awaited_once_with(MESSAGE_ID)
    # A cached thread means there was no reason to call Discord's channel API.
    guild.fetch_channel.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_lookup_fetches_uncached_recorded_channel():
    """A valid queue entry should still work after its channel leaves cache."""
    # This channel is returned by the asynchronous Discord API lookup below.
    # Its guild attribute lets the helper verify that it belongs to this server.
    channel = make_channel(channel_id=THREAD_ID)
    queue = SimpleNamespace(
        find=Mock(return_value=[SimpleNamespace(channel_id=THREAD_ID)]),
    )
    # Leaving the regular cache empty while configuring fetched_channels models
    # a cache miss followed by an API success for an archived thread.
    guild = make_guild(
        guild_id=GUILD_ID,
        fetched_channels=[channel],
    )
    target_message = make_message(
        message_id=MESSAGE_ID,
        channel=channel,
        guild=guild,
    )
    channel.fetch_message = AsyncMock(return_value=target_message)
    # make_message() links a coherent graph and therefore registers its
    # channel. Remove it from the two live cache views to model later eviction.
    guild.channels.remove(channel)
    guild.text_channels.remove(channel)
    bot = make_bot(message_queue=queue)
    cog = channel_mods.ChannelMods(bot)
    ctx = make_context(
        guild=guild,
        author=target_message.author,
        bot=bot,
    )

    result = await cog._fetch_message_from_queue(ctx, MESSAGE_ID)

    assert result is target_message
    # The recorded channel ID—not the message ID—is used for channel lookup.
    guild.fetch_channel.assert_awaited_once_with(THREAD_ID)
    # Once that channel is resolved, the original message ID is fetched there.
    channel.fetch_message.assert_awaited_once_with(MESSAGE_ID)


@pytest.mark.asyncio
async def test_queue_lookup_rejects_uncached_channel_from_another_guild():
    """Never follow a queue record to a channel owned by another guild."""
    # Simulate an unexpected API/cache result whose guild differs from ctx.guild.
    foreign_guild = make_guild(guild_id=GUILD_ID + 1)
    channel = make_channel(
        channel_id=THREAD_ID,
        guild=foreign_guild,
        fetch_message=AsyncMock(),
    )
    queue = SimpleNamespace(
        find=Mock(return_value=[SimpleNamespace(channel_id=THREAD_ID)]),
    )
    guild = make_guild(
        guild_id=GUILD_ID,
        fetched_channels=[channel],
    )
    bot = make_bot(message_queue=queue)
    cog = channel_mods.ChannelMods(bot)
    ctx = make_context(guild=guild, bot=bot)

    result = await cog._fetch_message_from_queue(ctx, MESSAGE_ID)

    # Treat the cross-guild channel as a queue miss rather than exposing data
    # or attempting a message request in a different server.
    assert result is None
    channel.fetch_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_queue_entry_allows_normal_lookup_fallback():
    """A deleted/stale queued message should become an ordinary queue miss."""
    # The channel still exists, but Discord says the recorded message no longer
    # does.  This is expected when the queue outlives a deleted message.
    channel = make_thread(
        thread_id=THREAD_ID,
        fetch_message=AsyncMock(side_effect=discord_not_found()),
    )
    queue = SimpleNamespace(
        find=Mock(return_value=[SimpleNamespace(channel_id=THREAD_ID)]),
    )
    guild = make_guild(
        guild_id=GUILD_ID,
        threads=[channel],
    )
    bot = make_bot(message_queue=queue)
    cog = channel_mods.ChannelMods(bot)
    ctx = make_context(guild=guild, channel=channel, bot=bot)

    result = await cog._fetch_message_from_queue(ctx, MESSAGE_ID)

    # Returning None is what tells msg_delete() to continue with its original
    # current-channel lookup instead of aborting the command.
    assert result is None
    # Confirm this was a genuine stale-message miss, not an early queue failure.
    channel.fetch_message.assert_awaited_once_with(MESSAGE_ID)


@pytest.mark.asyncio
async def test_delete_queue_hit_skips_current_channel_fetch():
    """The full command should use a queue hit before its legacy lookup path."""

    # This is the thread named by the queue record.  The command reads its name,
    # mention, history, guild, and fetch_message method while deleting/logging.
    target_channel = make_thread(
        thread_id=THREAD_ID,
        name="queued-thread",
    )

    # Registering the thread through make_guild wires target_channel.guild and
    # configures the guild's synchronous channel/thread cache lookup.
    guild = make_guild(guild_id=GUILD_ID, threads=[target_channel])
    author = make_member(member_id=1, guild=guild)

    # Supply the minimal Discord Message surface exercised by msg_delete().
    target_message = make_message(
        message_id=MESSAGE_ID,
        author=author,
        channel=target_channel,
        guild=guild,
        content="target message",
    )
    target_channel.fetch_message = AsyncMock(return_value=target_message)

    # This is where ;del was invoked.  Its fetch mock is a tripwire: a queue hit
    # must prevent the command from making this older current-channel request.
    current_channel = make_channel(
        guild=guild,
        fetch_message=AsyncMock(),
    )
    queue = SimpleNamespace(
        find=Mock(return_value=[SimpleNamespace(channel_id=THREAD_ID)]),
    )

    # The deletion command also writes an audit log.  These two objects provide
    # the configured log channel and the message created in that channel.
    log_channel = make_channel(channel_id=98, guild=guild)
    log_message = make_message(message_id=99, channel=log_channel, guild=guild)
    bot = make_bot(
        db={
            "mod_channel": {},
            "submod_channel": {str(GUILD_ID): log_channel.id},
        },
        channels=[log_channel],
        message_queue=queue,
    )
    cog = channel_mods.ChannelMods(bot)

    # Build only the Context fields that msg_delete() reads.  The command text
    # is included because the production command copies it to a privacy DM.
    command_message = make_message(
        content=f";del {MESSAGE_ID}",
        author=author,
        channel=current_channel,
        guild=guild,
    )
    ctx = make_context(
        author=author,
        channel=current_channel,
        guild=guild,
        message=command_message,
        bot=bot,
    )
    safe_send = AsyncMock(return_value=log_message)
    send_attachments = AsyncMock()

    # Patch outbound sends so the test never contacts Discord.  Returning
    # log_message from safe_send also allows attachment-forwarding code to run.
    with (
        patch("cogs.channel_mods.utils.safe_send", safe_send),
        patch("cogs.channel_mods.hf.send_attachments_to_thread_on_message", send_attachments),
    ):
        # msg_delete is a discord.py Command object.  Calling .callback directly
        # bypasses command parsing/checks, so the cog instance is passed explicitly.
        await cog.msg_delete.callback(cog, ctx, str(MESSAGE_ID))

    # Together these assertions establish the desired branch: query the queue,
    # fetch from its thread, never fetch from ctx.channel, then delete the result.
    queue.find.assert_called_once_with(message_id=MESSAGE_ID, guild_id=GUILD_ID)
    target_channel.fetch_message.assert_awaited_once_with(MESSAGE_ID)
    current_channel.fetch_message.assert_not_awaited()
    target_message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_checks_queue_before_current_channel_fetch():
    """Record side effects to prove queue lookup happens first, even on a miss."""
    # Both fake operations append to this list, giving the test an observable
    # timeline rather than merely showing that each operation happened.
    events = []

    class RecordingQueue:
        """Small truthy queue double that records each find() call."""

        def __bool__(self):
            # _fetch_message_from_queue() intentionally ignores falsy queues.
            return True

        def find(self, **kwargs):
            events.append(("queue", kwargs))
            # An empty result forces msg_delete() into its normal fallback path.
            return []

    async def fetch_current(message_id):
        """Record the legacy current-channel fetch that follows a queue miss."""
        events.append(("current_channel", message_id))
        # A real missing message produces discord.NotFound.  With no guild text
        # channels below, the command will report failure and finish cleanly.
        raise discord_not_found()

    guild = make_guild(guild_id=GUILD_ID)
    current_channel = make_channel(
        guild=guild,
        fetch_message=AsyncMock(side_effect=fetch_current),
    )
    bot = make_bot(message_queue=RecordingQueue())
    cog = channel_mods.ChannelMods(bot)
    author = make_member(member_id=1, guild=guild)
    command_message = make_message(
        content=f";del {MESSAGE_ID}",
        author=author,
        channel=current_channel,
        guild=guild,
    )
    ctx = make_context(
        author=author,
        channel=current_channel,
        guild=guild,
        message=command_message,
        bot=bot,
    )
    # This test isolates the first two lookup stages.  Removing text-channel
    # fallbacks prevents the command from searching current_channel a second
    # time after its deliberate NotFound result.
    guild.text_channels.clear()

    # safe_send absorbs the privacy DM and final "unable to find" response.
    with patch("cogs.channel_mods.utils.safe_send", AsyncMock()):
        await cog.msg_delete.callback(cog, ctx, str(MESSAGE_ID))

    # The exact list comparison checks ordering as well as arguments.  Reversing
    # the implementation back to fetch_message-first would reverse these items.
    assert events == [
        ("queue", {"message_id": MESSAGE_ID, "guild_id": GUILD_ID}),
        ("current_channel", MESSAGE_ID),
    ]
