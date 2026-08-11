from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import cogs.owner as owner_module
from tests.discord_fakes import (
    make_bot,
    make_channel,
    make_context,
    make_guild,
    make_member,
    make_message,
)


pytestmark = pytest.mark.catchup


GUILD_ID = 111111111111111111
CHANNEL_ID = 222222222222222222
OWNER_ID = 333333333333333333
MESSAGE_ID = 444444444444444444
NOW = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)


def allow_history(_member):
    return SimpleNamespace(view_channel=True, read_message_history=True)


@pytest.mark.asyncio
async def test_resolve_catchup_channel_preflights_bot_permissions():
    bot_member = make_member()
    owner_member = make_member(member_id=OWNER_ID)
    permissions = {
        bot_member.id: SimpleNamespace(view_channel=True, read_message_history=False),
        owner_member.id: SimpleNamespace(view_channel=True, read_message_history=True),
    }
    guild = make_guild(
        guild_id=GUILD_ID,
        members=[bot_member, owner_member],
        me=bot_member,
    )
    make_channel(
        channel_id=CHANNEL_ID,
        name='general',
        guild=guild,
        permissions_for=lambda member: permissions[member.id],
    )
    cog = owner_module.Owner(make_bot())

    with pytest.raises(ValueError, match='Rai lacks Read Message History'):
        await cog._resolve_catchup_channel(guild, CHANNEL_ID, owner_member)


@pytest.mark.asyncio
async def test_catchup_command_searches_and_sends_private_markdown(monkeypatch):
    bot_member = make_member()
    author = make_member(
        member_id=OWNER_ID,
        display_name='Ryan, Jr.',
        global_name='Ryan',
        name='ryry013',
        send=AsyncMock(),
    )
    guild = make_guild(
        guild_id=GUILD_ID,
        members=[bot_member, author],
        me=bot_member,
    )
    channel = make_channel(
        channel_id=CHANNEL_ID,
        name='general',
        guild=guild,
        permissions_for=allow_history,
    )
    status = make_message(
        author=bot_member,
        channel=channel,
        edit=AsyncMock(),
    )
    bot = make_bot(http=object())
    ctx = make_context(
        guild=guild,
        channel=channel,
        author=author,
        bot=bot,
        send=AsyncMock(return_value=status),
    )
    cog = owner_module.Owner(bot)

    message = owner_module.catchup_utils.TranscriptMessage(
        id=MESSAGE_ID,
        channel_id=CHANNEL_ID,
        created_at=NOW - timedelta(days=1),
        author_id=999999999999999999,
        author_name='Someone Else',
        content='Ryan, this needs your review.',
        jump_url=f'https://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}/{MESSAGE_ID}',
    )
    hit = owner_module.catchup_utils.SearchHit(message=message, reasons={'name "Ryan"'})
    window = owner_module.catchup_utils.ContextWindow(
        channel_id=CHANNEL_ID,
        messages={MESSAGE_ID: message},
        hit_ids={MESSAGE_ID},
    )
    captured_search = {}

    async def collect_search_hits(_search, **kwargs):
        captured_search.update(kwargs)
        return owner_module.catchup_utils.SearchCollection(hits=[hit])

    async def collect_context_windows(hits, _fetch_context):
        assert hits == [hit]
        return owner_module.catchup_utils.ContextCollection(windows=[window])

    monkeypatch.setattr(owner_module.discord.utils, 'utcnow', lambda: NOW)
    monkeypatch.setattr(owner_module.catchup_utils, 'collect_search_hits', collect_search_hits)
    monkeypatch.setattr(owner_module.catchup_utils, 'collect_context_windows', collect_context_windows)

    await owner_module.Owner.catchup.callback(
        cog,
        ctx,
        days=14,
        spec=f'<#{CHANNEL_ID}> | R-Dog',
    )

    assert captured_search['guild_id'] == GUILD_ID
    assert captured_search['channel_ids'] == [CHANNEL_ID]
    assert captured_search['user_id'] == OWNER_ID
    assert captured_search['aliases'] == ['Ryan, Jr.', 'Ryan', 'ryry013', 'R-Dog']
    assert captured_search['min_id'] == owner_module.discord.utils.time_snowflake(
        NOW - timedelta(days=14),
        high=False,
    )
    assert captured_search['max_id'] == owner_module.discord.utils.time_snowflake(NOW, high=True)

    author.send.assert_awaited_once()
    dm_kwargs = author.send.await_args.kwargs
    assert dm_kwargs['file'].filename == 'discord_catchup_20260727.md'
    assert dm_kwargs['allowed_mentions'].everyone is False
    assert dm_kwargs['allowed_mentions'].users is False
    dm_kwargs['file'].fp.seek(0)
    markdown = dm_kwargs['file'].fp.read().decode('utf-8')
    assert '# Discord catch-up export' in markdown
    assert 'Ryan, this needs your review.' in markdown
    assert '**MATCH — name "Ryan"' in markdown

    assert ctx.send.await_count == 1
    assert 'sent to you by DM' in ctx.send.await_args.args[0]
    assert status.edit.await_count == 2
    assert status.edit.await_args.kwargs['content'].startswith('Sent 1 Markdown file')
