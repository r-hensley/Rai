import pytest

import cogs.channel_mods as channel_mods
import cogs.utils.BotUtils.bot_utils as utils
from tests.discord_fakes import (
    make_bot,
    make_channel,
    make_context,
    make_guild,
    make_member,
    make_message,
)


@pytest.fixture(autouse=True)
def modlog_edit_context(monkeypatch):
    async def member_not_found(_ctx, _user):
        return None

    monkeypatch.setattr(channel_mods.utils, 'member_converter', member_not_found)
    monkeypatch.setattr(channel_mods.hf, 'admin_check', lambda _ctx: True)


@pytest.mark.asyncio
async def test_modlog_edit_out_of_range(monkeypatch):
    called = {}

    async def fake_safe_send(destination, content='', *, embed=None, **kwargs):
        called['content'] = content

    monkeypatch.setattr(utils, 'safe_send', fake_safe_send)

    # Prepare minimal objects
    guild = make_guild(guild_id=1)
    bot = make_bot(db={'modlog': {str(guild.id): {'42': []}},
                       'mod_channel': {}, 'voicemod': {}})
    author = make_member(member_id=2, guild=guild)
    channel = make_channel(guild=guild, name='chan')
    message = make_message(guild=guild, channel=channel, author=author)
    ctx = make_context(
        guild=guild,
        bot=bot,
        author=author,
        channel=channel,
        message=message,
    )

    cog = channel_mods.ChannelMods(bot)

    # Index 5 is out of range for an empty list
    await cog.modlog_edit.callback(cog, ctx, '42', 5, reason='new')

    assert called.get('content') is not None
    assert "couldn't find the mod log" in called['content']


@pytest.mark.asyncio
async def test_modlog_edit_success_changes_reason(monkeypatch):
    called = {}

    async def fake_safe_send(destination, content='', *, embed=None, **kwargs):
        called['embed'] = embed

    monkeypatch.setattr(utils, 'safe_send', fake_safe_send)

    guild = make_guild(guild_id=1)
    bot_db = {'modlog': {str(guild.id): {'42': [{'reason': 'old reason'}]}},
              'mod_channel': {}, 'voicemod': {}}
    bot = make_bot(db=bot_db)
    author = make_member(member_id=2, guild=guild)
    channel = make_channel(guild=guild, name='chan')
    message = make_message(guild=guild, channel=channel, author=author)
    ctx = make_context(
        guild=guild,
        bot=bot,
        author=author,
        channel=channel,
        message=message,
    )

    cog = channel_mods.ChannelMods(bot)

    await cog.modlog_edit.callback(cog, ctx, '42', 1, reason='new reason')

    assert bot_db['modlog'][str(guild.id)]['42'][0]['reason'] == 'new reason'
    assert 'embed' in called
