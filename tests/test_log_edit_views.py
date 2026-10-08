"""Shared warning-edit state, Discord failure handling, and UI authorization."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs.utils import helper_functions as hf
from cogs.utils import views


def make_interaction(*, authorized=True):
    return SimpleNamespace(
        authorized=authorized,
        response=SimpleNamespace(
            send_modal=AsyncMock(),
            send_message=AsyncMock(),
            edit_message=AsyncMock(),
            defer=AsyncMock(),
        ),
        edit_original_response=AsyncMock(),
    )


def make_case(*, reason="old reason", copies=2):
    entry = {"reason": reason}
    embed = discord.Embed(title="Warning")
    embed.add_field(name="User", value="Test user", inline=False)
    embed.add_field(name="Reason", value=reason[:1024], inline=False)
    if len(reason) > 1024:
        embed.add_field(name="Reason (cont.)", value=reason[1024:], inline=False)
    embed.add_field(name="Jump URL", value="https://example.com/warning", inline=False)
    state = views.LogEditState(
        modlog_entry=views.ModlogDictEntryRef(entry),
        base_embed=embed,
        current_reason=reason,
    )
    messages = []
    edit_views = []
    for index in range(copies):
        message = Mock(spec=discord.Message)
        message.id = 100 + index
        message.edit = AsyncMock()
        messages.append(message)
        edit_views.append(views.LogEditView(state=state, message=message))
    return SimpleNamespace(
        state=state, entry=entry, embed=embed, messages=messages, views=edit_views,
    )


def embed_reason(embed):
    return "".join(field.value for field in embed.fields
                   if field.name in ("Reason", "Reason (cont.)"))


def response_text(interaction):
    text = []
    for method in (interaction.response.send_message,
                   interaction.response.edit_message,
                   interaction.edit_original_response):
        for call in method.await_args_list:
            content = call.kwargs.get("content", call.args[0] if call.args else "")
            text.append(content or "")
    return " ".join(text).lower()


def discord_error(error_type=discord.Forbidden):
    status = 404 if error_type is discord.NotFound else 403
    return error_type(
        SimpleNamespace(status=status, reason="test failure"),
        {"code": 10008 if status == 404 else 50013, "message": "test failure"},
    )


@pytest.fixture(autouse=True)
def warning_permissions(monkeypatch):
    # Model the existing warning policy without coupling these UI tests to guild config.
    monkeypatch.setattr(hf, "trial_helper_check", lambda interaction: interaction.authorized)


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", [0, 1])
async def test_either_copy_updates_both_before_committing_storage(trigger):
    case = make_case()
    interaction = make_interaction()

    async def edit_message(**kwargs):
        interaction.response.defer.assert_awaited_once()
        assert case.entry["reason"] == case.state.current_reason == "old reason"
        assert case.state.revision == 0
        assert embed_reason(case.state.base_embed) == "old reason"
        assert embed_reason(kwargs["embed"]) == "new reason"
        assert "view" not in kwargs, "Editing the embed must preserve each message's own view"

    for message in case.messages:
        message.edit.side_effect = edit_message

    await case.views[trigger].apply_edit(interaction, "new reason")

    for message in case.messages:
        message.edit.assert_awaited_once()
    assert case.entry["reason"] == case.state.current_reason == "new reason"
    assert all(view.current_reason == "new reason" for view in case.views)
    assert case.state.revision == 1
    assert embed_reason(case.state.base_embed) == "new reason"
    assert [field.name for field in case.state.base_embed.fields] == ["User", "Reason", "Jump URL"]


@pytest.mark.asyncio
async def test_nonstaff_cannot_open_or_apply_edit():
    case = make_case()
    interaction = make_interaction(authorized=False)

    await case.views[0].edit_button.callback(interaction)
    interaction.response.send_modal.assert_not_awaited()
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True

    await case.views[0].apply_edit(interaction, "not authorized")
    for message in case.messages:
        message.edit.assert_not_awaited()
    assert case.entry["reason"] == case.state.current_reason == "old reason"
    assert case.state.revision == 0


@pytest.mark.asyncio
async def test_permission_revoked_after_preview_blocks_confirmation():
    case = make_case()
    interaction = make_interaction()
    await case.views[0].edit_button.callback(interaction)
    modal = interaction.response.send_modal.await_args.args[0]
    modal.new_reason._value = "new reason"
    await modal.on_submit(interaction)
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True
    confirmation = interaction.response.send_message.await_args.kwargs["view"]

    confirmation_interaction = make_interaction(authorized=False)
    await confirmation.confirm.callback(confirmation_interaction)

    assert case.entry["reason"] == "old reason"
    for message in case.messages:
        message.edit.assert_not_awaited()
    assert confirmation_interaction.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_deleted_copy_is_skipped_and_not_retried():
    case = make_case()
    case.messages[0].edit.side_effect = discord_error(discord.NotFound)

    await case.views[1].apply_edit(make_interaction(), "first edit")
    assert case.entry["reason"] == "first edit"
    assert embed_reason(case.messages[1].edit.await_args.kwargs["embed"]) == "first edit"

    await case.views[1].apply_edit(make_interaction(), "second edit")
    assert case.messages[0].edit.await_count == 1
    assert case.messages[1].edit.await_count == 2
    assert case.entry["reason"] == case.state.current_reason == "second edit"
    assert case.state.revision == 2


@pytest.mark.asyncio
async def test_all_copies_deleted_keeps_saved_reason():
    case = make_case()
    for message in case.messages:
        message.edit.side_effect = discord_error(discord.NotFound)
    interaction = make_interaction()

    await case.views[0].apply_edit(interaction, "new reason")

    assert case.entry["reason"] == case.state.current_reason == "old reason"
    assert case.state.revision == 0
    assert response_text(interaction)
    assert "✅" not in response_text(interaction)


@pytest.mark.asyncio
async def test_first_api_failure_keeps_all_state_and_other_copy_unchanged():
    case = make_case()
    case.messages[0].edit.side_effect = discord_error()
    interaction = make_interaction()

    await case.views[0].apply_edit(interaction, "new reason")

    case.messages[1].edit.assert_not_awaited()
    assert case.entry["reason"] == case.state.current_reason == "old reason"
    assert embed_reason(case.state.base_embed) == "old reason"
    assert case.state.revision == 0
    assert response_text(interaction)
    assert "✅" not in response_text(interaction)


@pytest.mark.asyncio
async def test_second_api_failure_restores_already_updated_copy():
    case = make_case()
    case.messages[1].edit.side_effect = discord_error()
    interaction = make_interaction()

    await case.views[0].apply_edit(interaction, "new reason")

    assert [embed_reason(call.kwargs["embed"])
            for call in case.messages[0].edit.await_args_list] == ["new reason", "old reason"]
    assert case.entry["reason"] == case.state.current_reason == "old reason"
    assert embed_reason(case.state.base_embed) == "old reason"
    assert case.state.revision == 0
    assert "✅" not in response_text(interaction)


@pytest.mark.asyncio
async def test_failed_rollback_reports_incomplete_synchronization():
    case = make_case()
    case.messages[0].edit.side_effect = [None, discord_error()]
    case.messages[1].edit.side_effect = discord_error()
    interaction = make_interaction()

    await case.views[0].apply_edit(interaction, "new reason")

    assert case.messages[0].edit.await_count == 2
    assert case.entry["reason"] == case.state.current_reason == "old reason"
    assert case.state.revision == 0
    feedback = response_text(interaction)
    assert any(phrase in feedback for phrase in (
        "out of sync", "out-of-sync", "partial", "could not restore", "couldn't restore",
        "failed to restore", "restore failed", "not be restored", "not restored",
    )), feedback
    assert "✅" not in feedback


@pytest.mark.asyncio
async def test_modal_keeps_original_revision_if_other_copy_changes_before_submit():
    case = make_case()
    interaction = make_interaction()
    await case.views[0].edit_button.callback(interaction)
    modal = interaction.response.send_modal.await_args.args[0]
    modal.new_reason._value = "stale draft"

    await case.views[1].apply_edit(make_interaction(), "another moderator's edit")
    await modal.on_submit(interaction)
    confirmation = interaction.response.send_message.await_args.kwargs["view"]
    confirmation_interaction = make_interaction()
    await confirmation.confirm.callback(confirmation_interaction)

    assert case.entry["reason"] == case.state.current_reason == "another moderator's edit"
    assert case.state.revision == 1
    assert all(message.edit.await_count == 1 for message in case.messages)
    assert response_text(confirmation_interaction)
    assert "✅" not in response_text(confirmation_interaction)


@pytest.mark.asyncio
async def test_concurrent_edits_serialize_updates_to_both_copies():
    case = make_case()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_deferred = asyncio.Event()

    async def edit_first_copy(**kwargs):
        if embed_reason(kwargs["embed"]) == "first edit":
            first_entered.set()
            await release_first.wait()

    case.messages[0].edit.side_effect = edit_first_copy
    first_interaction = make_interaction()
    second_interaction = make_interaction()
    second_interaction.response.defer.side_effect = lambda: second_deferred.set()
    first_task = asyncio.create_task(case.views[0].apply_edit(first_interaction, "first edit"))
    second_task = None
    try:
        await asyncio.wait_for(first_entered.wait(), timeout=2)
        second_task = asyncio.create_task(case.views[1].apply_edit(second_interaction, "second edit"))
        await asyncio.wait_for(second_deferred.wait(), timeout=2)
        assert case.messages[0].edit.await_count == 1
        case.messages[1].edit.assert_not_awaited()
    finally:
        release_first.set()
        await asyncio.wait_for(asyncio.gather(first_task, *([second_task] if second_task else [])), timeout=2)

    assert case.entry["reason"] == case.state.current_reason == "second edit"
    assert case.state.revision == 2
    for message in case.messages:
        assert [embed_reason(call.kwargs["embed"])
                for call in message.edit.await_args_list] == ["first edit", "second edit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [1024, 1025, 2048])
async def test_reason_boundaries_preserve_other_fields(length):
    case = make_case(reason="x" * 2048)
    reason = "y" * length

    await case.views[0].apply_edit(make_interaction(), reason)

    assert case.entry["reason"] == case.state.current_reason == reason
    fields = case.state.base_embed.fields
    assert fields[0].name == "User" and fields[-1].name == "Jump URL"
    assert embed_reason(case.state.base_embed) == reason
    assert all(len(field.value) <= 1024 for field in fields)
    assert sum(field.name.startswith("Reason") for field in fields) == (1 if length <= 1024 else 2)


@pytest.mark.asyncio
async def test_overlong_edit_leaves_all_copies_and_saved_reason_unchanged():
    case = make_case()
    interaction = make_interaction()

    await case.views[0].apply_edit(interaction, "x" * 2049)

    assert case.entry["reason"] == "old reason"
    assert case.state.revision == 0
    assert embed_reason(case.state.base_embed) == "old reason"
    for message in case.messages:
        message.edit.assert_not_awaited()
    assert "too long" in response_text(interaction)


@pytest.mark.asyncio
async def test_modal_accepts_existing_2048_character_reason():
    case = make_case(reason="x" * 2048)
    interaction = make_interaction()

    await case.views[0].edit_button.callback(interaction)

    modal = interaction.response.send_modal.await_args.args[0]
    assert modal.new_reason.default == "x" * 2048
    assert modal.new_reason.max_length == 2048


@pytest.mark.asyncio
async def test_new_modal_and_confirmation_support_old_live_view_after_reload():
    # Instances created before reloading utils have no shared state and accept
    # only the original apply_edit(interaction, reason) call signature.
    old_view = SimpleNamespace(current_reason="old reason")
    old_view.apply_edit = AsyncMock()
    modal = views.EditReasonModal(old_view)
    modal.new_reason._value = "new reason"
    interaction = make_interaction()

    await modal.on_submit(interaction)
    confirmation = interaction.response.send_message.await_args.kwargs["view"]
    confirmation_interaction = make_interaction()
    await confirmation.confirm.callback(confirmation_interaction)

    old_view.apply_edit.assert_awaited_once_with(confirmation_interaction, "new reason")
