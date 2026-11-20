from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs.utils import helper_functions as _helper_functions  # noqa: F401
from cogs.ai import AI, SP_SERVER_ID, STAFF_PING_SUMMARY_CHANNEL_ID, STAFF_PING_UNCLEAR
from tests.discord_fakes import make_bot, make_channel, make_guild, make_member, make_message

ROLE_ID = 123456789012345678
USER_ID = 234567890123456789


def setup_ping(content=None, history=()):
    guild = make_guild(guild_id=SP_SERVER_ID, get_role=Mock(return_value=object()))
    channel = make_channel(guild=guild)

    async def channel_history(**kwargs):
        for item in history:
            yield item

    channel.history = channel_history
    author = make_member(guild=guild)
    msg = make_message(
        guild=guild, channel=channel, author=author,
        content=content or f"<@&{ROLE_ID}>",
        reference=None, get_ctx=AsyncMock(), ctx=object(),
    )
    notif = make_message(
        channel=make_channel(channel_id=STAFF_PING_SUMMARY_CHANNEL_ID, guild=guild),
        author=author, message_id=444444444444444445, edit=AsyncMock(),
    )
    interactions = SimpleNamespace(staffping_code=AsyncMock(return_value=notif))
    bot = make_bot(
        db={"staff_ping": {str(SP_SERVER_ID): {"role": ROLE_ID, "channel": notif.channel.id}}},
        openai=object(), get_cog=Mock(return_value=interactions),
    )
    cog = AI.__new__(AI)
    cog.bot = bot
    cog.chat_completion_text = AsyncMock(return_value="This may have been an accidental staff ping.")
    return cog, msg, notif


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    f"<@&{ROLE_ID}>",
    f"<@&{ROLE_ID}> please help with the channel",
    f"<@&{ROLE_ID}> <@{USER_ID}> needs help",
])
async def test_non_reply_pings_are_summarized_with_original_mentions(content):
    cog, msg, notif = setup_ping(content)
    await cog.mods_ping(msg)
    messages = cog.chat_completion_text.await_args.kwargs["messages"]
    assert content in messages[1]["content"]
    assert "mistaken or accidental" in messages[0]["content"]
    assert "ordinary help" in messages[0]["content"]
    edit = notif.edit.await_args.kwargs
    assert "accidental" in edit["content"]
    assert edit["allowed_mentions"].to_dict() == {"parse": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [True, False])
async def test_replies_use_available_context_and_continue_if_deleted(cached):
    cog, msg, notif = setup_ping()
    reply = make_message(content="Please help me", channel=msg.channel, author=msg.author, message_id=444444444444444446)
    msg.reference = SimpleNamespace(cached_message=reply if cached else None, message_id=reply.id)
    msg.channel.fetch_message = AsyncMock(side_effect=discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"), "deleted"))
    await cog.mods_ping(msg)
    messages = cog.chat_completion_text.await_args.kwargs["messages"]
    assert any("Please help me" in item["content"] for item in messages) == cached
    if not cached:
        assert '"reply_unavailable": true' in messages[1]["content"]
    notif.edit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("result", ["", "No summary available."])
async def test_unclear_ping_is_visible_to_staff(result):
    cog, msg, notif = setup_ping()
    cog.chat_completion_text.return_value = result
    await cog.mods_ping(msg)
    assert STAFF_PING_UNCLEAR in notif.edit.await_args.kwargs["content"]


@pytest.mark.asyncio
async def test_distinct_pings_in_same_channel_are_not_suppressed():
    cog, msg, notif = setup_ping()
    await cog.mods_ping(msg)
    await cog.mods_ping(msg)
    assert cog.chat_completion_text.await_count == 1
    msg.id += 1
    await cog.mods_ping(msg)
    assert cog.chat_completion_text.await_count == 2


@pytest.mark.asyncio
async def test_attachment_only_history_is_included():
    previous = make_message(content="", attachments=[SimpleNamespace(filename="evidence.png")])
    cog, msg, notif = setup_ping(history=[previous])
    await cog.mods_ping(msg)
    messages = cog.chat_completion_text.await_args.kwargs["messages"]
    assert "evidence.png" in messages[-1]["content"]


@pytest.mark.asyncio
async def test_history_failure_releases_deduplication(monkeypatch):
    cog, msg, notif = setup_ping()

    async def failed_history(**kwargs):
        raise RuntimeError("history unavailable")
        yield

    msg.channel.history = failed_history
    monkeypatch.setattr("cogs.ai.utils.safe_reply", AsyncMock())
    with pytest.raises(RuntimeError, match="history unavailable"):
        await cog.mods_ping(msg)
    assert msg.id not in cog.staff_ping_summary_cooldowns()
    cog.chat_completion_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_ai_failure_releases_deduplication(monkeypatch):
    cog, msg, notif = setup_ping()
    cog.chat_completion_text.side_effect = RuntimeError("API unavailable")
    monkeypatch.setattr("cogs.ai.utils.safe_reply", AsyncMock())
    with pytest.raises(RuntimeError, match="API unavailable"):
        await cog.mods_ping(msg)
    assert msg.id not in cog.staff_ping_summary_cooldowns()
    notif.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_long_output_is_bounded_and_mentions_are_disabled():
    cog, msg, notif = setup_ping()
    cog.chat_completion_text.return_value = "@everyone " * 500
    await cog.mods_ping(msg)
    edit = notif.edit.await_args.kwargs
    assert len(edit["content"]) <= 2000
    assert edit["allowed_mentions"].to_dict() == {"parse": []}


@pytest.mark.asyncio
async def test_ai_disabled_keeps_staff_notification_without_summary():
    cog, msg, notif = setup_ping()
    cog.bot.db["ai_features"] = {"enabled": False}
    await cog.mods_ping(msg)
    cog.bot.get_cog("Interactions").staffping_code.assert_awaited_once()
    cog.chat_completion_text.assert_not_awaited()
    notif.edit.assert_not_awaited()
