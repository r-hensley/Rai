from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs.utils import views
from cogs import channel_mods as channel_mods_module
from cogs import general as general_module
from cogs import submod as submod_module
from tests.discord_fakes import (
    make_bot,
    make_channel,
    make_context,
    make_guild,
    make_interaction,
    make_member,
    make_message,
)


def make_forbidden() -> discord.Forbidden:
    return discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"),
        {"code": 50278, "message": "Cannot send messages to this user due to having no mutual guilds"},
    )


def test_view_consumers_resolve_symbols_through_reloaded_module(monkeypatch):
    pagination_view = object()
    offer_fallback = object()
    channel_check = object()
    monkeypatch.setattr(views, 'PaginationView', pagination_view)
    monkeypatch.setattr(views, 'offer_public_notification_fallback', offer_fallback)
    monkeypatch.setattr(views, 'is_public_notification_channel', channel_check)

    assert general_module.view_utils.PaginationView is pagination_view
    assert submod_module.view_utils.offer_public_notification_fallback is offer_fallback
    assert submod_module.view_utils.is_public_notification_channel is channel_check
    assert channel_mods_module.view_utils.offer_public_notification_fallback is offer_fallback


def make_fallback_case(*, configured_channel_id=None, guild_id=views.SP_SERVER_ID):
    guild = make_guild(guild_id=guild_id, name="Spanish-English Language Exchange")
    fallback_channel_id = configured_channel_id or views.SP_PUBLIC_MOD_NOTIFICATION_CHANNEL_ID
    fallback_channel = make_channel(
        channel_id=fallback_channel_id,
        guild=guild,
        send=AsyncMock(),
    )
    command_channel = make_channel(channel_id=222222222222222223, guild=guild)
    author = make_member(member_id=111111111111111112, guild=guild)
    target = make_member(member_id=111111111111111113, guild=guild)
    config = {'channel': None}
    if configured_channel_id is not None:
        config['warn_notification_channel'] = configured_channel_id
    bot = make_bot(
        db={'modlog': {str(guild.id): config}},
        guilds=[guild],
    )
    prompt_message = make_message(
        message_id=444444444444444445,
        channel=command_channel,
        guild=guild,
        edit=AsyncMock(),
    )
    ctx = make_context(
        guild=guild,
        channel=command_channel,
        author=author,
        bot=bot,
    )
    return ctx, target, fallback_channel, prompt_message


@pytest.mark.asyncio
async def test_spanish_fallback_uses_default_channel_and_snapshots_embed(monkeypatch):
    ctx, target, fallback_channel, prompt_message = make_fallback_case()
    safe_send = AsyncMock(return_value=prompt_message)
    monkeypatch.setattr(views.utils, 'safe_send', safe_send)
    embed = discord.Embed(title="Warning from the server")

    view = await views.offer_public_notification_fallback(ctx, target, embed, "warning")
    embed.title = "Internal warning log"
    embed.add_field(name="User", value=str(target.id))

    assert view.channel is fallback_channel
    assert view.embed.title == "Warning from the server"
    assert not view.embed.fields
    assert safe_send.await_args.kwargs['view'] is view
    assert view.message is prompt_message


@pytest.mark.asyncio
async def test_configured_channel_overrides_default(monkeypatch):
    configured_id = 333333333333333334
    ctx, target, fallback_channel, prompt_message = make_fallback_case(
        configured_channel_id=configured_id,
    )
    safe_send = AsyncMock(return_value=prompt_message)
    monkeypatch.setattr(views.utils, 'safe_send', safe_send)

    view = await views.offer_public_notification_fallback(
        ctx, target, discord.Embed(title="Mute"), "mute notification")

    assert view.channel is fallback_channel
    assert view.channel.id == configured_id


