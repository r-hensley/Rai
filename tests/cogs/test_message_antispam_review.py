import asyncio
import sys
import types
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from tests.discord_fakes import (
    make_bot,
    make_channel,
    make_guild,
    make_interaction,
    make_member,
    make_message,
    make_role,
)


# cogs.message imports Rai for a type annotation, while Rai imports helper_functions.
# Supply the type during collection so this focused module can be tested in isolation.
_previous_rai_module = sys.modules.get("Rai")
if _previous_rai_module is None:
    rai_stub = types.ModuleType("Rai")
    rai_stub.Rai = type("Rai", (), {})
    sys.modules["Rai"] = rai_stub

try:
    from cogs import message as message_module  # noqa: E402
finally:
    if _previous_rai_module is None:
        sys.modules.pop("Rai", None)


TARGET_ID = 555555555555555555
STAFF_ID = 666666666666666666
SOURCE_MESSAGE_ID = 777777777777777777


def discord_forbidden(*, code: int = 50013, message: str = "Missing Permissions"):
    return discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"),
        {"code": code, "message": message},
    )


def make_response():
    return SimpleNamespace(
        send_message=AsyncMock(),
        defer=AsyncMock(),
        send_modal=AsyncMock(),
        edit_message=AsyncMock(),
    )


def make_staff_interaction(
        *,
        role_id: int | None = message_module.SP_TRIAL_ROLE_ID,
        guild_id: int = message_module.SP_SERVER_ID,
        ban: AsyncMock | None = None,
):
    roles = []
    if role_id is not None:
        roles.append(make_role(role_id=role_id))
    guild = make_guild(
        guild_id=guild_id,
        roles=roles,
        ban=ban or AsyncMock(),
    )
    staff = make_member(member_id=STAFF_ID, guild=guild, roles=roles)
    return make_interaction(
        guild=guild,
        user=staff,
        response=make_response(),
    )


def make_review_case(entries=None):
    entries = [] if entries is None else entries
    trial_role = make_role(role_id=message_module.SP_TRIAL_ROLE_ID)
    guild = make_guild(
        guild_id=message_module.SP_SERVER_ID,
        roles=[trial_role],
        ban=AsyncMock(),
    )
    target = make_member(
        member_id=TARGET_ID,
        guild=guild,
        send=AsyncMock(),
    )
    expected_timeout = discord.utils.utcnow() + timedelta(hours=1)
    current_member = SimpleNamespace(
        id=target.id,
        timed_out_until=expected_timeout,
        edit=AsyncMock(),
    )
    guild.fetch_member = AsyncMock(return_value=current_member)
    staff = make_member(
        member_id=STAFF_ID,
        guild=guild,
        roles=[trial_role],
    )
    bot = make_bot(
        db={
            "modlog": {
                str(guild.id): {
                    "channel": None,
                    str(target.id): entries,
                },
            },
        },
        guilds=[guild],
    )
    claim_key = (guild.id, target.id)
    claim_token = object()
    bot.antispam_review_claims = {claim_key: claim_token}
    incident_id = str(SOURCE_MESSAGE_ID)
    view = message_module.AntispamReviewView(
        bot,
        target,
        "Antispam: repeated message",
        incident_id,
        expected_timeout,
        claim_key,
        claim_token,
    )
    prompt_message = make_message(
        guild=guild,
        author=staff,
        edit=AsyncMock(),
    )
    view.message = prompt_message
    interaction = make_interaction(
        guild=guild,
        user=staff,
        message=prompt_message,
        response=make_response(),
    )
    return SimpleNamespace(
        bot=bot,
        guild=guild,
        target=target,
        current_member=current_member,
        staff=staff,
        claim_key=claim_key,
        claim_token=claim_token,
        incident_id=incident_id,
        expected_timeout=expected_timeout,
        view=view,
        prompt_message=prompt_message,
        interaction=interaction,
        entries=entries,
    )


