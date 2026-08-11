from unittest.mock import AsyncMock

import pytest

from cogs import quotes as quotes_module
from cogs.quotes import Quotes
from tests.discord_fakes import (
    make_attachment,
    make_bot,
    make_channel,
    make_context,
    make_guild,
    make_interaction,
    make_member,
    make_message,
)


GUILD_ID = 243838819743432704


def _quote_entry(**overrides):
    entry = {
        "id": 1,
        "name": "ping",
        "name_key": "ping",
        "body": "stored @everyone and @here text",
        "author_id": 123,
        "author_name": "quote author",
        "times_used": 0,
        "last_used_at": None,
        "source_channel_id": None,
        "source_message_id": None,
        "created_at_source": "message",
    }
    entry.update(overrides)
    return entry


def _quotes_cog(*entries):
    bot = make_bot(
        db={
            "quotes": {
                str(GUILD_ID): {
                    "next_id": len(entries) + 1,
                    "entries": list(entries),
                    "log_channel": None,
                },
            },
        },
    )
    return Quotes(bot)


def _assert_mentions_disabled(allowed_mentions):
    assert allowed_mentions.to_dict() == {"parse": []}


@pytest.mark.asyncio
async def test_qsearch_suppresses_mentions_in_user_written_preview(monkeypatch):
    safe_send = AsyncMock()
    monkeypatch.setattr(quotes_module.utils, "safe_send", safe_send)
    cog = _quotes_cog(_quote_entry())
    ctx = make_context(guild=make_guild(guild_id=GUILD_ID))

    await Quotes.qsearch.callback(cog, ctx, text="stored")

    safe_send.assert_awaited_once()
    assert "@everyone" in safe_send.await_args.args[1]
    assert "@here" in safe_send.await_args.args[1]
    _assert_mentions_disabled(safe_send.await_args.kwargs["allowed_mentions"])


@pytest.mark.asyncio
async def test_qinfo_suppresses_mentions_in_user_written_embed(monkeypatch):
    safe_send = AsyncMock()
    monkeypatch.setattr(quotes_module.utils, "safe_send", safe_send)
    cog = _quotes_cog(_quote_entry())
    ctx = make_context(guild=make_guild(guild_id=GUILD_ID))

    await Quotes.qinfo.callback(cog, ctx, quote_id=1)

    safe_send.assert_awaited_once()
    assert "@everyone" in safe_send.await_args.kwargs["embed"].description
    _assert_mentions_disabled(safe_send.await_args.kwargs["allowed_mentions"])


@pytest.mark.asyncio
async def test_interaction_quote_pages_suppress_mentions_on_every_page():
    cog = _quotes_cog()
    interaction = make_interaction()
    lines = [f"quote {index} @everyone" for index in range(Quotes.LIST_PAGE_SIZE + 1)]

    await cog._send_quote_pages_interaction(interaction, "User quotes", lines)

    interaction.response.send_message.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()
    _assert_mentions_disabled(
        interaction.response.send_message.await_args.kwargs["allowed_mentions"]
    )
    _assert_mentions_disabled(interaction.followup.send.await_args.kwargs["allowed_mentions"])


@pytest.mark.asyncio
async def test_direct_quote_display_suppresses_mentions():
    destination = make_channel(send=AsyncMock())
    author = make_member(member_id=456)

    await Quotes._send_quote(destination, author, _quote_entry())

    destination.send.assert_awaited_once()
    _assert_mentions_disabled(destination.send.await_args.kwargs["allowed_mentions"])


@pytest.mark.asyncio
async def test_yaml_parse_error_suppresses_mentions_reflected_from_user_file(monkeypatch):
    safe_send = AsyncMock()
    monkeypatch.setattr(quotes_module.utils, "safe_send", safe_send)
    attachment = make_attachment(
        filename="quotes.yaml",
        data=b"quote: [@everyone",
    )
    message = make_message(attachments=[attachment])
    ctx = make_context(message=message)
    cog = _quotes_cog()

    await Quotes.quotesimport.callback(cog, ctx)

    safe_send.assert_awaited_once()
    assert "@everyone" in safe_send.await_args.args[1]
    _assert_mentions_disabled(safe_send.await_args.kwargs["allowed_mentions"])