@pytest.mark.asyncio
async def test_missing_nonspanish_fallback_reports_without_creating_view(monkeypatch):
    guild = make_guild(guild_id=999999999999999999)
    author = make_member(member_id=111111111111111112, guild=guild)
    target = make_member(member_id=111111111111111113, guild=guild)
    bot = make_bot(db={'modlog': {str(guild.id): {'channel': None}}}, guilds=[guild])
    ctx = make_context(guild=guild, author=author, bot=bot)
    safe_send = AsyncMock()
    monkeypatch.setattr(views.utils, 'safe_send', safe_send)

    view = await views.offer_public_notification_fallback(
        ctx, target, discord.Embed(title="Warning"), "warning")

    assert view is None
    assert "no usable public fallback channel" in safe_send.await_args.args[1]
    assert 'view' not in safe_send.await_args.kwargs


@pytest.mark.asyncio
async def test_non_message_channel_is_rejected_as_fallback(monkeypatch):
    guild = make_guild(guild_id=views.SP_SERVER_ID)
    invalid_channel = SimpleNamespace(
        id=views.SP_PUBLIC_MOD_NOTIFICATION_CHANNEL_ID,
        mention="#not-a-text-channel",
        _fake_discord_kind="category",
    )
    guild.get_channel_or_thread = Mock(return_value=invalid_channel)
    author = make_member(member_id=111111111111111112, guild=guild)
    target = make_member(member_id=111111111111111113, guild=guild)
    bot = make_bot(db={'modlog': {str(guild.id): {'channel': None}}}, guilds=[guild])
    ctx = make_context(guild=guild, author=author, bot=bot)
    safe_send = AsyncMock()
    monkeypatch.setattr(views.utils, 'safe_send', safe_send)

    view = await views.offer_public_notification_fallback(
        ctx, target, discord.Embed(title="Warning"), "warning")

    assert view is None
    assert "no usable public fallback channel" in safe_send.await_args.args[1]


@pytest.mark.asyncio
async def test_warn_set_rejects_non_text_channel(monkeypatch):
    guild = make_guild(guild_id=views.SP_SERVER_ID)
    invalid_channel = SimpleNamespace(
        id=333333333333333334,
        mention="#not-a-text-channel",
    )
    guild.get_channel_or_thread = Mock(return_value=invalid_channel)
    author = make_member(member_id=111111111111111112, guild=guild)
    bot = make_bot(db={'modlog': {str(guild.id): {'channel': None}}}, guilds=[guild])
    ctx = make_context(guild=guild, author=author, bot=bot)
    cog = object.__new__(submod_module.Submod)
    cog.bot = bot
    safe_send = AsyncMock()
    monkeypatch.setattr(submod_module.utils, 'safe_send', safe_send)

    await submod_module.Submod.set_warn_notification_channel.callback(
        cog, ctx, str(invalid_channel.id))

    assert 'warn_notification_channel' not in bot.db['modlog'][str(guild.id)]
    assert "usable text channel or thread" in safe_send.await_args.args[1]


@pytest.mark.asyncio
async def test_authorized_public_send_posts_once_and_finishes(monkeypatch):
    ctx, target, fallback_channel, prompt_message = make_fallback_case()
    safe_send = AsyncMock(return_value=prompt_message)
    monkeypatch.setattr(views.utils, 'safe_send', safe_send)
    view = await views.offer_public_notification_fallback(
        ctx, target, discord.Embed(title="Warning from the server"), "warning")
    interaction = make_interaction(
        guild=ctx.guild,
        channel=ctx.channel,
        user=ctx.author,
        message=prompt_message,
    )

    await view.send_publicly.callback(interaction)

    interaction.response.defer.assert_awaited_once_with()
    public_call = safe_send.await_args_list[-1]
    assert public_call.args[0] is fallback_channel
    assert target.mention in public_call.args[1]
    assert public_call.kwargs['embed'].title == "Warning from the server"
    assert all(item.disabled for item in view.children)
    assert view.is_finished()
    prompt_message.edit.assert_awaited_once()

    second_interaction = make_interaction(
        guild=ctx.guild,
        channel=ctx.channel,
        user=ctx.author,
        message=prompt_message,
    )
    await view.send_publicly.callback(second_interaction)
    second_interaction.response.send_message.assert_awaited_once_with(
        "This public-delivery prompt has already been handled.",
        ephemeral=True,
    )
    assert safe_send.await_args_list.count(public_call) == 1


