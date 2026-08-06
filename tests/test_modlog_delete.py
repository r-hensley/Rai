import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


# Keep this focused unit test independent from Rai's runtime startup checks and
# credentials; channel_mods only needs the Rai class for a type annotation here.
_previous_rai_module = sys.modules.get("Rai")
if _previous_rai_module is None:
    rai_stub = types.ModuleType("Rai")
    rai_stub.Rai = type("Rai", (), {})
    sys.modules["Rai"] = rai_stub

from cogs.utils import helper_functions as hf  # noqa: E402

_previous_bot = hf.here.bot
hf.here.bot = SimpleNamespace(profiling_decorators=set())
try:
    import cogs.channel_mods as channel_mods  # noqa: E402
finally:
    hf.here.bot = _previous_bot
    if _previous_rai_module is None:
        sys.modules.pop("Rai", None)


def make_context(entries):
    guild = SimpleNamespace(id=1)
    bot = SimpleNamespace(
        db={'modlog': {str(guild.id): {'42': entries}}},
        get_channel=lambda _channel_id: None,
    )
    ctx = SimpleNamespace(
        guild=guild,
        bot=bot,
        author=SimpleNamespace(id=2),
        message=SimpleNamespace(add_reaction=AsyncMock()),
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
    bot, ctx = make_context(entries)
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
    bot, ctx = make_context(entries)
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
    bot, ctx = make_context(entries)
    cog = channel_mods.ChannelMods(bot)

    await cog.modlog_delete.callback(cog, ctx, '42', indices='-all')

    assert '42' not in bot.db['modlog']['1']
