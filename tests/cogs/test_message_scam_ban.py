import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest


# cogs.message imports Rai for a type annotation, while Rai imports helper_functions.
# Supply the type during collection so this focused module can be tested in isolation.
_previous_rai_module = sys.modules.get("Rai")
if _previous_rai_module is None:
    rai_stub = types.ModuleType("Rai")
    rai_stub.Rai = type("Rai", (), {})
    sys.modules["Rai"] = rai_stub

from cogs.utils import helper_functions as hf  # noqa: E402

_previous_bot = hf.here.bot
hf.here.bot = SimpleNamespace(profiling_decorators=set())
try:
    from cogs import message as message_module  # noqa: E402
finally:
    hf.here.bot = _previous_bot
    if _previous_rai_module is None:
        sys.modules.pop("Rai", None)


def make_target():
    return SimpleNamespace(id=42, mention="<@42>", send=AsyncMock(), edit=AsyncMock())


def make_interaction():
    guild = SimpleNamespace(
        id=1,
        name="Spanish-English Language Exchange",
        ban=AsyncMock(),
    )
    interaction = SimpleNamespace(
        guild=guild,
        user=SimpleNamespace(mention="<@99>"),
        response=SimpleNamespace(
            defer=AsyncMock(),
            send_message=AsyncMock(),
            send_modal=AsyncMock(),
        ),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    return interaction


@pytest.fixture(autouse=True)
def allow_trial_helper(monkeypatch):
    monkeypatch.setattr(message_module.hf, "trial_helper_check", lambda _: True)


@pytest.mark.asyncio
async def test_ban_button_opens_modal_with_required_reason_and_notification_choice():
    view = message_module.ScamBanPromptView(SimpleNamespace(), make_target(), "reported content")
    interaction = make_interaction()

    await view.ban_user.callback(interaction)

    interaction.response.send_modal.assert_awaited_once()
    modal = interaction.response.send_modal.await_args.args[0]
    assert isinstance(modal, message_module.ScamBanReasonModal)
    assert modal.reason.required is True
    assert modal.reason.value == "Hacked account"
    assert modal.notification.required is True
    assert [(option.label, option.value) for option in modal.notification.options] == [
        ("Send DM", "dm"),
        ("Silent", "silent"),
    ]
    assert not any(option.default for option in modal.notification.options)


@pytest.mark.asyncio
@pytest.mark.parametrize(("notification", "silent"), [("silent", True), ("dm", False)])
async def test_modal_trims_reason_and_passes_notification_choice_to_prompt_view(notification, silent):
    prompt_view = SimpleNamespace(submit_ban=AsyncMock())
    modal = message_module.ScamBanReasonModal(prompt_view)
    modal.reason._value = "  repeated harassment  "
    modal.notification._value = notification
    interaction = make_interaction()

    await modal.on_submit(interaction)

    prompt_view.submit_ban.assert_awaited_once_with(
        interaction,
        "repeated harassment",
        silent=silent,
    )


@pytest.mark.asyncio
async def test_silent_incident_ban_skips_dm_and_records_silent(monkeypatch):
    target = make_target()
    interaction = make_interaction()
    prompt_message = SimpleNamespace(edit=AsyncMock())
    view = message_module.ScamBanPromptView(SimpleNamespace(), target, "reported content")
    view.message = prompt_message
    add_to_modlog = Mock()
    monkeypatch.setattr(message_module.hf, "add_to_modlog", add_to_modlog)

    await view.submit_ban(interaction, "Repeated harassment", silent=True)

    interaction.response.defer.assert_awaited_once_with()
    target.send.assert_not_awaited()
    interaction.guild.ban.assert_awaited_once_with(target, reason="Repeated harassment")
    add_to_modlog.assert_called_once_with(
        None,
        [target, interaction.guild],
        "Ban",
        "Repeated harassment",
        True,
        None,
    )
    result = prompt_message.edit.await_args.kwargs["content"]
    assert "Notification: Silent (no DM sent)" in result
    assert all(item.disabled for item in view.children)


@pytest.mark.asyncio
async def test_non_silent_incident_ban_sends_generic_reason_dm(monkeypatch):
    target = make_target()
    interaction = make_interaction()
    prompt_message = SimpleNamespace(edit=AsyncMock())
    view = message_module.ScamBanPromptView(SimpleNamespace(), target, "reported content")
    view.message = prompt_message
    add_to_modlog = Mock()
    monkeypatch.setattr(message_module.hf, "add_to_modlog", add_to_modlog)

    await view.submit_ban(interaction, "Impersonating another member", silent=False)

    target.send.assert_awaited_once()
    dm_embed = target.send.await_args.kwargs["embed"]
    assert dm_embed.title == "You're being banned from Spanish-English Language Exchange"
    assert dm_embed.fields[0].value == "Impersonating another member"
    assert message_module.BAN_APPEAL_LINK in dm_embed.fields[1].value
    assert "hacked" not in str(dm_embed.to_dict()).lower()
    assert add_to_modlog.call_args.args[4] is False
    result = prompt_message.edit.await_args.kwargs["content"]
    assert "Notification: DM sent with the reason and appeal link" in result


@pytest.mark.asyncio
async def test_failed_dm_falls_back_to_silent_ban(monkeypatch):
    target = make_target()
    target.send.side_effect = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"),
        {"code": 50007, "message": "Cannot send messages to this user"},
    )
    interaction = make_interaction()
    prompt_message = SimpleNamespace(edit=AsyncMock())
    view = message_module.ScamBanPromptView(SimpleNamespace(), target, "reported content")
    view.message = prompt_message
    add_to_modlog = Mock()
    monkeypatch.setattr(message_module.hf, "add_to_modlog", add_to_modlog)

    await view.submit_ban(interaction, "Ban evasion", silent=False)

    interaction.guild.ban.assert_awaited_once_with(target, reason="Ban evasion")
    assert add_to_modlog.call_args.args[4] is True
    result = prompt_message.edit.await_args.kwargs["content"]
    assert "DM could not be delivered; ban completed silently" in result