@pytest.mark.asyncio
async def test_cancel_and_timeout_never_send_to_public_channel(monkeypatch):
    ctx, target, fallback_channel, prompt_message = make_fallback_case()
    safe_send = AsyncMock(return_value=prompt_message)
    monkeypatch.setattr(views.utils, 'safe_send', safe_send)
    view = await views.offer_public_notification_fallback(
        ctx, target, discord.Embed(title="Mute"), "mute notification")
    interaction = make_interaction(
        guild=ctx.guild,
        channel=ctx.channel,
        user=ctx.author,
        message=prompt_message,
    )

    await view.cancel.callback(interaction)

    assert all(item.disabled for item in view.children)
    assert view.is_finished()
    assert not any(sent.args[0] is fallback_channel for sent in safe_send.await_args_list)

    timeout_prompt = make_message(edit=AsyncMock())
    timeout_view = views.PublicNotificationFallbackView(
        author=ctx.author,
        target=target,
        channel=fallback_channel,
        embed=discord.Embed(title="Warning"),
        notification_label="warning",
    )
    timeout_view.message = timeout_prompt
    await timeout_view.on_timeout()
    assert timeout_view.is_finished()
    assert all(item.disabled for item in timeout_view.children)
    timeout_prompt.edit.assert_awaited_once()