@pytest.mark.parametrize(
    ("guild_id", "role_id", "higher_staff", "expected"),
    [
        (message_module.SP_SERVER_ID, message_module.SP_TRIAL_ROLE_ID, False, True),
        (message_module.SP_SERVER_ID, message_module.SP_SERVER_STAFF_ROLE_ID, False, True),
        (message_module.SP_SERVER_ID, 999999999999999999, True, True),
        (message_module.SP_SERVER_ID, 999999999999999999, False, False),
        (111111111111111111, message_module.SP_TRIAL_ROLE_ID, True, False),
    ],
)
def test_spanish_antispam_staff_permission_matrix(
        monkeypatch,
        guild_id,
        role_id,
        higher_staff,
        expected,
):
    interaction = make_staff_interaction(role_id=role_id, guild_id=guild_id)
    monkeypatch.setattr(
        message_module.hf,
        "trial_helper_check",
        lambda _ctx: higher_staff,
    )

    assert message_module.spanish_antispam_staff_check(interaction) is expected


@pytest.mark.asyncio
async def test_interaction_check_explains_denied_staff_access(monkeypatch):
    case = make_review_case()
    unauthorized = make_staff_interaction(role_id=None)
    monkeypatch.setattr(message_module.hf, "trial_helper_check", lambda _ctx: False)

    allowed = await case.view.interaction_check(unauthorized)

    assert allowed is False
    unauthorized.response.send_message.assert_awaited_once()
    assert unauthorized.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_ban_button_opens_antispam_reason_modal():
    case = make_review_case()

    await case.view.ban_user.callback(case.interaction)

    case.interaction.response.send_modal.assert_awaited_once()
    modal = case.interaction.response.send_modal.await_args.args[0]
    assert isinstance(modal, message_module.AntispamBanReasonModal)
    assert modal.reason.value == case.view.reason
    assert {(option.label, option.value) for option in modal.notification.options} == {
        ("Send DM", "dm"),
        ("Silent", "silent"),
    }


@pytest.mark.asyncio
async def test_false_alarm_removes_only_exact_tagged_mute_entry():
    older_same_reason = {
        "type": "Mute",
        "reason": "Antispam: repeated message",
        "antispam_incident_id": "older-incident",
    }
    exact_incident = {
        "type": "Mute",
        "reason": "Antispam: repeated message",
        "antispam_incident_id": str(SOURCE_MESSAGE_ID),
    }
    later_same_reason = {
        "type": "Mute",
        "reason": "Antispam: repeated message",
    }
    entries = [older_same_reason, exact_incident, later_same_reason]
    case = make_review_case(entries)

    await case.view.false_alarm.callback(case.interaction)

    case.current_member.edit.assert_awaited_once()
    assert case.current_member.edit.await_args.kwargs["timed_out_until"] is None
    assert entries == [older_same_reason, later_same_reason]
    assert case.claim_key not in case.bot.antispam_review_claims
    assert all(item.disabled for item in case.view.children)
    assert case.view.is_finished()
    result = case.prompt_message.edit.await_args.kwargs["content"]
    assert "Deleted its exact mute modlog entry" in result
    assert case.staff.mention in result


@pytest.mark.asyncio
async def test_false_alarm_does_not_delete_an_untagged_mute_entry():
    unrelated_entry = {
        "type": "Mute",
        "reason": "Antispam: repeated message",
    }
    case = make_review_case([unrelated_entry])

    await case.view.false_alarm.callback(case.interaction)

    assert case.entries == [unrelated_entry]
    result = case.prompt_message.edit.await_args.kwargs["content"]
    assert "tagged mute modlog entry was already absent" in result


