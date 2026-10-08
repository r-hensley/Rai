"""Single-user ban confirmation and event-log editing."""

import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs import logger, submod
from cogs.utils import helper_functions as hf, views
from tests.discord_fakes import (
    make_bot, make_channel, make_context, make_guild, make_interaction, make_member,
)


def reason_in(embed):
    return "".join(f.value for f in embed.fields if f.name.startswith("Reason"))


@pytest.fixture
def ban_case(monkeypatch):
    def make_case(*, count=1, fails=False, confirmed=True, early_event=False, timed=False,
                  logging_enabled=True):
        guild = make_guild(guild_id=submod.SP_SERV_ID)
        guild.me = make_member(member_id=999999999999999999, guild=guild, top_role=100)
        channel = make_channel(guild=guild)
        summary_channel = make_channel(channel_id=333333333333333333, guild=guild)
        author = make_member(member_id=111111111111111111, guild=guild)
        targets = [make_member(
            member_id=222222222222222222 + i, guild=guild, top_role=1,
            joined_at=discord.utils.utcnow() - timedelta(days=5),
        ) for i in range(count)]
        bot = make_bot(guilds=[guild], recently_removed_members={}, db={
            'modlog': {str(guild.id): {'channel': summary_channel.id}},
            'bans': {str(guild.id): {'enable': logging_enabled, 'channel': summary_channel.id}},
        })
        ctx = make_context(guild=guild, channel=channel, author=author, bot=bot, user=author)
        cog = submod.Submod(bot)
        log_cog = logger.Logger.__new__(logger.Logger)
        log_cog.bot = bot
        log_cog.make_ban_embed = AsyncMock(return_value=(
            discord.Embed(description='Original ban summary'), discord.Embed(),
        ))
        sends, events = [], []

        async def send(destination, content=None, *, embed=None, view=None, **kwargs):
            message = Mock(spec=discord.Message)
            message.id = 444444444444444444 + len(sends)
            message.content, message.view = content, view
            message.embeds = [discord.Embed.from_dict(deepcopy(embed.to_dict()))] if embed else []

            async def edit(**changes):
                if 'embed' in changes:
                    message.embeds = [discord.Embed.from_dict(deepcopy(changes['embed'].to_dict()))]
                for name in ('content', 'view'):
                    if name in changes:
                        setattr(message, name, changes[name])
                return message

            message.edit = AsyncMock(side_effect=edit)
            sends.append(SimpleNamespace(destination=destination, message=message))
            return message

        async def ctx_send(*args, **kwargs):
            return await send(ctx, *args, **kwargs)

        async def decide(view):
            view.confirmed, view.silent = confirmed, True

        async def ban(target, **kwargs):
            if fails:
                raise discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'no permission')
            if early_event:
                events.append(asyncio.create_task(log_cog.on_member_ban(guild, target)))
                await asyncio.sleep(0)
                log_cog.make_ban_embed.assert_not_awaited()

        ctx.send = AsyncMock(side_effect=ctx_send)
        guild.ban = AsyncMock(side_effect=ban)
        monkeypatch.setattr(submod.Submod.BanConfirmationView, 'wait', decide)
        monkeypatch.setattr(submod.utils, 'safe_send', send)
        monkeypatch.setattr(hf.here, 'bot', bot)
        monkeypatch.setattr(hf, 'admin_check', lambda _: True)
        monkeypatch.setattr(hf, 'is_muted', lambda *_: False)
        monkeypatch.setattr(hf, 'suspected_spam_activity_flag', AsyncMock(return_value=False))
        monkeypatch.setattr(hf, 'excessive_dm_activity', AsyncMock(return_value=False))
        monkeypatch.setattr(hf, 'args_discriminator', lambda _: SimpleNamespace(
            user_ids=[t.id for t in targets], reason='Original ban reason',
            length=[0, 2] if timed else None, time_string='2026/10/09 00:00 UTC',
        ))
        return SimpleNamespace(
            cog=cog, logger=log_cog, bot=bot, ctx=ctx, guild=guild, targets=targets,
            sends=sends, events=events, summary_channel=summary_channel,
        )
    return make_case


async def run_ban(case):
    await submod.Submod.prefix_cmd_ban.callback(case.cog, case.ctx, args_in='parsed in fixture')
    if case.events:
        await asyncio.wait_for(asyncio.gather(*case.events), timeout=2)