@pytest.mark.asyncio
async def test_unauthorized_user_is_rejected():
    ctx, target, fallback_channel, prompt_message = make_fallback_case()
    other_user = make_member(member_id=111111111111111114, guild=ctx.guild)
    interaction = make_interaction(
        guild=ctx.guild,
        channel=ctx.channel,
        user=other_user,
        message=prompt_message,
    )
    view = views.PublicNotificationFallbackView(
        author=ctx.author,
        target=target,
        channel=fallback_channel,
        embed=discord.Embed(title="Warning"),
        notification_label="warning",
    )

    assert await view.interaction_check(interaction) is False
    interaction.response.send_message.assert_awaited_once_with(
        "Only the moderator who initiated this action can use these buttons.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_public_send_failure_leaves_prompt_retryable(monkeypatch):
    ctx, target, fallback_channel, prompt_message = make_fallback_case()

    async def safe_send(destination, *args, **kwargs):
        if destination is fallback_channel:
            raise make_forbidden()
        return prompt_message

    safe_send_mock = AsyncMock(side_effect=safe_send)
    monkeypatch.setattr(views.utils, 'safe_send', safe_send_mock)
    view = await views.offer_public_notification_fallback(
        ctx, target, discord.Embed(title="Warning"), "warning")
    interaction = make_interaction(
        guild=ctx.guild,
        channel=ctx.channel,
        user=ctx.author,
        message=prompt_message,
    )

    await view.send_publicly.callback(interaction)

    assert view.handling is False
    assert not view.is_finished()
    assert not any(item.disabled for item in view.children)
    interaction.followup.send.assert_awaited_once()
    failure_text = interaction.followup.send.await_args.args[0]
    assert "permissions there, then retry" in failure_text
    assert "trigger a new notification" in failure_text


@pytest.mark.asyncio
async def test_warn_dm_failure_offers_fallback_and_still_logs(monkeypatch):
    guild = make_guild(guild_id=views.SP_SERVER_ID)
    target = make_member(member_id=111111111111111113, guild=guild)
    author = make_member(member_id=111111111111111112, guild=guild)
    channel = make_channel(channel_id=222222222222222223, guild=guild)
    bot = make_bot(
        db={'modlog': {str(guild.id): {'channel': None}}},
        guilds=[guild],
    )
    ctx = make_context(guild=guild, channel=channel, author=author, bot=bot)
    cog = object.__new__(submod_module.Submod)
    cog.bot = bot
    monkeypatch.setattr(
        submod_module.hf,
        'args_discriminator',
        lambda _: SimpleNamespace(user_ids=[target.id], reason="Repeated harassment"),
    )
    modlog_entry = SimpleNamespace(
        silent=False,
        reason=None,
        add_to_modlog=Mock(return_value={'channel': None, str(target.id): [{}]}),
    )
    monkeypatch.setattr(submod_module.hf, 'ModlogEntry', lambda **_: modlog_entry)
    offer_fallback = AsyncMock()
    monkeypatch.setattr(
        submod_module.view_utils,
        'offer_public_notification_fallback',
        offer_fallback,
    )

    async def safe_send(destination, *args, **kwargs):
        if destination is target:
            raise make_forbidden()
        return make_message(channel=channel, guild=guild)

    monkeypatch.setattr(submod_module.utils, 'safe_send', AsyncMock(side_effect=safe_send))

    await submod_module.Submod.warn.callback(cog, ctx, args="ignored by test parser")

    offer_fallback.assert_awaited_once()
    assert offer_fallback.await_args.args[:2] == (ctx, target)
    assert offer_fallback.await_args.args[3] == "warning"
    modlog_entry.add_to_modlog.assert_called_once_with()


def make_mute_case(*, automatic: bool):
    guild = make_guild(guild_id=views.SP_SERVER_ID)
    bot_member = make_member(member_id=777777777777777777, guild=guild, bot=True)
    guild.me = bot_member
    author = bot_member if automatic else make_member(member_id=111111111111111112, guild=guild)
    target = make_member(
        member_id=111111111111111113,
        guild=guild,
        timeout=AsyncMock(),
    )
    channel = make_channel(channel_id=222222222222222223, guild=guild)
    bot = make_bot(
        user=bot_member,
        db={'modlog': {str(guild.id): {'channel': None}}},
        guilds=[guild],
    )
    ctx = make_context(guild=guild, channel=channel, author=author, bot=bot)
    cog = object.__new__(channel_mods_module.ChannelMods)
    cog.bot = bot
    parsed_args = SimpleNamespace(
        time_string="2026/08/11 20:00 UTC",
        time_obj=discord.utils.utcnow() + timedelta(hours=1),
        timedelta_obj=timedelta(hours=1),
        time_arg="1h",
        length=[0, 1, 0, 0],
        reason="Repeated-message antispam",
        user_ids=[target.id],
    )
    return cog, ctx, target, parsed_args


@pytest.mark.asyncio
@pytest.mark.parametrize("automatic", [False, True])
async def test_mute_dm_failure_only_offers_human_invoker_fallback(monkeypatch, automatic):
    cog, ctx, target, parsed_args = make_mute_case(automatic=automatic)
    monkeypatch.setattr(channel_mods_module.hf, 'args_discriminator', lambda **_: parsed_args)
    monkeypatch.setattr(channel_mods_module.hf, 'submod_check', lambda _: True)
    monkeypatch.setattr(
        channel_mods_module.hf,
        'add_to_modlog',
        Mock(return_value={'channel': None}),
    )
    offer_fallback = AsyncMock()
    monkeypatch.setattr(
        channel_mods_module.view_utils,
        'offer_public_notification_fallback',
        offer_fallback,
    )

    async def safe_send(destination, *args, **kwargs):
        if destination is target:
            raise make_forbidden()
        return make_message(channel=ctx.channel, guild=ctx.guild)

    monkeypatch.setattr(channel_mods_module.utils, 'safe_send', AsyncMock(side_effect=safe_send))

    await channel_mods_module.ChannelMods.mute.callback(cog, ctx, args="ignored by test parser")

    target.timeout.assert_awaited_once()
    if automatic:
        offer_fallback.assert_not_awaited()
    else:
        offer_fallback.assert_awaited_once()
        assert offer_fallback.await_args.args[:2] == (ctx, target)
        assert offer_fallback.await_args.args[3] == "mute notification"