@pytest.mark.asyncio
async def test_failed_untimeout_leaves_review_available_for_retry():
    exact_incident = {
        "type": "Mute",
        "reason": "Antispam: repeated message",
        "antispam_incident_id": str(SOURCE_MESSAGE_ID),
    }
    case = make_review_case([exact_incident])
    case.current_member.edit.side_effect = discord_forbidden()

    await case.view.false_alarm.callback(case.interaction)

    assert case.view.action_in_progress is False
    assert not case.view.is_finished()
    assert not any(item.disabled for item in case.view.children)
    assert case.bot.antispam_review_claims[case.claim_key] is case.claim_token
    assert case.entries == [exact_incident]
    case.interaction.followup.send.assert_awaited_once()
    assert case.interaction.followup.send.await_args.kwargs["ephemeral"] is True

    case.current_member.edit.side_effect = None
    retry = make_interaction(
        guild=case.guild,
        user=case.staff,
        message=case.prompt_message,
        response=make_response(),
    )
    await case.view.false_alarm.callback(retry)

    assert case.current_member.edit.await_count == 2
    assert case.entries == []
    assert case.claim_key not in case.bot.antispam_review_claims
    assert case.view.is_finished()


@pytest.mark.asyncio
async def test_false_alarm_refuses_to_remove_a_changed_timeout():
    exact_incident = {
        "type": "Mute",
        "reason": "Antispam: repeated message",
        "antispam_incident_id": str(SOURCE_MESSAGE_ID),
    }
    case = make_review_case([exact_incident])
    case.current_member.timed_out_until = case.expected_timeout + timedelta(hours=2)

    await case.view.false_alarm.callback(case.interaction)

    case.current_member.edit.assert_not_awaited()
    assert case.entries == [exact_incident]
    assert case.bot.antispam_review_claims[case.claim_key] is case.claim_token
    assert case.view.action_in_progress is False
    assert not case.view.is_finished()
    warning = case.interaction.followup.send.await_args.args[0]
    assert "timeout has changed" in warning


@pytest.mark.asyncio
async def test_silent_ban_succeeds_and_releases_review_claim(monkeypatch):
    case = make_review_case()
    add_to_modlog = Mock()
    monkeypatch.setattr(message_module.hf, "add_to_modlog", add_to_modlog)

    await case.view.submit_ban(case.interaction, "Repeated harassment", silent=True)

    case.interaction.response.defer.assert_awaited_once_with()
    case.target.send.assert_not_awaited()
    case.guild.ban.assert_awaited_once_with(case.target, reason="Repeated harassment")
    add_to_modlog.assert_called_once_with(
        None,
        [case.target, case.guild],
        "Ban",
        "Repeated harassment",
        True,
        None,
    )
    assert case.claim_key not in case.bot.antispam_review_claims
    assert all(item.disabled for item in case.view.children)
    assert case.view.is_finished()


@pytest.mark.asyncio
async def test_successful_ban_finishes_even_if_modlog_write_fails(monkeypatch):
    case = make_review_case()
    monkeypatch.setattr(
        message_module.hf,
        "add_to_modlog",
        Mock(side_effect=RuntimeError("database unavailable")),
    )

    await case.view.submit_ban(case.interaction, "Ban evasion", silent=True)

    case.guild.ban.assert_awaited_once()
    assert case.claim_key not in case.bot.antispam_review_claims
    assert case.view.is_finished()
    assert all(item.disabled for item in case.view.children)
    result = case.prompt_message.edit.await_args.kwargs["content"]
    assert "ban succeeded, but its modlog entry failed" in result


@pytest.mark.asyncio
async def test_ban_dm_failure_falls_back_to_silent_ban(monkeypatch):
    case = make_review_case()
    case.target.send.side_effect = discord_forbidden(
        code=50007,
        message="Cannot send messages to this user",
    )
    add_to_modlog = Mock()
    monkeypatch.setattr(message_module.hf, "add_to_modlog", add_to_modlog)

    await case.view.submit_ban(case.interaction, "Ban evasion", silent=False)

    case.guild.ban.assert_awaited_once_with(case.target, reason="Ban evasion")
    assert add_to_modlog.call_args.args[4] is True
    result = case.prompt_message.edit.await_args.kwargs["content"]
    assert "DM could not be delivered" in result
    assert case.claim_key not in case.bot.antispam_review_claims


