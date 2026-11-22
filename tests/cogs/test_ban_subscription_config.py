"""Persistent config message for cross-server ban alert pings."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs import logger, persistent_embeds


GUILD_ID = 243838819743432704
CHANNEL_ID = 222222222222222222
MESSAGE_ID = 333333333333333333
ROLE_ID = 444444444444444444
USER_ID = 555555555555555555


def make_bot():
    channel = SimpleNamespace(
        id=CHANNEL_ID,
        guild=SimpleNamespace(id=GUILD_ID),
        send=AsyncMock(return_value=SimpleNamespace(id=MESSAGE_ID)),
        fetch_message=AsyncMock(return_value=SimpleNamespace(id=MESSAGE_ID)),
    )
    bot = SimpleNamespace(
        db={'bansub': {'guild_to_role': {str(GUILD_ID): ROLE_ID}, 'user_to_role': {}},
            'mod_channel': {str(GUILD_ID): CHANNEL_ID}},
        get_channel=Mock(return_value=channel),
        add_view=Mock(),
    )
    return bot, channel


@pytest.mark.asyncio
async def test_config_posts_on_first_alert_only_and_restores_button_after_reload(monkeypatch):
    bot, channel = make_bot()
    save = AsyncMock()
    monkeypatch.setattr(persistent_embeds.utils, 'dump_json', save)

    assert bot.db.get('persistent_embeds') is None
    url = await persistent_embeds.ensure_ban_config_message(bot, GUILD_ID)
    assert bot.db['persistent_embeds']['ban_subscriptions'][str(GUILD_ID)] == {
        'channel_id': CHANNEL_ID, 'message_id': MESSAGE_ID,
    }
    assert channel.send.await_count == 1
    assert "No one yet." in channel.send.await_args.kwargs['embed'].description
    save.assert_awaited_once_with('db')
    assert url == persistent_embeds.ban_config_url(bot, GUILD_ID) == (
        f'https://discord.com/channels/{GUILD_ID}/{CHANNEL_ID}/{MESSAGE_ID}'
    )

    await persistent_embeds.ensure_ban_config_message(bot, GUILD_ID)
    assert channel.send.await_count == 1
    bot.add_view.reset_mock()
    persistent_embeds.restore_views(bot)
    assert bot.add_view.call_args.kwargs['message_id'] == MESSAGE_ID


@pytest.mark.asyncio
async def test_simultaneous_alerts_post_one_config_message(monkeypatch):
    bot, channel = make_bot()
    monkeypatch.setattr(persistent_embeds.utils, 'dump_json', AsyncMock())
    urls = await asyncio.gather(
        persistent_embeds.ensure_ban_config_message(bot, GUILD_ID),
        persistent_embeds.ensure_ban_config_message(bot, GUILD_ID),
    )
    assert urls[0] == urls[1]
    channel.send.assert_awaited_once()


def test_logger_reload_restores_saved_button_without_posting():
    bot, channel = make_bot()
    bot.db['persistent_embeds'] = {'ban_subscriptions': {
        str(GUILD_ID): {'channel_id': CHANNEL_ID, 'message_id': MESSAGE_ID}}}
    cog = logger.Logger.__new__(logger.Logger)
    cog.bot = bot

    cog.cog_load()

    bot.add_view.assert_called_once()
    assert bot.add_view.call_args.kwargs['message_id'] == MESSAGE_ID
    channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_deleted_config_message_is_replaced(monkeypatch):
    bot, channel = make_bot()
    bot.db['persistent_embeds'] = {'ban_subscriptions': {
        str(GUILD_ID): {'channel_id': CHANNEL_ID, 'message_id': MESSAGE_ID - 1}}}
    channel.fetch_message.side_effect = discord.NotFound(
        SimpleNamespace(status=404, reason='Not Found'), 'Unknown Message')
    monkeypatch.setattr(persistent_embeds.utils, 'dump_json', AsyncMock())

    await persistent_embeds.ensure_ban_config_message(bot, GUILD_ID)

    channel.send.assert_awaited_once()
    assert bot.db['persistent_embeds']['ban_subscriptions'][str(GUILD_ID)]['message_id'] == MESSAGE_ID


@pytest.mark.asyncio
async def test_button_toggles_existing_ban_subscription(monkeypatch):
    bot, _ = make_bot()
    bot.db['persistent_embeds'] = {'ban_subscriptions': {
        str(GUILD_ID): {'channel_id': CHANNEL_ID, 'message_id': MESSAGE_ID}}}
    save = AsyncMock()
    monkeypatch.setattr(persistent_embeds.utils, 'dump_json', save)
    interaction = SimpleNamespace(
        guild=SimpleNamespace(id=GUILD_ID),
        message=SimpleNamespace(id=MESSAGE_ID, edit=AsyncMock()),
        user=SimpleNamespace(id=USER_ID),
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )
    view = persistent_embeds.BanSubscriptionView(bot)

    await view.children[0].callback(interaction)
    assert persistent_embeds.ban_subscribers(bot, GUILD_ID) == [USER_ID]
    await view.children[0].callback(interaction)
    assert persistent_embeds.ban_subscribers(bot, GUILD_ID) == []
    assert str(USER_ID) not in bot.db['bansub']['user_to_role']
    assert save.await_count == 2
    assert interaction.response.defer.await_count == 2
    assert interaction.followup.send.await_args.kwargs['ephemeral'] is True
    assert "No one yet." in interaction.message.edit.await_args.kwargs['embed'].description


@pytest.mark.asyncio
async def test_button_save_failure_keeps_subscription_unchanged(monkeypatch):
    bot, _ = make_bot()
    bot.db['persistent_embeds'] = {'ban_subscriptions': {
        str(GUILD_ID): {'channel_id': CHANNEL_ID, 'message_id': MESSAGE_ID}}}
    monkeypatch.setattr(persistent_embeds.utils, 'dump_json', AsyncMock(side_effect=OSError('disk full')))
    interaction = SimpleNamespace(
        guild=SimpleNamespace(id=GUILD_ID),
        message=SimpleNamespace(id=MESSAGE_ID, edit=AsyncMock()),
        user=SimpleNamespace(id=USER_ID),
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    await persistent_embeds.BanSubscriptionView(bot).children[0].callback(interaction)

    assert persistent_embeds.ban_subscribers(bot, GUILD_ID) == []
    interaction.message.edit.assert_not_awaited()
    assert "couldn't save" in interaction.followup.send.await_args.args[0]


@pytest.mark.asyncio
async def test_old_config_message_cannot_change_subscriptions(monkeypatch):
    bot, _ = make_bot()
    bot.db['persistent_embeds'] = {'ban_subscriptions': {
        str(GUILD_ID): {'channel_id': CHANNEL_ID, 'message_id': MESSAGE_ID}}}
    save = AsyncMock()
    monkeypatch.setattr(persistent_embeds.utils, 'dump_json', save)
    interaction = SimpleNamespace(
        guild=SimpleNamespace(id=GUILD_ID),
        message=SimpleNamespace(id=MESSAGE_ID - 1),
        user=SimpleNamespace(id=USER_ID),
        response=SimpleNamespace(send_message=AsyncMock()),
    )

    await persistent_embeds.BanSubscriptionView(bot).children[0].callback(interaction)
    save.assert_not_awaited()
    assert persistent_embeds.ban_subscribers(bot, GUILD_ID) == []