@pytest.mark.asyncio
@pytest.mark.parametrize('early_event', [False, True])
@pytest.mark.parametrize('edit_from', ['confirmation', 'summary'])
async def test_single_ban_edits_both_messages_and_record(ban_case, early_event, edit_from):
    case = ban_case(early_event=early_event, timed=True)
    await run_ban(case)
    if not early_event:
        await case.logger.on_member_ban(case.guild, case.targets[0])
    confirmation, summary = [item.message for item in case.sends]
    assert isinstance(confirmation.view, views.BanLogEditView)
    assert isinstance(summary.view, views.BanLogEditView)
    assert confirmation.view is not summary.view
    assert confirmation.view.state is summary.view.state
    assert confirmation.content is None
    source = confirmation if edit_from == 'confirmation' else summary
    interaction = make_interaction(guild=case.guild, user=case.ctx.author, channel=case.ctx.channel)

    await source.view.apply_edit(interaction, 'Corrected reason')

    assert reason_in(confirmation.embeds[0]) == reason_in(summary.embeds[0]) == 'Corrected reason'
    entry = case.bot.db['modlog'][str(case.guild.id)][str(case.targets[0].id)][0]
    assert entry['reason'] == 'Corrected reason'
    assert entry['length'] == '0d2h'
    assert case.bot.db['bans'][str(case.guild.id)]['timed_bans'][str(case.targets[0].id)] == '2026/10/09 00:00 UTC'
    assert summary.embeds[0].fields[1].value == '0d2h'
    assert not case.bot.pending_ban_edits
    case.guild.ban.assert_awaited_once()


@pytest.mark.asyncio
async def test_late_summary_uses_reason_already_edited_in_confirmation(ban_case):
    case = ban_case()
    await run_ban(case)
    confirmation = case.sends[0].message
    await confirmation.view.apply_edit(
        make_interaction(guild=case.guild, user=case.ctx.author, channel=case.ctx.channel), 'Early correction',
    )

    await case.logger.on_member_ban(case.guild, case.targets[0])

    summary = case.sends[-1].message
    assert reason_in(summary.embeds[0]) == 'Early correction'
    assert summary.view.state is confirmation.view.state


@pytest.mark.asyncio
@pytest.mark.parametrize('logging_enabled', [False, True])
async def test_bulk_bans_keep_existing_ui(ban_case, logging_enabled):
    case = ban_case(count=2, logging_enabled=logging_enabled)
    await run_ban(case)
    for target in case.targets:
        await case.logger.on_member_ban(case.guild, target)
    assert all(item.message.view is None for item in case.sends)
    assert not getattr(case.bot, 'pending_ban_edits', {})
    assert case.guild.ban.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('fails,confirmed', [(True, True), (False, False)])
async def test_failed_or_cancelled_ban_has_no_edit_button_or_saved_ban(ban_case, fails, confirmed):
    case = ban_case(fails=fails, confirmed=confirmed)
    await run_ban(case)
    assert all(item.message.view is None for item in case.sends)
    assert str(case.targets[0].id) not in case.bot.db['modlog'][str(case.guild.id)]
    for state in getattr(case.bot, 'pending_ban_edits', {}).values():
        assert state.modlog_entry is None
        assert not state.lock.locked()


@pytest.mark.asyncio
async def test_confirmation_still_editable_when_ban_logging_disabled(ban_case):
    case = ban_case(logging_enabled=False)
    await run_ban(case)
    await case.logger.on_member_ban(case.guild, case.targets[0])
    assert len(case.sends) == 1
    assert isinstance(case.sends[0].message.view, views.BanLogEditView)
    assert not case.bot.pending_ban_edits


@pytest.mark.asyncio
async def test_ban_editor_requires_ban_staff_and_rechecks_at_confirmation(monkeypatch):
    role = object()
    guild = SimpleNamespace(get_role=lambda _: role)
    user = SimpleNamespace(roles=[role])
    interaction = SimpleNamespace(
        guild=guild, user=user, response=SimpleNamespace(send_message=AsyncMock(), send_modal=AsyncMock()),
    )
    monkeypatch.setattr(hf, 'admin_check', lambda _: False)
    monkeypatch.setattr(hf, 'submod_check', lambda _: True)
    monkeypatch.setattr(hf, 'trial_helper_check', lambda _: True)
    state = views.BanLogEditState(base_embed=discord.Embed(), current_reason='old', helper_role_id=1)
    view = views.BanLogEditView(state=state)
    await view.edit_button.callback(interaction)
    interaction.response.send_modal.assert_awaited_once()
    user.roles.clear()

    await view.apply_edit(interaction, 'unauthorized edit')

    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.await_args.kwargs['ephemeral'] is True
    assert state.current_reason == 'old'
    # A helper cannot edit bans outside the original new-member eligibility.
    user.roles.append(role)
    state.helper_role_id = None
    assert not await view.check_edit_permission(interaction)
