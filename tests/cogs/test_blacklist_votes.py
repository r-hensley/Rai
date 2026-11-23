import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from cogs.general import General
from cogs.utils.blacklist import BANS_CHANNEL_ID, BLACKLIST_CHANNEL_ID, VOTE_CUSTOM_ID


TARGET = '123456789012345678'


@pytest.fixture
def voting():
    config = {'residency': {'1': 10, '2': 10, '3': 20, '4': 30}, 'votes': {}, 'blacklist': []}
    rai = SimpleNamespace(id=7)
    channel = SimpleNamespace(id=BLACKLIST_CHANNEL_ID, mention='#global-blacklist')
    entry = SimpleNamespace(
        id=123456789012345679, author=rai, channel=channel, embeds=[],
        jump_url='https://discord.com/channels/1/2/3', delete=AsyncMock(),
    )

    async def update(*, embed, **kwargs):
        entry.embeds = [embed]
        return entry

    entry.edit = AsyncMock(side_effect=update)
    channel.send = AsyncMock(side_effect=update)
    channel.fetch_message = AsyncMock(return_value=entry)
    crosspost = SimpleNamespace(
        author=rai, channel=SimpleNamespace(id=BANS_CHANNEL_ID),
        embeds=[discord.Embed(title='GBL Network Ban', description=(
            f'**Example** － <@{TARGET}>\n({TARGET})\n'
            '__Server__: Example server\n\n__Reason__: Spam\nAdditional evidence'
        ))],
        jump_url='https://discord.com/channels/1/4/5',
    )
    bot = SimpleNamespace(
        db={'global_blacklist': config}, user=rai,
        get_channel={BLACKLIST_CHANNEL_ID: channel}.get,
        get_user={int(TARGET): 'Example'}.get,
    )
    return General(bot), config, entry, crosspost


def moderator(user_id):
    return SimpleNamespace(id=user_id, name=f'moderator{user_id}', bot=False)


def click(message, user_id, *, custom_id=VOTE_CUSTOM_ID):
    return SimpleNamespace(
        type=discord.InteractionType.component, data={'custom_id': custom_id},
        channel_id=message.channel.id, message=message, user=moderator(user_id),
        response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_vote_buttons_work_without_restoring_per_message_views(voting):
    cog, config, entry, crosspost = voting
    first, duplicate = click(crosspost, 1), click(crosspost, 2)
    await asyncio.gather(cog.on_interaction(first), cog.on_interaction(duplicate))

    entry.channel.send.assert_awaited_once()
    view = entry.channel.send.await_args.kwargs['view']
    assert view.to_components()[0]['components'][0]['custom_id'] == VOTE_CUSTOM_ID
    assert view.is_finished()  # discord.py sends the components without storing a finished View.
    first.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert first.followup.send.await_args.kwargs['ephemeral']
    assert 'already voted' in duplicate.followup.send.await_args.args[0]
    assert '1/3 servers' in entry.embeds[0].description
    fields = {field.name: field for field in entry.embeds[0].fields}
    assert fields['Reason'].value == 'Spam\nAdditional evidence'
    assert not fields['Reason'].inline
    assert crosspost.jump_url in fields['Source'].value

    # Recreate the cog using the existing DB, with no restored views or message cache.
    bot = SimpleNamespace(**vars(cog.bot))
    bot.db = json.loads(json.dumps(bot.db))
    config = bot.db['global_blacklist']
    cog = General(bot)
    await cog.on_interaction(click(entry, 3))
    assert config['votes'][TARGET]['votes'] == [10, 20]
    assert '2/3 servers' in entry.embeds[0].description
    await cog.on_interaction(click(crosspost, 4))
    assert config['votes'] == {}
    assert config['blacklist'] == [int(TARGET)]
    assert 'Blacklisted · 3/3 servers' in entry.embeds[0].description
    assert entry.edit.await_args.kwargs['view'] is None


@pytest.mark.asyncio
async def test_legacy_arrow_completes_existing_blacklist_entry(voting):
    cog, config, entry, _ = voting
    embed = discord.Embed(title=f'{TARGET} Example (2 votes)')
    embed.add_field(name='Voters', value='first, second')
    embed.add_field(name='Reason', value='Spam')
    entry.embeds = [embed]
    config['votes'][TARGET] = {'votes': [10, 20], 'message': entry.id}

    payload = SimpleNamespace(
        channel_id=entry.channel.id, emoji=SimpleNamespace(name='⬆'),
        member=moderator(4), user_id=4, message_id=entry.id,
    )
    await cog.on_raw_reaction_add(payload)

    assert config['blacklist'] == [int(TARGET)]
    assert entry.embeds[0].title == f'{TARGET} Example (3 votes)'
    assert entry.embeds[0].fields[0].value == 'first, second, moderator4'


@pytest.mark.asyncio
async def test_vote_routing_and_residency_checks(voting):
    cog, config, entry, crosspost = voting
    unrelated = click(crosspost, 1, custom_id='different-button')
    await cog.on_interaction(unrelated)
    unrelated.response.defer.assert_not_awaited()

    wrong_channel = click(crosspost, 1)
    wrong_channel.channel_id = 9999
    await cog.on_interaction(wrong_channel)
    wrong_channel.response.defer.assert_not_awaited()

    unregistered = click(crosspost, 99)
    await cog.on_interaction(unregistered)
    assert 'Claim residency' in unregistered.followup.send.await_args.args[0]

    crosspost.embeds[0].description = 'UNBANNED\n' + crosspost.embeds[0].description
    unbanned = click(crosspost, 1)
    await cog.on_interaction(unbanned)
    assert 'unavailable' in unbanned.followup.send.await_args.args[0]
    entry.channel.send.assert_not_awaited()
    assert config['votes'] == {}


@pytest.mark.asyncio
async def test_failed_edit_leaves_vote_available_for_retry(voting):
    cog, config, entry, crosspost = voting
    await cog.on_interaction(click(crosspost, 1))
    error = discord.HTTPException(SimpleNamespace(status=500, reason='Synthetic failure'), '')
    entry.edit.side_effect = error

    with pytest.raises(discord.HTTPException):
        await cog.on_interaction(click(entry, 3))

    assert config['votes'][TARGET]['votes'] == [10]
    assert '1/3 servers' in entry.embeds[0].description


@pytest.mark.asyncio
async def test_reason_edit_and_removal_support_new_entry_layout(voting):
    cog, config, entry, crosspost = voting
    await cog.on_interaction(click(crosspost, 1))
    ctx = SimpleNamespace(
        send=AsyncMock(), author=moderator(1), message=SimpleNamespace(add_reaction=AsyncMock()),
    )
    await General.blacklist_reason.callback(cog, ctx, str(entry.id), reason='Updated evidence')
    assert {field.name: field.value for field in entry.embeds[0].fields}['Reason'] == 'Updated evidence'

    await General.blacklist_remove.callback(cog, ctx, str(entry.id))
    entry.delete.assert_awaited_once()
    assert config['votes'] == {}
    assert 'Entry removed' in entry.embeds[0].description
    assert 'view' not in entry.channel.send.await_args.kwargs
