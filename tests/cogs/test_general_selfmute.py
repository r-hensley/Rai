import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from cogs import general as general_module
from tests.discord_fakes import (
    make_bot,
    make_channel,
    make_context,
    make_guild,
    make_member,
    make_message,
)


def make_forbidden() -> discord.Forbidden:
    response = SimpleNamespace(status=403, reason="Forbidden")
    return discord.Forbidden(
        response,
        {"code": 50013, "message": "Missing Permissions"},
    )


def make_selfmute_case(*, native_timeout_fails: bool):
    guild = make_guild()
    bot_member = make_member(member_id=777777777777777777, guild=guild, bot=True)
    guild.me = bot_member
    channel = make_channel(
        guild=guild,
        permissions_for=lambda member: SimpleNamespace(manage_messages=True),
    )

    timeout = AsyncMock()
    if native_timeout_fails:
        timeout.side_effect = make_forbidden()
    author = make_member(member_id=555555555555555555, guild=guild, timeout=timeout)
    command_message = make_message(
        content=";selfmute",
        author=author,
        channel=channel,
        guild=guild,
    )
    confirmation_message = make_message(
        content="yes",
        author=author,
        channel=channel,
        guild=guild,
    )
    bot = make_bot(
        db={"selfmute": {}},
        owner_id=999999999999999999,
        wait_for=AsyncMock(return_value=confirmation_message),
    )
    ctx = make_context(
        author=author,
        channel=channel,
        guild=guild,
        message=command_message,
        bot=bot,
    )
    cog = object.__new__(general_module.General)
    cog.bot = bot
    prompt = SimpleNamespace(reply=AsyncMock())
    return cog, ctx, prompt, timeout


@pytest.mark.asyncio
async def test_short_manual_selfmute_waits_and_expires_immediately(monkeypatch):
    cog, ctx, prompt, timeout = make_selfmute_case(native_timeout_fails=True)
    safe_reply = AsyncMock(return_value=prompt)
    safe_send = AsyncMock()
    entries_seen_during_sleep = []

    async def sleep_and_observe(delay):
        entries_seen_during_sleep.append(
            (
                delay,
                cog.bot.db["selfmute"][str(ctx.guild.id)][str(ctx.author.id)].copy(),
            )
        )

    monkeypatch.setattr(general_module.utils, "safe_reply", safe_reply)
    monkeypatch.setattr(general_module.utils, "safe_send", safe_send)
    monkeypatch.setattr(general_module.asyncio, "sleep", sleep_and_observe)

    await general_module.General.selfmute.callback(cog, ctx, "1m")

    timeout.assert_awaited_once()
    assert len(entries_seen_during_sleep) == 1
    delay, entry = entries_seen_during_sleep[0]
    assert 0 < delay <= 60
    assert entry["enable"] is True
    assert cog.bot.db["selfmute"][str(ctx.guild.id)] == {}
    safe_send.assert_awaited_once_with(ctx.author, "Your selfmute has expired.")


@pytest.mark.asyncio
async def test_five_minute_manual_selfmute_still_uses_background_sweep(monkeypatch):
    cog, ctx, prompt, timeout = make_selfmute_case(native_timeout_fails=True)
    safe_reply = AsyncMock(return_value=prompt)
    safe_send = AsyncMock()
    sleep = AsyncMock()
    monkeypatch.setattr(general_module.utils, "safe_reply", safe_reply)
    monkeypatch.setattr(general_module.utils, "safe_send", safe_send)
    monkeypatch.setattr(general_module.asyncio, "sleep", sleep)

    await general_module.General.selfmute.callback(cog, ctx, "5m")

    timeout.assert_awaited_once()
    sleep.assert_not_awaited()
    entry = cog.bot.db["selfmute"][str(ctx.guild.id)][str(ctx.author.id)]
    assert entry["enable"] is True
    safe_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_short_native_timeout_does_not_use_manual_wait(monkeypatch):
    cog, ctx, prompt, timeout = make_selfmute_case(native_timeout_fails=False)
    safe_reply = AsyncMock(return_value=prompt)
    safe_send = AsyncMock()
    sleep = AsyncMock()
    monkeypatch.setattr(general_module.utils, "safe_reply", safe_reply)
    monkeypatch.setattr(general_module.utils, "safe_send", safe_send)
    monkeypatch.setattr(general_module.asyncio, "sleep", sleep)

    await general_module.General.selfmute.callback(cog, ctx, "1m")

    timeout.assert_awaited_once()
    sleep.assert_not_awaited()
    entry = cog.bot.db["selfmute"][str(ctx.guild.id)][str(ctx.author.id)]
    assert entry["enable"] is False
    safe_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_short_manual_selfmute_does_not_remove_replacement_entry(monkeypatch):
    cog, ctx, prompt, _timeout = make_selfmute_case(native_timeout_fails=True)
    safe_reply = AsyncMock(return_value=prompt)
    safe_send = AsyncMock()
    replacement_entry = None

    async def replace_entry_while_sleeping(_delay):
        nonlocal replacement_entry
        guild_config = cog.bot.db["selfmute"][str(ctx.guild.id)]
        current_entry = guild_config[str(ctx.author.id)]
        replacement_entry = {
            "enable": True,
            "time": current_entry["time"] + 60,
        }
        guild_config[str(ctx.author.id)] = replacement_entry

    monkeypatch.setattr(general_module.utils, "safe_reply", safe_reply)
    monkeypatch.setattr(general_module.utils, "safe_send", safe_send)
    monkeypatch.setattr(general_module.asyncio, "sleep", replace_entry_while_sleeping)

    await general_module.General.selfmute.callback(cog, ctx, "1m")

    stored_entry = cog.bot.db["selfmute"][str(ctx.guild.id)][str(ctx.author.id)]
    assert stored_entry is replacement_entry
    safe_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_short_manual_wait_leaves_entry_for_background(monkeypatch):
    cog, ctx, prompt, _timeout = make_selfmute_case(native_timeout_fails=True)
    safe_reply = AsyncMock(return_value=prompt)
    safe_send = AsyncMock()
    sleep = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(general_module.utils, "safe_reply", safe_reply)
    monkeypatch.setattr(general_module.utils, "safe_send", safe_send)
    monkeypatch.setattr(general_module.asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await general_module.General.selfmute.callback(cog, ctx, "1m")

    entry = cog.bot.db["selfmute"][str(ctx.guild.id)][str(ctx.author.id)]
    assert entry["enable"] is True
    safe_send.assert_not_awaited()