@pytest.mark.asyncio
async def test_failed_ban_resets_guard_and_leaves_prompt_available(monkeypatch):
    target = make_target()
    interaction = make_interaction()
    interaction.guild.ban.side_effect = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"),
        {"code": 50013, "message": "Missing Permissions"},
    )
    prompt_message = SimpleNamespace(edit=AsyncMock())
    view = message_module.ScamBanPromptView(SimpleNamespace(), target, "reported content")
    view.message = prompt_message
    add_to_modlog = Mock()
    monkeypatch.setattr(message_module.hf, "add_to_modlog", add_to_modlog)

    await view.submit_ban(interaction, "Ban evasion", silent=True)

    interaction.followup.send.assert_awaited_once()
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    assert view.ban_in_progress is False
    assert not any(item.disabled for item in view.children)
    add_to_modlog.assert_not_called()
    prompt_message.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_modal_submission_rechecks_staff_permission(monkeypatch):
    monkeypatch.setattr(message_module.hf, "trial_helper_check", lambda _: False)
    target = make_target()
    interaction = make_interaction()
    view = message_module.ScamBanPromptView(SimpleNamespace(), target, "reported content")

    await view.submit_ban(interaction, "Ban evasion", silent=True)

    interaction.response.send_message.assert_awaited_once_with(
        "Only Spanish server trial staff or above can use this button.",
        ephemeral=True,
    )
    interaction.response.defer.assert_not_awaited()
    interaction.guild.ban.assert_not_awaited()


@pytest.mark.asyncio
async def test_false_alarm_cannot_run_while_ban_is_in_progress():
    target = make_target()
    interaction = make_interaction()
    view = message_module.ScamBanPromptView(SimpleNamespace(), target, "reported content")
    view.ban_in_progress = True

    await view.false_alarm.callback(interaction)

    target.edit.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(
        "This incident is already being handled.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_timeout_followup_prompt_has_no_hacked_account_default():
    prompt_message = SimpleNamespace()
    msg = SimpleNamespace(
        author=make_target(),
        reply=AsyncMock(return_value=prompt_message),
    )

    await message_module.handle_scam_timeout_followup(
        SimpleNamespace(),
        msg,
        "reported content",
        message_module.timedelta(minutes=10),
    )

    prompt_text = msg.reply.await_args.args[0]
    assert "Hacked account" not in prompt_text
    assert "enter a reason" in prompt_text
    assert "choose whether to notify" in prompt_text
    assert msg.reply.await_args.kwargs["view"].message is prompt_message