@pytest.mark.asyncio
async def test_failed_ban_leaves_review_available_for_retry(monkeypatch):
    case = make_review_case()
    case.guild.ban.side_effect = [discord_forbidden(), None]
    add_to_modlog = Mock()
    monkeypatch.setattr(message_module.hf, "add_to_modlog", add_to_modlog)

    await case.view.submit_ban(case.interaction, "Ban evasion", silent=True)

    assert case.view.action_in_progress is False
    assert not case.view.is_finished()
    assert not any(item.disabled for item in case.view.children)
    assert case.bot.antispam_review_claims[case.claim_key] is case.claim_token
    add_to_modlog.assert_not_called()
    case.interaction.followup.send.assert_awaited_once()

    retry = make_interaction(
        guild=case.guild,
        user=case.staff,
        message=case.prompt_message,
        response=make_response(),
    )
    await case.view.submit_ban(retry, "Ban evasion", silent=True)

    assert case.guild.ban.await_count == 2
    add_to_modlog.assert_called_once()
    assert case.claim_key not in case.bot.antispam_review_claims
    assert case.view.is_finished()


@pytest.mark.asyncio
async def test_ban_submission_rechecks_staff_permission(monkeypatch):
    case = make_review_case()
    case.staff.roles = []
    monkeypatch.setattr(message_module.hf, "trial_helper_check", lambda _ctx: False)

    await case.view.submit_ban(case.interaction, "Ban evasion", silent=True)

    case.interaction.response.send_message.assert_awaited_once()
    case.interaction.response.defer.assert_not_awaited()
    case.guild.ban.assert_not_awaited()
    assert case.bot.antispam_review_claims[case.claim_key] is case.claim_token


@pytest.mark.asyncio
async def test_only_one_false_alarm_action_can_run_at_a_time():
    exact_incident = {
        "type": "Mute",
        "reason": "Antispam: repeated message",
        "antispam_incident_id": str(SOURCE_MESSAGE_ID),
    }
    case = make_review_case([exact_incident])
    edit_started = asyncio.Event()
    finish_edit = asyncio.Event()

    async def blocked_edit(**_kwargs):
        edit_started.set()
        await finish_edit.wait()

    case.current_member.edit.side_effect = blocked_edit
    first_action = asyncio.create_task(
        case.view.false_alarm.callback(case.interaction)
    )
    await edit_started.wait()

    second = make_interaction(
        guild=case.guild,
        user=case.staff,
        message=case.prompt_message,
        response=make_response(),
    )
    await case.view.false_alarm.callback(second)

    case.current_member.edit.assert_awaited_once()
    second.response.send_message.assert_awaited_once()
    assert "already being handled" in second.response.send_message.await_args.args[0]

    finish_edit.set()
    await first_action
    assert case.entries == []


@pytest.mark.asyncio
async def test_timeout_disables_review_and_releases_its_claim():
    case = make_review_case()

    await case.view.on_timeout()

    assert case.claim_key not in case.bot.antispam_review_claims
    assert all(item.disabled for item in case.view.children)
    assert case.view.is_finished()
    case.prompt_message.edit.assert_awaited_once()
    assert "no automatic change" in case.prompt_message.edit.await_args.kwargs["content"]


@pytest.mark.asyncio
async def test_timeout_does_not_release_a_replacement_claim():
    case = make_review_case()
    replacement_token = object()
    case.bot.antispam_review_claims[case.claim_key] = replacement_token

    await case.view.on_timeout()

    assert case.bot.antispam_review_claims[case.claim_key] is replacement_token


