import sqlite3
import traceback
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

# Importing helper_functions first follows Rai's normal startup import order and
# avoids cogs.ai's runtime Rai type import observing a half-initialized module.
from cogs.utils import helper_functions as _helper_functions  # noqa: F401
from cogs import ai as ai_module
from cogs.ai import AI
from cogs.utils.traceback_store import TracebackStore
from Rai import Rai
from cogs.background import Background
from cogs.utils.BotUtils import bot_utils as utils
from tests.discord_fakes import (
    make_attachment,
    make_bot,
    make_channel,
    make_guild,
    make_member,
    make_message,
    make_thread,
)


SOURCE_CHANNEL_ID = 123456789012345678
FORUM_CHANNEL_ID = 1360884895957651496


def _attachment_filename() -> str:
    for module in (utils, ai_module):
        for name in (
            "TRACEBACK_ATTACHMENT_FILENAME",
            "FULL_TRACEBACK_ATTACHMENT_FILENAME",
        ):
            if value := getattr(module, name, None):
                return value
    return "rai-traceback.txt"


def _forum_with_thread(*, thread_send: AsyncMock | None = None):
    thread = make_thread(
        send=thread_send or AsyncMock(),
        delete=AsyncMock(),
    )
    forum = MagicMock(spec=discord.ForumChannel)
    forum.id = FORUM_CHANNEL_ID
    forum.create_thread = AsyncMock(return_value=SimpleNamespace(thread=thread))
    return forum, thread


@pytest.fixture
def store(tmp_path):
    archive = TracebackStore(tmp_path / "tracebacks.db")
    archive.initialize()
    return archive


def _cog(store, *, forum=None):
    guild = make_guild(guild_id=1)
    bot_user = make_member(member_id=999, bot=True, guild=guild)
    bot = make_bot(
        user=bot_user,
        traceback_store=store,
        db={"ai_features": {"enabled": True}},
        openai=object(),
        get_channel=MagicMock(return_value=forum),
    )
    cog = AI.__new__(AI)
    cog.bot = bot
    cog.chat_completion_text = AsyncMock(
        return_value="Parsed traceback\nAI diagnosis",
    )
    return cog, bot


def _message(
        bot,
        body=(
            'Traceback (most recent call last):\n'
            '  File "example.py", line 1, in run\n'
            '    raise RuntimeError("boom")\n'
            'RuntimeError: boom'
        ),
        *,
        channel_id=SOURCE_CHANNEL_ID,
        embeds=None,
        attachments=None,
):
    guild = bot.user.guild
    channel = guild.get_channel(channel_id)
    if channel is None:
        channel = make_channel(channel_id=channel_id, guild=guild)
    return make_message(
        guild=guild,
        author=bot.user,
        channel=channel,
        content=f"```py\n{body}\n```",
        embeds=[MagicMock(spec=discord.Embed)] if embeds is None else embeds,
        attachments=[] if attachments is None else attachments,
    )


def _configure_source_channel(monkeypatch):
    monkeypatch.setenv("TRACEBACK_LOGGING_CHANNEL", str(SOURCE_CHANNEL_ID + 10))
    monkeypatch.setenv("ERROR_CHANNEL_ID", str(SOURCE_CHANNEL_ID))


def _published(store):
    with closing(sqlite3.connect(store.filename)) as db:
        return db.execute("SELECT forum_thread_id FROM error_groups WHERE forum_thread_id IS NOT NULL").fetchall()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    "Translator probe armed for three failures or two hours.",
    "{'active': True, 'saved': 904, 'missed': 0}",
    "print('Traceback (most recent call last):')",
])
async def test_ordinary_python_output_is_not_archived(monkeypatch, store, body):
    _configure_source_channel(monkeypatch)
    forum, _thread = _forum_with_thread()
    cog, bot = _cog(store, forum=forum)

    await cog.on_message(_message(bot, body))

    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone() == (0,)
        assert db.execute("SELECT COUNT(*) FROM error_groups").fetchone() == (0,)
    cog.chat_completion_text.assert_not_awaited()
    forum.create_thread.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["normal", "chain", "group"])
