from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs import events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('evidence', 'search_count', 'allowed'),
    [
        ('member_join_date', 0, True),
        ('saved_join_date', 0, True),
        ('first_message', 1, True),
        ('too_recent', 1, False),
        ('no_match', 1, False),
        ('index_unavailable', 1, False),
        ('search_timeout', 1, True),
        ('new_account', 0, False),
    ],
)
async def test_spanish_voice_gate_uses_earlier_membership(monkeypatch, evidence, search_count, allowed):
    now = discord.utils.utcnow().replace(microsecond=0)
    older = now - timedelta(days=30)
    recent = now - timedelta(hours=1)
    user_id = 123456789012345678
    guild = SimpleNamespace(id=events.SP_SERVER_ID, get_role=Mock(return_value=object()))
    channel = SimpleNamespace(category=SimpleNamespace(id=1), user_limit=0, set_permissions=AsyncMock())
    after = SimpleNamespace(channel=channel)
    member = SimpleNamespace(
        id=user_id, guild=guild, roles=[], voice=after, edit=AsyncMock(),
        created_at=recent if evidence == 'new_account' else older - timedelta(days=365),
        joined_at=older if evidence == 'member_join_date' else now - timedelta(minutes=30),
    )
    joindates = {str(user_id): older.timestamp()} if evidence == 'saved_join_date' else {}
    messages = []
    if evidence in ('first_message', 'too_recent'):
        message_time = older if evidence == 'first_message' else recent
        messages.append([{
            'id': str(discord.utils.time_snowflake(message_time)),
            'author': {'id': str(user_id)},
        }])
    data = {'messages': messages}
    if evidence == 'index_unavailable':
        data = {'code': 110000, 'retry_after': 60}
    request = AsyncMock(return_value=data)
    if evidence == 'search_timeout':
        request.side_effect = TimeoutError
    bot = SimpleNamespace(
        db={'voice_lock': {str(guild.id): {'categories': {'1': True}}},
            'joindates': joindates, 'timed_voice_role': {}},
        stats={}, get_guild=Mock(return_value=guild), http=SimpleNamespace(request=request),
    )
    send = AsyncMock()
    save = AsyncMock()
    monkeypatch.setattr(events.hf, 'count_messages', Mock(return_value=0))
    monkeypatch.setattr(events.utils, 'safe_send', send)
    monkeypatch.setattr(events.utils, 'dump_json', save)
    monkeypatch.setattr(events.asyncio, 'sleep', AsyncMock())

    await events.Events(bot).on_voice_state_update(member, SimpleNamespace(channel=None), after)

    assert request.await_count == search_count
    if search_count:
        route, = request.call_args.args
        assert route.url.endswith(f'/guilds/{guild.id}/messages/search')
        params = dict(request.call_args.kwargs['params'])
        assert params['author_id'] == str(user_id)
        assert params['max_id'] == str(discord.utils.time_snowflake(member.joined_at))
        assert params['sort_order'] == 'asc'
        assert params['limit'] == '1'
        assert 'channel_id' not in params
    if allowed:
        member.edit.assert_not_awaited()
        send.assert_not_awaited()
        channel.set_permissions.assert_not_awaited()
    else:
        member.edit.assert_awaited_once_with(voice_channel=None)
        send.assert_awaited_once()
    if evidence in ('first_message', 'too_recent'):
        assert joindates[str(user_id)] == message_time.timestamp()
        save.assert_awaited_once_with('db', bot=bot)
    else:
        save.assert_not_awaited()