@pytest.mark.asyncio
async def test_review_setup_failure_does_not_clear_a_preexisting_timeout():
    incidents_channel = make_channel(channel_id=message_module.SP_INCIDENTS_CHANNEL_ID)
    guild = make_guild(
        guild_id=message_module.SP_SERVER_ID,
        channels=[incidents_channel],
    )
    existing_timeout = discord.utils.utcnow() + timedelta(days=1)
    target = make_member(
        member_id=TARGET_ID,
        guild=guild,
        timed_out_until=existing_timeout,
        timeout=AsyncMock(),
        edit=AsyncMock(),
    )
    claim_key = (guild.id, target.id)
    claim_token = object()
    bot = make_bot(
        db={"modlog": {str(guild.id): {"channel": None, str(target.id): []}}},
        guilds=[guild],
        antispam_review_claims={claim_key: claim_token},
    )
    source_message = make_message(
        message_id=SOURCE_MESSAGE_ID,
        author=target,
        guild=guild,
        channel=incidents_channel,
        get_ctx=AsyncMock(side_effect=AttributeError("context unavailable")),
    )

    view = await message_module.create_spanish_antispam_review(
        bot,
        source_message,
        "Antispam: repeated message",
        incidents_channel,
        claim_key,
        claim_token,
    )

    assert view is None
    target.timeout.assert_not_awaited()
    target.edit.assert_not_awaited()
    assert target.timed_out_until == existing_timeout
    assert claim_key not in bot.antispam_review_claims


@pytest.mark.asyncio
async def test_existing_staff_timeout_is_left_unchanged():
    incidents_channel = make_channel(
        channel_id=message_module.SP_INCIDENTS_CHANNEL_ID,
        send=AsyncMock(),
    )
    guild = make_guild(
        guild_id=message_module.SP_SERVER_ID,
        channels=[incidents_channel],
    )
    guild.me = make_member(member_id=333333333333333333, guild=guild, bot=True)
    existing_timeout = discord.utils.utcnow() + timedelta(days=1)
    target = make_member(
        member_id=TARGET_ID,
        guild=guild,
        timeout=AsyncMock(),
        edit=AsyncMock(),
    )
    current_member = SimpleNamespace(
        id=target.id,
        timed_out_until=existing_timeout,
        edit=AsyncMock(),
    )
    guild.fetch_member = AsyncMock(return_value=current_member)
    claim_key = (guild.id, target.id)
    claim_token = object()
    bot = make_bot(
        db={"modlog": {str(guild.id): {"channel": None, str(target.id): []}}},
        guilds=[guild],
        antispam_review_claims={claim_key: claim_token},
    )
    source_message = make_message(
        message_id=SOURCE_MESSAGE_ID,
        author=target,
        guild=guild,
        channel=incidents_channel,
        get_ctx=AsyncMock(),
        ctx=SimpleNamespace(author=target, guild=guild),
    )

    view = await message_module.create_spanish_antispam_review(
        bot,
        source_message,
        "Antispam: repeated message",
        incidents_channel,
        claim_key,
        claim_token,
    )

    assert view is None
    target.timeout.assert_not_awaited()
    target.edit.assert_not_awaited()
    current_member.edit.assert_not_awaited()
    assert current_member.timed_out_until == existing_timeout
    assert claim_key not in bot.antispam_review_claims
    assert "already have an active timeout" in incidents_channel.send.await_args.args[0]


@pytest.mark.asyncio
async def test_failed_review_rollback_keeps_log_and_timed_claim():
    guild = make_guild(guild_id=message_module.SP_SERVER_ID)
    expected_timeout = discord.utils.utcnow() + timedelta(hours=1)
    target = make_member(
        member_id=TARGET_ID,
        guild=guild,
    )
    current_member = SimpleNamespace(
        id=target.id,
        timed_out_until=expected_timeout,
        edit=AsyncMock(side_effect=discord_forbidden()),
    )
    guild.fetch_member = AsyncMock(return_value=current_member)
    incident_entry = {
        "type": "Mute",
        "reason": "Antispam",
        "antispam_incident_id": str(SOURCE_MESSAGE_ID),
    }
    claim_key = (guild.id, target.id)
    claim_token = object()
    bot = make_bot(
        db={
            "modlog": {
                str(guild.id): {
                    "channel": None,
                    str(target.id): [incident_entry],
                },
            },
        },
        guilds=[guild],
        antispam_review_claims={claim_key: claim_token},
    )

    cleared, status = await message_module.rollback_unposted_antispam_review(
        bot,
        target,
        incident_entry,
        expected_timeout,
        claim_key,
        claim_token,
    )

    assert cleared is False
    assert "couldn't remove" in status
    assert bot.db["modlog"][str(guild.id)][str(target.id)] == [incident_entry]
    assert bot.antispam_review_claims[claim_key] is claim_token


