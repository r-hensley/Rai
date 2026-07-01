import pytest
from types import SimpleNamespace

import cogs.channel_mods as channel_mods
import cogs.utils.BotUtils.bot_utils as utils


@pytest.mark.asyncio
async def test_modlog_edit_out_of_range(monkeypatch):
    called = {}

    async def fake_safe_send(destination, content='', *, embed=None, **kwargs):
        called['content'] = content

    monkeypatch.setattr(utils, 'safe_send', fake_safe_send)

    # Prepare minimal objects
    guild = SimpleNamespace(id=1, members=[])
    bot = SimpleNamespace(db={'modlog': {str(guild.id): {'42': []}},
                              'mod_channel': {}, 'voicemod': {}})
    ctx = SimpleNamespace(guild=guild, bot=bot, author=SimpleNamespace(id=2),
                          channel=SimpleNamespace(name='chan'), message=SimpleNamespace(content=''))

    cog = channel_mods.ChannelMods(bot)

    # Index 5 is out of range for an empty list
    await cog.modlog_edit(ctx, '42', 5, reason='new')

    assert called.get('content') is not None
    assert "couldn't find the mod log" in called['content']


@pytest.mark.asyncio
async def test_modlog_edit_success_changes_reason(monkeypatch):
    called = {}

    async def fake_safe_send(destination, content='', *, embed=None, **kwargs):
        called['embed'] = embed

    monkeypatch.setattr(utils, 'safe_send', fake_safe_send)

    guild = SimpleNamespace(id=1, members=[])
    bot_db = {'modlog': {str(guild.id): {'42': [{'reason': 'old reason'}]}},
              'mod_channel': {}, 'voicemod': {}}
    bot = SimpleNamespace(db=bot_db)
    ctx = SimpleNamespace(guild=guild, bot=bot, author=SimpleNamespace(id=2),
                          channel=SimpleNamespace(name='chan'), message=SimpleNamespace(content=''))

    cog = channel_mods.ChannelMods(bot)

    await cog.modlog_edit(ctx, '42', 1, reason='new reason')

    assert bot_db[str(guild.id)]['42'][0]['reason'] == 'new reason'
    assert 'embed' in called
