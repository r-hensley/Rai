"""Warning command coverage for editable confirmation and modlog copies."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs import submod
from tests.discord_fakes import (
    make_bot,
    make_channel,
    make_context,
    make_guild,
    make_interaction,
    make_member,
)


@pytest.fixture
def warning_case(monkeypatch):
    def make_case(*, channel_mode="separate", existing_entries=()):
        guild = make_guild()
        command_channel = make_channel(guild=guild, name="commands")
        if channel_mode == "separate":
            log_channel = make_channel(
                channel_id=333333333333333333, guild=guild, name="modlog")
        elif channel_mode == "same":
            log_channel = command_channel
        else:
            assert channel_mode == "unconfigured"
            log_channel = None
        moderator = make_member(
            member_id=111111111111111112, name="Moderator", guild=guild)
        user = make_member(name="Warned user", guild=guild)
        config = {"channel": log_channel.id if log_channel else None,
                  str(user.id): list(existing_entries)}
        bot = make_bot(guilds=[guild], db={"modlog": {str(guild.id): config}})
        ctx = make_context(
            guild=guild, channel=command_channel, author=moderator, bot=bot)
        cog = submod.Submod(bot)
        sends = []

        async def safe_send(destination, content="", *, embed=None, view=None, **kwargs):
            channel = ctx.channel if destination is ctx else destination
            message = Mock(spec=discord.Message)
            message.id = 444444444444444444 + len(sends)
            message.channel = channel
            message.guild = guild
            message.embeds = [discord.Embed.from_dict(deepcopy(embed.to_dict()))] if embed else []
            message.view = view

            async def edit(**changes):
                if "embed" in changes:
                    message.embeds = [discord.Embed.from_dict(deepcopy(changes["embed"].to_dict()))]
                if "view" in changes:
                    message.view = changes["view"]
                return message

            message.edit = AsyncMock(side_effect=edit)
            sends.append(SimpleNamespace(
                destination=destination, content=content, embed=discord.Embed.from_dict(deepcopy(embed.to_dict())) if embed else None,
                view=view, message=message))
            return message

        monkeypatch.setattr(submod.utils, "safe_send", safe_send)
        monkeypatch.setattr(submod.hf.here, "bot", bot)
        monkeypatch.setattr(submod.hf, "trial_helper_check", lambda _interaction: True)
        return SimpleNamespace(
            cog=cog, ctx=ctx, user=user, guild=guild, moderator=moderator,
            log_channel=log_channel, config=config, sends=sends)

    return make_case


async def warn(case, *, reason="Original reason", silent=False, users=None):
    users = users or [case.user]
    args = " ".join(str(user.id) for user in users) + " " + reason
    if silent:
        args += " -s"
    await submod.Submod.warn.callback(case.cog, case.ctx, args=args)


def internal_sends(case):
    return [sent for sent in case.sends
            if sent.destination is case.ctx or sent.destination is case.log_channel]


def reason_in(embed):
    return "".join(field.value for field in embed.fields
                   if field.name in ("Reason", "Reason (cont.)"))


def assert_edit_button(sent):
    assert sent.view is not None, "The button must accompany the initial send"
    assert isinstance(sent.view, submod.view_utils.LogEditView)
    assert any(button.label == "Edit" for button in sent.view.children)
    assert sent.view.message is sent.message


def interaction_for(case, sent):
    return make_interaction(
        guild=case.guild, channel=sent.message.channel, user=case.moderator)


@pytest.mark.asyncio
@pytest.mark.parametrize("edit_from", ["command", "summary"])
async def test_editing_either_warning_copy_updates_both_and_saved_reason(warning_case, edit_from):
    case = warning_case()
    await warn(case)
    copies = internal_sends(case)
    assert len(copies) == 2
    for sent in copies:
        assert_edit_button(sent)
    command = next(sent for sent in copies if sent.destination is case.ctx)
    summary = next(sent for sent in copies if sent.destination is case.log_channel)
    assert command.view is not summary.view
    assert command.view.state is summary.view.state
    source = command if edit_from == "command" else summary

    await source.view.apply_edit(interaction_for(case, source), "Corrected reason")

    assert case.config[str(case.user.id)][0]["reason"] == "Corrected reason"
    for sent in copies:
        sent.message.edit.assert_awaited_once()
        assert reason_in(sent.message.embeds[0]) == "Corrected reason"
        assert sent.message.view is sent.view
        assert sent.view.current_reason == "Corrected reason"
        assert reason_in(sent.view.base_embed) == "Corrected reason"

    # Opening the other copy's modal must start with the latest shared reason.
    peer = summary if source is command else command
    interaction = interaction_for(case, peer)
    await peer.view.edit_button.callback(interaction)
    modal = interaction.response.send_modal.await_args.args[0]
    assert modal.new_reason.default == "Corrected reason"


@pytest.mark.asyncio
async def test_warning_in_modlog_channel_sends_one_editable_internal_copy(warning_case):
    case = warning_case(channel_mode="same")
    await warn(case)
    copies = internal_sends(case)
    assert len(copies) == 1
    assert copies[0].destination is case.ctx
    assert_edit_button(copies[0])

    await copies[0].view.apply_edit(interaction_for(case, copies[0]), "Updated in place")

    copies[0].message.edit.assert_awaited_once()
    assert reason_in(copies[0].message.embeds[0]) == "Updated in place"
    assert case.config[str(case.user.id)][0]["reason"] == "Updated in place"


@pytest.mark.asyncio
async def test_warning_without_modlog_channel_has_editable_confirmation(warning_case):
    case = warning_case(channel_mode="unconfigured")
    await warn(case)
    copies = internal_sends(case)
    assert len(copies) == 1
    assert copies[0].destination is case.ctx
    assert_edit_button(copies[0])

    await copies[0].view.apply_edit(interaction_for(case, copies[0]), "Local correction")

    assert reason_in(copies[0].message.embeds[0]) == "Local correction"
    assert case.config[str(case.user.id)][0]["reason"] == "Local correction"


@pytest.mark.asyncio
async def test_silent_log_arguments_create_two_editable_copies_without_dm(warning_case):
    case = warning_case()
    # ;log delegates to ;warn with a trailing -s argument.
    await warn(case, reason="Staff-only incident", silent=True)
    copies = internal_sends(case)
    assert len(copies) == len(case.sends) == 2
    for sent in copies:
        assert_edit_button(sent)
        assert reason_in(sent.embed) == "Staff-only incident"
        assert sent.embed.title == "Log *(This incident was not sent to the user)*"
    entry = case.config[str(case.user.id)][0]
    assert entry["silent"] is True
    assert entry["reason"] == "Staff-only incident"

    await copies[0].view.apply_edit(interaction_for(case, copies[0]), "Revised staff incident")

    assert entry["reason"] == "Revised staff incident"
    assert all(reason_in(sent.message.embeds[0]) == "Revised staff incident" for sent in copies)


@pytest.mark.asyncio
async def test_warned_user_dm_has_no_edit_button_and_is_not_changed(warning_case):
    case = warning_case()
    await warn(case)
    dms = [sent for sent in case.sends if sent.destination is case.user]
    assert len(dms) == 1
    dm = dms[0]
    assert dm.view is None
    assert dm.embed.title == f"Warning from {case.guild.name}"
    assert reason_in(dm.embed) == "Original reason"
    copy = internal_sends(case)[0]

    await copy.view.apply_edit(interaction_for(case, copy), "Internal correction")

    dm.message.edit.assert_not_awaited()
    assert reason_in(dm.message.embeds[0]) == "Original reason"


@pytest.mark.asyncio
async def test_editing_one_warning_does_not_change_another_warning_for_same_user(warning_case):
    earlier = {"type": "Warning", "reason": "Earlier incident"}
    case = warning_case(existing_entries=[earlier])
    await warn(case, reason="First new incident", silent=True)
    first_copies = internal_sends(case).copy()
    await warn(case, reason="Second new incident", silent=True)
    second_copies = internal_sends(case)[len(first_copies):]
    assert len(first_copies) == len(second_copies) == 2
    assert first_copies[0].view.state is not second_copies[0].view.state

    await first_copies[0].view.apply_edit(
        interaction_for(case, first_copies[0]), "Corrected first incident")

    assert [entry["reason"] for entry in case.config[str(case.user.id)]] == [
        "Earlier incident", "Corrected first incident", "Second new incident"]
    for sent in second_copies:
        sent.message.edit.assert_not_awaited()
        assert sent.view.current_reason == "Second new incident"
        assert reason_in(sent.message.embeds[0]) == "Second new incident"


@pytest.mark.asyncio
async def test_multiuser_warning_keeps_editable_copy_groups_independent(warning_case):
    case = warning_case()
    other = make_member(member_id=666666666666666666, name="Other user", guild=case.guild)
    await warn(case, users=[case.user, other], silent=True)
    copies = internal_sends(case)
    assert len(copies) == 4
    first_copies, other_copies = copies[:2], copies[2:]
    assert first_copies[0].view.state is first_copies[1].view.state
    assert other_copies[0].view.state is other_copies[1].view.state
    assert first_copies[0].view.state is not other_copies[0].view.state

    await first_copies[0].view.apply_edit(
        interaction_for(case, first_copies[0]), "Correction for first user")

    assert case.config[str(case.user.id)][0]["reason"] == "Correction for first user"
    assert case.config[str(other.id)][0]["reason"] == "Original reason"
    for sent in other_copies:
        sent.message.edit.assert_not_awaited()
        assert reason_in(sent.message.embeds[0]) == "Original reason"