@pytest.mark.asyncio
async def test_unpostable_review_rolls_back_timeout_log_and_claim(monkeypatch):
    incidents_channel = make_channel(
        channel_id=message_module.SP_INCIDENTS_CHANNEL_ID,
        send=AsyncMock(side_effect=discord_forbidden()),
    )
    guild = make_guild(
        guild_id=message_module.SP_SERVER_ID,
        channels=[incidents_channel],
    )
    guild.me = make_member(member_id=333333333333333333, guild=guild, bot=True)
    target = make_member(
        member_id=TARGET_ID,
        guild=guild,
        send=AsyncMock(),
        timeout=AsyncMock(),
    )
    pre_timeout_member = SimpleNamespace(
        id=target.id,
        timed_out_until=None,
        edit=AsyncMock(),
    )
    current_member = SimpleNamespace(
        id=target.id,
        timed_out_until=None,
        edit=AsyncMock(),
    )

    async def apply_timeout(until, **_kwargs):
        current_member.timed_out_until = until

    target.timeout.side_effect = apply_timeout
    guild.fetch_member = AsyncMock(
        side_effect=[pre_timeout_member, current_member, current_member],
    )
    incident_entry = {"type": "Mute", "reason": "Antispam"}
    claim_key = (guild.id, target.id)
    claim_token = object()
    ctx = SimpleNamespace(
        author=target,
        guild=guild,
    )
    source_message = make_message(
        message_id=SOURCE_MESSAGE_ID,
        author=target,
        guild=guild,
        channel=incidents_channel,
        get_ctx=AsyncMock(),
        ctx=ctx,
    )
    bot = make_bot(
        db={
            "modlog": {
                str(guild.id): {
                    "channel": incidents_channel.id,
                    str(target.id): [],
                },
            },
        },
        guilds=[guild],
        antispam_review_claims={claim_key: claim_token},
    )
    modlog_config = bot.db["modlog"][str(guild.id)]

    def append_modlog(*_args, **_kwargs):
        modlog_config[str(target.id)].append(incident_entry)
        return modlog_config

    monkeypatch.setattr(
        message_module.hf,
        "add_to_modlog",
        Mock(side_effect=append_modlog),
    )

    view = await message_module.create_spanish_antispam_review(
        bot,
        source_message,
        "Antispam: repeated message",
        incidents_channel,
        claim_key,
        claim_token,
    )

    assert view is None
    target.timeout.assert_awaited_once()
    current_member.edit.assert_awaited_once()
    assert bot.db["modlog"][str(guild.id)][str(target.id)] == []
    assert claim_key not in bot.antispam_review_claims


