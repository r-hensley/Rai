"""Mute/unmute reason editing through the real command and permission paths."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest
from discord.ext import commands
from discord.ext.commands.view import StringView

from cogs import channel_mods
from cogs.utils import helper_functions as hf
from tests.discord_fakes import (
    make_bot, make_channel, make_guild, make_interaction, make_member, make_message, make_role,
)


def reason_in(embed):
    return ''.join(f.value for f in embed.fields if f.name.startswith('Reason'))


@pytest.fixture
def timeout_case(monkeypatch):
    def build(*, mode='separate', timed_out=True, automatic=False):
        guild = make_guild(guild_id=123456789012345678)
        channel = make_channel(guild=guild, category=SimpleNamespace(id=1))
        channel.permissions_for = Mock(return_value=discord.Permissions(view_channel=True))
        if mode == 'separate':
            summary = make_channel(channel_id=333333333333333333, guild=guild)
            summary.permissions_for = Mock(return_value=discord.Permissions(view_channel=True))
        else:
            summary = channel if mode == 'same' else None
        mod_role = make_role(role_id=555555555555555555, guild=guild)
        helper_role = make_role(role_id=666666666666666666, guild=guild)
        bot_user = make_member(member_id=777777777777777777, guild=guild, bot=True)
        guild.me = bot_user
        author = bot_user if automatic else make_member(
            member_id=111111111111111111, guild=guild, roles=[mod_role])
        target = make_member(
            member_id=222222222222222222, guild=guild,
            timeout=AsyncMock(), edit=AsyncMock(), is_timed_out=Mock(return_value=timed_out),
        )
        bot = make_bot(user=bot_user, guilds=[guild], db={
            'modlog': {str(guild.id): {'channel': summary.id if summary else None}},
            'mod_channel': {str(guild.id): channel.id},
            'mod_role': {str(guild.id): {'id': mod_role.id}},
            'submod_role': {str(guild.id): {'id': []}},
            'helper_role': {str(guild.id): {'id': helper_role.id}},
            'voicemod': {},
        })
        ctx = commands.Context(
            message=make_message(guild=guild, channel=channel, author=author, _state=None),
            bot=bot, view=StringView(''),
        )
        cog = channel_mods.ChannelMods(bot)
        sends = []

        async def send(destination, content='', *, embed=None, view=None, **kwargs):
            message = Mock(spec=discord.Message)
            message.id = 444444444444444444 + len(sends)
            message.view = view
            message.embeds = [discord.Embed.from_dict(deepcopy(embed.to_dict()))] if embed else []

            async def edit(**changes):
                message.embeds = [discord.Embed.from_dict(deepcopy(changes['embed'].to_dict()))]
                return message

            message.edit = AsyncMock(side_effect=edit)
            sends.append(SimpleNamespace(destination=destination, content=content, message=message))
            return message

        monkeypatch.setattr(hf.here, 'bot', bot)
        monkeypatch.setattr(channel_mods.utils, 'safe_send', send)
        return SimpleNamespace(
            guild=guild, channel=channel, summary=summary, ctx=ctx, cog=cog, bot=bot,
            author=author, target=target, helper_role=helper_role, sends=sends,
        )
    return build


def interaction(case, *, user=None, summary=False):
    data = make_interaction(guild=case.guild, channel=case.summary if summary else case.channel,
                            user=user or case.author)
    result = Mock(spec=discord.Interaction)
    for key, value in vars(data).items():
        setattr(result, key, value)
    return result


async def run_action(case, action, reason='Original reason'):
    if action == 'mute':
        await channel_mods.ChannelMods.mute.callback(
            case.cog, case.ctx, args=f'1h {case.target.id} {reason}')
    else:
        return await channel_mods.ChannelMods.unmute.callback(case.cog, case.ctx, str(case.target.id))


def copies(case):
    return [s.message for s in case.sends if s.message.view is not None]


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['mute', 'unmute'])
@pytest.mark.parametrize('source', [0, 1])
async def test_either_copy_updates_exact_saved_entry_and_both_embeds(timeout_case, action, source):
    case = timeout_case()
    entries = case.bot.db['modlog'][str(case.guild.id)].setdefault(str(case.target.id), [])
    entries.append({'reason': 'Earlier record'})
    result = await run_action(case, action)
    messages = copies(case)
    assert len(messages) == 2
    assert messages[0].view is not messages[1].view
    assert messages[0].view.state is messages[1].view.state
    if action == 'unmute':
        assert result is True
        assert messages[0].view.current_reason == ''
    before_length = entries[-1]['length']
    await messages[source].view.apply_edit(interaction(case, summary=bool(source)), 'Corrected reason')
    assert all(reason_in(m.embeds[0]) == 'Corrected reason' for m in messages)
    assert entries[-1]['reason'] == 'Corrected reason'
    assert entries[-1]['length'] == before_length
    assert entries[0]['reason'] == 'Earlier record'
    if action == 'mute':
        case.target.timeout.assert_awaited_once()
        dm = next(s.message for s in case.sends if s.destination is case.target)
        assert dm.view is None
        dm.edit.assert_not_awaited()
        assert reason_in(dm.embeds[0]) == 'Original reason'
    else:
        case.target.edit.assert_awaited_once_with(timed_out_until=None)


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['mute', 'unmute'])
@pytest.mark.parametrize('mode', ['same', 'unconfigured'])
async def test_single_copy_when_summary_is_same_channel_or_unconfigured(timeout_case, action, mode):
    case = timeout_case(mode=mode)
    await run_action(case, action)
    assert len(copies(case)) == 1
    await copies(case)[0].view.apply_edit(interaction(case), 'Local correction')
    assert reason_in(copies(case)[0].embeds[0]) == 'Local correction'


@pytest.mark.asyncio
async def test_mute_helper_can_edit_from_summary_but_loses_access_when_role_removed(timeout_case):
    case = timeout_case()
    case.author.roles[:] = [case.helper_role]
    await run_action(case, 'mute')
    view = copies(case)[1].view
    opening = interaction(case, summary=True)
    await view.edit_button.callback(opening)
    opening.response.send_modal.assert_awaited_once()
    case.author.roles.clear()
    confirmation = interaction(case, summary=True)
    await view.apply_edit(confirmation, 'Denied')
    assert view.current_reason == 'Original reason'
    confirmation.response.send_message.assert_awaited_once()
    assert case.ctx.author is case.author
    assert case.ctx.channel is case.channel


@pytest.mark.asyncio
async def test_mute_helper_needs_current_access_to_original_channel(timeout_case):
    case = timeout_case()
    case.author.roles[:] = [case.helper_role]
    await run_action(case, 'mute')
    case.channel.permissions_for.return_value = discord.Permissions.none()
    view = copies(case)[1].view
    assert not await view.check_edit_permission(interaction(case, summary=True))


@pytest.mark.asyncio
async def test_unmute_edit_requires_admin_policy_even_for_helpers(timeout_case):
    case = timeout_case()
    await run_action(case, 'unmute')
    case.author.roles[:] = [case.helper_role]
    assert not await copies(case)[0].view.check_edit_permission(interaction(case))


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['forbidden', 'already_unmuted', 'missing'])
async def test_failed_unmute_has_no_success_embed_edit_button_or_record(timeout_case, failure):
    case = timeout_case(timed_out=failure != 'already_unmuted')
    if failure == 'forbidden':
        case.target.edit.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'Denied')
    elif failure == 'missing':
        case.guild.get_member = Mock(return_value=None)
    assert await run_action(case, 'unmute') is None
    assert not copies(case)
    assert not any(s.message.embeds for s in case.sends)
    assert str(case.target.id) not in case.bot.db['modlog'][str(case.guild.id)]


@pytest.mark.asyncio
async def test_long_mute_reason_fits_fields_and_can_be_edited(timeout_case):
    case = timeout_case()
    await run_action(case, 'mute', 'x' * 2048)
    for message in copies(case):
        assert all(len(f.value) <= 1024 for f in message.embeds[0].fields if f.name.startswith('Reason'))
        assert reason_in(message.embeds[0]) == 'x' * 2048
    await copies(case)[0].view.apply_edit(interaction(case), 'Short reason')
    assert all(reason_in(m.embeds[0]) == 'Short reason' for m in copies(case))


@pytest.mark.asyncio
async def test_automatic_unmute_keeps_background_contract_without_messages(timeout_case):
    case = timeout_case(automatic=True)
    assert await run_action(case, 'unmute') is True
    assert not case.sends
    assert case.bot.db['modlog'][str(case.guild.id)][str(case.target.id)][0]['type'] == 'Unmute'


@pytest.mark.asyncio
async def test_multiuser_mute_keeps_records_and_edits_independent(timeout_case):
    case = timeout_case()
    other = make_member(member_id=888888888888888888, guild=case.guild, timeout=AsyncMock())
    await channel_mods.ChannelMods.mute.callback(
        case.cog, case.ctx, args=f'1h {case.target.id} {other.id} Original reason')
    first, second = copies(case)[:2], copies(case)[2:]
    assert len(first) == len(second) == 2
    assert first[0].view.state is not second[0].view.state
    await first[0].view.apply_edit(interaction(case), 'First user correction')
    assert all(reason_in(m.embeds[0]) == 'Original reason' for m in second)
    assert case.bot.db['modlog'][str(case.guild.id)][str(other.id)][0]['reason'] == 'Original reason'


@pytest.mark.asyncio
async def test_failed_mute_has_no_record_or_edit_button(timeout_case):
    case = timeout_case()
    case.target.timeout.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'Denied')
    await run_action(case, 'mute')
    assert not copies(case)
    assert str(case.target.id) not in case.bot.db['modlog'][str(case.guild.id)]