async def test_legacy_formatted_tracebacks_are_preserved(monkeypatch, store, kind):
    _configure_source_channel(monkeypatch)
    cog, bot = _cog(store)
    bot.db["ai_features"]["enabled"] = False
    try:
        if kind == "group":
            raise ExceptionGroup("failures", [ValueError("first"), RuntimeError("second")])
        if kind == "chain":
            raise RuntimeError("outer") from ValueError("inner without stack")
        raise RuntimeError("boom")
    except Exception as error:
        body = "".join(traceback.format_exception(error))

    msg = _message(bot, body)
    await cog.on_message(msg)

    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT sample_traceback FROM caller_paths").fetchall() == [(body + "\n",)]
        assert db.execute("SELECT COUNT(*) FROM events").fetchone() == (1,)


@pytest.mark.asyncio
async def test_tagged_attachment_without_stack_is_still_archived(monkeypatch, store):
    _configure_source_channel(monkeypatch)
    cog, bot = _cog(store)
    bot.db["ai_features"]["enabled"] = False
    body = "ValueError: exception without stack\n"
    msg = _message(bot, attachments=[make_attachment(filename=_attachment_filename(), data=body.encode())])
    msg.content = utils.TRACEBACK_MESSAGE_MARKER

    await cog.on_message(msg)

    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT sample_traceback FROM caller_paths").fetchall() == [(body,)]


@pytest.mark.asyncio
async def test_self_authored_traceback_is_dispatched_before_general_bot_filter(monkeypatch, store):
    _configure_source_channel(monkeypatch)
    cog, bot = _cog(store)
    msg = _message(bot)
    cog.log_rai_tracebacks = AsyncMock()
    cog.mods_ping = AsyncMock()
    cog.sp_serv_other_language_detection = AsyncMock()
    cog.chatgpt_new_user_moderation = AsyncMock()
    cog.check_ryry_messages = AsyncMock()

    await cog.on_message(msg)

    cog.log_rai_tracebacks.assert_awaited_once()
    cog.mods_ping.assert_not_awaited()
    cog.sp_serv_other_language_detection.assert_not_awaited()
    cog.chatgpt_new_user_moderation.assert_not_awaited()
    cog.check_ryry_messages.assert_not_awaited()


@pytest.mark.asyncio
async def test_self_authored_message_outside_traceback_channel_is_ignored(monkeypatch, store):
    _configure_source_channel(monkeypatch)
    cog, bot = _cog(store)
    msg = _message(bot, channel_id=SOURCE_CHANNEL_ID + 1)
    cog.log_rai_tracebacks = AsyncMock()
    cog.mods_ping = AsyncMock()
    cog.sp_serv_other_language_detection = AsyncMock()
    cog.chatgpt_new_user_moderation = AsyncMock()
    cog.check_ryry_messages = AsyncMock()

    await cog.on_message(msg)

    cog.log_rai_tracebacks.assert_not_awaited()
    cog.mods_ping.assert_not_awaited()
    cog.sp_serv_other_language_detection.assert_not_awaited()
    cog.chatgpt_new_user_moderation.assert_not_awaited()
    cog.check_ryry_messages.assert_not_awaited()