@pytest.mark.asyncio
async def test_mismatched_post_write_timeout_opens_no_review_and_keeps_claim(monkeypatch):
    incidents_channel = make_channel(
        channel_id=message_module.SP_INCIDENTS_CHANNEL_ID,
        send=AsyncMock(),
    )
    guild = make_guild(
        guild_id=message_module.SP_SERVER_ID,
        channels=[incidents_channel],
    )
    guild.me = make_member(member_id=333333333333333333, guild=guild, bot=True)
    target = make_member(
        member_id=TARGET_ID,
        guild=guild,
        timeout=AsyncMock(),
    )
    pre_timeout_member = SimpleNamespace(id=target.id, timed_out_until=None, edit=AsyncMock())
    current_member = SimpleNamespace(id=target.id, timed_out_until=None, edit=AsyncMock())

    async def apply_different_timeout(until, **_kwargs):
        current_member.timed_out_until = until + timedelta(minutes=5)

    target.timeout.side_effect = apply_different_timeout
    guild.fetch_member = AsyncMock(
        side_effect=[pre_timeout_member, current_member, current_member],
    )
    claim_key = (guild.id, target.id)
    claim_token = object()
    bot = make_bot(
        db={"modlog": {str(guild.id): {"channel": None, str(target.id): []}}},
        guilds=[guild],
        antispam_review_claims={claim_key: claim_token},
    )
    source_message = make_message(
        message_id=SOURCE_MESSAGE_ID,
        author=target,
        guild=guild,
        channel=incidents_channel,
        get_ctx=AsyncMock(),
        ctx=SimpleNamespace(author=target, guild=guild),
    )
    add_to_modlog = Mock()
    monkeypatch.setattr(message_module.hf, "add_to_modlog", add_to_modlog)

    view = await message_module.create_spanish_antispam_review(
        bot,
        source_message,
        "Antispam: repeated message",
        incidents_channel,
        claim_key,
        claim_token,
    )

    assert view is None
    add_to_modlog.assert_not_called()
    current_member.edit.assert_not_awaited()
    assert bot.antispam_review_claims[claim_key] is claim_token
    incidents_channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_review_claim_suppresses_duplicate_sanction():
    incidents_channel = make_channel(channel_id=message_module.SP_INCIDENTS_CHANNEL_ID)
    source_channel = make_channel(channel_id=222222222222222223)
    guild = make_guild(
        guild_id=message_module.SP_SERVER_ID,
        channels=[incidents_channel, source_channel],
    )
    target = make_member(
        member_id=TARGET_ID,
        guild=guild,
        joined_at=discord.utils.utcnow() - timedelta(days=30),
    )
    source_message = make_message(
        message_id=SOURCE_MESSAGE_ID,
        content="repeated message",
        author=target,
        channel=source_channel,
        guild=guild,
        get_ctx=AsyncMock(),
    )
    claim_key = (guild.id, target.id)
    bot = make_bot(
        db={
            "antispam": {
                str(guild.id): {
                    "enable": True,
                    "ignored": [],
                    "message_threshold": 1,
                    "time_threshold": 10,
                    "action": "mute",
                    "ban_override": 0,
                    "exempt_roles": [],
                },
            },
        },
        guilds=[guild],
        antispam_review_claims={claim_key: object()},
    )

    await message_module.Message.antispam_check.__wrapped__(
        SimpleNamespace(bot=bot),
        source_message,
    )

    source_message.get_ctx.assert_not_awaited()
    source_message.delete.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_review_channel_resolver_uses_configured_mod_channel_fallback():
    fallback_channel = make_channel(
        channel_id=222222222222222225,
        send=AsyncMock(),
    )
    guild = make_guild(
        guild_id=message_module.SP_SERVER_ID,
        channels=[fallback_channel],
        fetch_channel=AsyncMock(side_effect=discord_forbidden()),
    )
    bot = make_bot(
        db={"mod_channel": {str(guild.id): fallback_channel.id}},
        guilds=[guild],
    )

    channel = await message_module.resolve_spanish_antispam_review_channel(bot, guild)

    assert channel is fallback_channel
    guild.fetch_channel.assert_awaited_once_with(message_module.SP_INCIDENTS_CHANNEL_ID)


@pytest.mark.asyncio
async def test_review_channel_resolver_rejects_cross_guild_fallback():
    spanish_guild = make_guild(
        guild_id=message_module.SP_SERVER_ID,
        fetch_channel=AsyncMock(side_effect=discord_forbidden()),
    )
    other_guild = make_guild(guild_id=111111111111111111)
    foreign_channel = make_channel(
        channel_id=222222222222222226,
        guild=other_guild,
        send=AsyncMock(),
    )
    bot = make_bot(
        db={"mod_channel": {str(spanish_guild.id): foreign_channel.id}},
        guilds=[spanish_guild, other_guild],
    )

    channel = await message_module.resolve_spanish_antispam_review_channel(
        bot,
        spanish_guild,
    )

    assert channel is None


