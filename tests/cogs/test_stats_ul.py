import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from cogs import stats as stats_module
from cogs import message as message_module
from cogs.utils import helper_functions as hf
from tests.discord_fakes import make_bot, make_context, make_guild, make_member


NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def queued_message(language, when=NOW, *, author_id=456, guild_id=123):
    return hf.MiniMessage(
        message_id=discord.utils.time_snowflake(when), content='example',
        author_id=author_id, channel_id=987, guild_id=guild_id, detected_lang=language,
    )


@pytest.fixture
def language_stats(monkeypatch):
    guild = make_guild(guild_id=123, emojis=[])
    author = make_member(member_id=456, guild=guild)
    ctx = make_context(guild=guild, author=author)
    config = {
        'enable': True,
        'messages': {
            '20261014': {'456': {
                'channels': {str(ctx.channel.id): 100},
                'lang': {'en': 90, 'es': 10},
            }},
            '20261015': {
                '456': {
                    'channels': {str(ctx.channel.id): 4},
                    'lang': {'en': 3, 'es': 1},
                },
            },
        },
        'voice': {'total_time': {}},
    }
    queue = hf.MessageQueue([
        queued_message('en', NOW - timedelta(hours=24, milliseconds=1)),
        queued_message('es', NOW - timedelta(hours=24)),
        queued_message('en', NOW - timedelta(seconds=3)),
        queued_message('en', NOW - timedelta(seconds=2)),
        queued_message('en', NOW - timedelta(seconds=1)),
        queued_message('es'),
        queued_message(None),
        queued_message('fr', author_id=789),
        queued_message('fr', guild_id=999),
        queued_message('fr', NOW + timedelta(seconds=1)),
    ])
    bot = make_bot(stats={'123': config}, message_queue=queue)
    monkeypatch.setattr(hf.here, 'bot', bot)
    monkeypatch.setattr(discord.utils, 'utcnow', lambda: NOW)
    return bot, ctx, config


def test_rolling_window_uses_queue_and_survives_json_reload(language_stats):
    bot, ctx, config = language_stats
    # Old daily-only data must not be counted as though it had exact timestamps.
    config['messages']['20261013'] = {'456': {'channels': {}, 'lang': {'en': 1000}}}
    bot.stats = json.loads(json.dumps(bot.stats))
    saved_queue = json.dumps(bot.message_queue.to_dict_list())
    bot.message_queue = hf.MessageQueue.from_dict(json.loads(saved_queue))

    counts, total, percentages = hf.get_language_stats(
        ctx.author.id, ctx.guild, since=NOW - timedelta(hours=24))

    assert counts == {'en': 3, 'es': 2}
    assert total == 5
    assert percentages == {'en': 60.0, 'es': 40.0}
    assert hf.get_language_stats(ctx.author.id, ctx.guild)[1] == 1104


@pytest.mark.asyncio
async def test_ul_shows_separate_month_and_rolling_day(language_stats, monkeypatch):
    bot, ctx, _ = language_stats
    send = AsyncMock()
    monkeypatch.setattr(stats_module.utils, 'safe_send', send)

    await stats_module.Stats.ul.callback(stats_module.Stats(bot), ctx)

    embed = send.await_args.kwargs['embed']
    assert embed.title == 'Your languages'
    assert embed.description == (
        '__Last 30 days__\n**English**: 89.4% | **Spanish**: 10.6%\n\n'
        '__Last 24 hours__\n**English**: 60.0% | **Spanish**: 40.0%'
    )
    assert embed.footer.text is None


@pytest.mark.asyncio
async def test_ul_handles_legacy_data(language_stats, monkeypatch):
    bot, ctx, _ = language_stats
    legacy_record = queued_message('en').to_dict()
    legacy_record.pop('detected_lang')
    bot.message_queue = hf.MessageQueue([legacy_record])
    send = AsyncMock()
    monkeypatch.setattr(stats_module.utils, 'safe_send', send)

    await stats_module.Stats.ul.callback(stats_module.Stats(bot), ctx)

    embed = send.await_args.kwargs['embed']
    assert '**English**: 89.4%' in embed.description
    assert '__Last 24 hours__\nNo language data to show.' in embed.description
    assert embed.footer.text is None


@pytest.mark.asyncio
async def test_queue_ingestion_preserves_detection(language_stats):
    bot, ctx, _ = language_stats
    bot.message_queue.clear()
    bot.db = {'deletes': {'123': {'enable': True}}, 'edits': {}}
    cog = object.__new__(message_module.Message)
    cog.bot = bot
    msg = hf.RaiMessage(SimpleNamespace(
        id=discord.utils.time_snowflake(NOW), guild=ctx.guild, author=ctx.author,
        channel=ctx.channel, content='hola', attachments=[], embeds=[],
    ))
    msg.detected_lang = 'es'
    await message_module.Message.add_to_message_queue.__wrapped__(cog, msg)
    msg.detected_lang = None
    await message_module.Message.add_to_message_queue.__wrapped__(cog, msg)

    assert [message.detected_lang for message in bot.message_queue] == ['es', None]
    assert hf.get_language_stats(ctx.author.id, ctx.guild, since=NOW - timedelta(hours=24)) == (
        {'es': 1}, 1, {'es': 100.0})


def test_message_refresh_preserves_language_and_handles_old_runtime_objects():
    message = queued_message('es')
    message.embeds = [{'url': 'https://example.com/image.png'}]
    refreshed = hf.MiniMessage.from_mini_message(message)
    assert refreshed.detected_lang == 'es'
    assert refreshed.embeds == message.embeds

    del message.detected_lang
    assert message.to_dict()['detected_lang'] is None
    assert hf.MiniMessage.from_mini_message(message).detected_lang is None


def test_missing_queue_has_no_recent_language_data(language_stats):
    bot, ctx, _ = language_stats
    del bot.message_queue
    assert hf.get_language_stats(ctx.author.id, ctx.guild, since=NOW - timedelta(hours=24)) == ({}, 0, {})
