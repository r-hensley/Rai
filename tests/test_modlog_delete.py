import pytest

import cogs.channel_mods as channel_mods
from tests.discord_fakes import (
    make_bot,
    make_context,
    make_guild,
    make_member,
    make_message,
)


def make_modlog_context(entries):
    guild = make_guild(guild_id=1)
    bot = make_bot(
        db={'modlog': {str(guild.id): {'42': entries}}},
    )
    author = make_member(member_id=2, guild=guild)
    message = make_message(author=author, guild=guild)
    ctx = make_context(
        guild=guild,
        bot=bot,
        author=author,
        message=message,
    )
    return bot, ctx


@pytest.fixture(autouse=True)
def trial_staff_context(monkeypatch):
    async def member_not_found(_ctx, _user):
        return None

    async def safe_send(*_args, **_kwargs):
        return None

    # Calling the command callback directly bypasses its decorator, so explicitly
    # model a Trial Staff caller who does not have unrestricted submod access.
    monkeypatch.setattr(channel_mods.utils, 'member_converter', member_not_found)
    monkeypatch.setattr(channel_mods.utils, 'safe_send', safe_send)
    monkeypatch.setattr(channel_mods.hf, 'submod_check', lambda _ctx: False)


@pytest.mark.asyncio
async def test_trial_staff_can_delete_automod_timeout():
    entries = [{
        'type': 'AutoMod Timeout',
        'author_id': None,
        'jump_url': None,
    }]
    bot, ctx = make_modlog_context(entries)
    cog = channel_mods.ChannelMods(bot)

    await cog.modlog_delete.callback(cog, ctx, '42', indices='1')

    assert entries == []
    ctx.message.add_reaction.assert_awaited_once_with('✅')


@pytest.mark.asyncio
async def test_trial_staff_cannot_delete_someone_elses_non_automod_log(monkeypatch):
    messages = []

    async def capture_safe_send(_destination, content='', **_kwargs):
        messages.append(content)

    monkeypatch.setattr(channel_mods.utils, 'safe_send', capture_safe_send)
    entries = [{
        'type': 'Warning',
        'author_id': 999,
        'jump_url': None,
    }]
    bot, ctx = make_modlog_context(entries)
    cog = channel_mods.ChannelMods(bot)

    await cog.modlog_delete.callback(cog, ctx, '42', indices='1')

    assert len(entries) == 1
    assert messages == ["Trial Staff solo puede borrar logs propios o de AutoMod."]
    ctx.message.add_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_trial_staff_can_delete_all_own_and_automod_logs():
    entries = [
        {'type': 'Warning', 'author_id': 2, 'jump_url': None},
        {'type': 'AutoMod Timeout', 'author_id': None, 'jump_url': None},
    ]
    bot, ctx = make_modlog_context(entries)
    cog = channel_mods.ChannelMods(bot)

    await cog.modlog_delete.callback(cog, ctx, '42', indices='-all')

    assert '42' not in bot.db['modlog']['1']