@pytest.mark.asyncio
async def test_spanish_antispam_core_mutes_and_tags_exact_new_modlog_entry(monkeypatch):
    incidents_channel = make_channel(
        channel_id=message_module.SP_INCIDENTS_CHANNEL_ID,
        send=AsyncMock(),
    )
    source_channel = make_channel(channel_id=222222222222222223)
    guild = make_guild(
        guild_id=message_module.SP_SERVER_ID,
        channels=[incidents_channel, source_channel],
    )
    guild.me = make_member(
        member_id=333333333333333333,
        name="Rai",
        guild=guild,
        bot=True,
    )
    target = make_member(
        member_id=TARGET_ID,
        guild=guild,
        joined_at=discord.utils.utcnow() - timedelta(days=30),
        ban=AsyncMock(),
        kick=AsyncMock(),
        send=AsyncMock(),
        timeout=AsyncMock(),
    )
    pre_timeout_member = SimpleNamespace(
        id=target.id,
        timed_out_until=None,
        edit=AsyncMock(),
    )
    current_member = SimpleNamespace(
        id=target.id,
        timed_out_until=None,
        edit=AsyncMock(),
    )

    async def apply_timeout(until, **_kwargs):
        current_member.timed_out_until = until

    target.timeout.side_effect = apply_timeout
    guild.fetch_member = AsyncMock(
        side_effect=[pre_timeout_member, current_member],
    )
    old_entry = {
        "type": "Mute",
        "reason": "Antispam: repeated message",
    }
    new_entry = {
        "type": "Mute",
        "reason": "Antispam: repeated message",
    }
    entries = [old_entry]

    ctx = SimpleNamespace(author=target, guild=guild)
    source_message = make_message(
        message_id=SOURCE_MESSAGE_ID,
        content="repeated message",
        author=target,
        channel=source_channel,
        guild=guild,
        get_ctx=AsyncMock(),
        ctx=ctx,
    )
    prompt_message = make_message(
        message_id=888888888888888888,
        author=guild.me,
        channel=incidents_channel,
        guild=guild,
        edit=AsyncMock(),
    )
    incidents_channel.send.return_value = prompt_message
    bot = make_bot(
        db={
            "antispam": {
                str(guild.id): {
                    "enable": True,
                    "ignored": [],
                    "message_threshold": 1,
                    "time_threshold": 10,
                    # Spanish antispam must use a reversible timeout regardless
                    # of the configured punishment used by other servers.
                    "action": "ban",
                    "ban_override": 0,
                    "exempt_roles": [],
                },
            },
            "modlog": {
                str(guild.id): {
                    "channel": incidents_channel.id,
                    str(target.id): entries,
                },
            },
        },
        guilds=[guild],
        antispam_review_claims={},
    )
    modlog_config = bot.db["modlog"][str(guild.id)]

    def append_modlog(*_args, **_kwargs):
        entries.append(new_entry)
        return modlog_config

    monkeypatch.setattr(
        message_module.hf,
        "add_to_modlog",
        Mock(side_effect=append_modlog),
    )
    cog = SimpleNamespace(bot=bot)

    await message_module.Message.antispam_check.__wrapped__(cog, source_message)

    source_message.get_ctx.assert_awaited_once_with()
    target.timeout.assert_awaited_once()
    assert target.timeout.await_args.args[0] == current_member.timed_out_until
    assert target.timeout.await_args.kwargs["reason"].startswith("Antispam:")
    assert entries == [old_entry, new_entry]
    assert "antispam_incident_id" not in old_entry
    assert new_entry["antispam_incident_id"] == str(source_message.id)
    assert new_entry["antispam_timeout_until"] == current_member.timed_out_until.isoformat()
    target.ban.assert_not_awaited()
    target.kick.assert_not_awaited()
    source_message.delete.assert_awaited_once_with()
    incidents_channel.send.assert_awaited_once()

    view = incidents_channel.send.await_args.kwargs["view"]
    assert isinstance(view, message_module.AntispamReviewView)
    assert view.message is prompt_message
    assert view.expected_timeout == current_member.timed_out_until
    claim_key = (guild.id, target.id)
    assert bot.antispam_review_claims[claim_key] is view.claim_token