@pytest.mark.asyncio
async def test_long_traceback_is_archived_without_ai_or_forum_post(monkeypatch, store):
    _configure_source_channel(monkeypatch)
    sent_source_messages = []

    async def capture_source_send(*args, **kwargs):
        file = kwargs.get("file")
        if file is None and kwargs.get("files"):
            file = kwargs["files"][0]

        attachment_bytes = None
        attachment_name = None
        if file is not None:
            attachment_name = file.filename
            original_position = file.fp.tell()
            file.fp.seek(0)
            attachment_bytes = file.fp.read()
            file.fp.seek(original_position)

        sent_source_messages.append(
            SimpleNamespace(
                content=args[0] if args else kwargs.get("content", ""),
                embed=kwargs.get("embed"),
                attachment_name=attachment_name,
                attachment_bytes=attachment_bytes,
            )
        )

    source_channel = make_channel(
        channel_id=SOURCE_CHANNEL_ID,
        send=AsyncMock(side_effect=capture_source_send),
    )
    producer_bot = make_bot(channels=[source_channel], traceback_store=store)
    producer_bot.record_traceback = Rai.record_traceback.__get__(producer_bot)
    long_error_text = "TRACEBACK-START-雪🚨-" + ("detail-line\n" * 450) + "TRACEBACK-END"

    try:
        try:
            raise ValueError("INNER-TRACEBACK-MARKER")
        except ValueError as inner_error:
            raise RuntimeError(long_error_text) from inner_error
    except RuntimeError as error:
        expected_full_traceback = "".join(
            traceback.format_exception(type(error), error, error.__traceback__, chain=True)
        )
        await utils.send_error_embed_internal(producer_bot, "long_trace_event", error)

    assert len(sent_source_messages) == 1
    attached_messages = [message for message in sent_source_messages if message.attachment_bytes is not None]
    assert len(attached_messages) == 1
    final_source_message = attached_messages[0]
    assert final_source_message is sent_source_messages[-1]
    assert final_source_message.attachment_name == _attachment_filename()
    full_traceback = final_source_message.attachment_bytes.decode("utf-8")
    assert full_traceback == expected_full_traceback
    assert "INNER-TRACEBACK-MARKER" in full_traceback
    assert "direct cause" in full_traceback
    assert "TRACEBACK-START-" in full_traceback
    assert "TRACEBACK-END" in full_traceback

    forum, thread = _forum_with_thread()
    cog, bot = _cog(store, forum=forum)

    for source_message in sent_source_messages:
        attachments = []
        if source_message.attachment_bytes is not None:
            attachments = [
                make_attachment(
                    filename=source_message.attachment_name,
                    data=source_message.attachment_bytes,
                )
            ]
        msg = _message(
            bot,
            embeds=[] if source_message.embed is None else [source_message.embed],
            attachments=attachments,
        )
        msg.content = source_message.content
        await cog.log_rai_tracebacks(msg)

    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT sample_traceback FROM caller_paths").fetchall() == [(full_traceback,)]
        assert db.execute("SELECT source_message_id, origin FROM events").fetchall() == [(msg.id, "long_trace_event")]
    cog.chat_completion_text.assert_not_awaited()
    forum.create_thread.assert_not_awaited()
    thread.send.assert_not_awaited()
    assert _published(store) == []


@pytest.mark.asyncio
async def test_background_error_uses_shared_traceback_sender(monkeypatch):
    bot = make_bot()
    cog = Background.__new__(Background)
    cog.bot = bot
    send_error_embed = AsyncMock()
    monkeypatch.setattr(utils, "send_error_embed", send_error_embed)
    error = RuntimeError("background failure")

    await cog.handle_error(error)

    send_error_embed.assert_awaited_once_with(bot, "Background task", error)


@pytest.mark.asyncio
async def test_shared_reporter_archives_without_discord_or_ai(monkeypatch, store):
    monkeypatch.setenv("TRACEBACK_LOGGING_CHANNEL", "0")
    monkeypatch.setenv("ERROR_CHANNEL_ID", "0")
    bot = make_bot(traceback_store=store, openai=None)
    bot.record_traceback = Rai.record_traceback.__get__(bot)
    for _ in range(3):
        try:
            raise ValueError("Google Translate returned an empty response")
        except ValueError as error:
            await utils.send_error_embed(bot, "translation", error)

    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT occurrences, caller_paths, forum_thread_id FROM group_summary").fetchall() == [
            (3, 1, None)]
        assert db.execute("SELECT DISTINCT origin, source_message_id FROM events").fetchall() == [("translation", None)]
        assert "Google Translate returned an empty response" in db.execute(
            "SELECT sample_traceback FROM caller_paths").fetchone()[0]


@pytest.mark.asyncio
async def test_source_delivery_with_ai_disabled_links_existing_event_without_downloading(monkeypatch, store):
    _configure_source_channel(monkeypatch)
    cog, bot = _cog(store)
    bot.db["ai_features"]["enabled"] = False
    error = ValueError("failure")
    event_id = await store.record_exception(error, "example", "".join(traceback.format_exception(error)))
    msg = _message(bot)
    msg.content = f"{utils.TRACEBACK_MESSAGE_MARKER}\nTraceback event: {event_id}\n```py\npreview```"
    cog.traceback_text_from_message = AsyncMock(side_effect=AssertionError("unexpected attachment read"))

    await cog.on_message(msg)
    await cog.on_message(msg)

    cog.chat_completion_text.assert_not_awaited()
    with closing(sqlite3.connect(store.filename)) as db:
        assert db.execute("SELECT id, source_message_id FROM events").fetchall() == [(event_id, msg.id)]
