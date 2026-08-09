import asyncio
import re
import traceback
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

# Importing helper_functions first follows Rai's normal startup import order and
# avoids cogs.ai's runtime Rai type import observing a half-initialized module.
from cogs.utils import helper_functions as _helper_functions  # noqa: F401
from cogs import ai as ai_module
from cogs.ai import AI
from cogs.background import Background
from cogs.utils.BotUtils import bot_utils as utils


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


def _http_error() -> discord.HTTPException:
    response = SimpleNamespace(status=500, reason="Server Error")
    return discord.HTTPException(response, {"code": 0, "message": "temporary failure"})


def _forum_with_thread(*, thread_send: AsyncMock | None = None):
    thread = MagicMock(spec=discord.Thread)
    thread.send = thread_send or AsyncMock()
    forum = MagicMock(spec=discord.ForumChannel)
    forum.id = FORUM_CHANNEL_ID
    forum.create_thread = AsyncMock(return_value=SimpleNamespace(thread=thread))
    return forum, thread


def _cog(*, forum=None):
    bot_user = SimpleNamespace(id=999, bot=True)
    bot = SimpleNamespace(
        user=bot_user,
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


def _message(bot, body="Traceback\nRuntimeError: boom", *, embeds=None, attachments=None):
    return SimpleNamespace(
        guild=SimpleNamespace(id=1),
        author=bot.user,
        channel=SimpleNamespace(id=SOURCE_CHANNEL_ID),
        content=f"```py\n{body}\n```",
        embeds=[MagicMock(spec=discord.Embed)] if embeds is None else embeds,
        attachments=[] if attachments is None else attachments,
    )


def _configure_source_channel(monkeypatch):
    monkeypatch.setenv("TRACEBACK_LOGGING_CHANNEL", str(SOURCE_CHANNEL_ID + 10))
    monkeypatch.setenv("ERROR_CHANNEL_ID", str(SOURCE_CHANNEL_ID))


def _dedupe_entries(bot) -> list[str]:
    return bot.db.get("rai_tracebacks", [])


def _assert_mentions_disabled(allowed_mentions):
    assert allowed_mentions.to_dict() == {"parse": []}


@pytest.mark.asyncio
async def test_self_authored_traceback_is_dispatched_before_general_bot_filter(monkeypatch):
    _configure_source_channel(monkeypatch)
    cog, bot = _cog()
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
async def test_self_authored_message_outside_traceback_channel_is_ignored(monkeypatch):
    _configure_source_channel(monkeypatch)
    cog, bot = _cog()
    msg = _message(bot)
    msg.channel = SimpleNamespace(id=SOURCE_CHANNEL_ID + 1)
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
async def test_long_traceback_attachment_creates_one_complete_forum_post(monkeypatch):
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

    source_channel = MagicMock(spec=discord.TextChannel)
    source_channel.send = AsyncMock(side_effect=capture_source_send)
    producer_bot = SimpleNamespace(
        get_channel=MagicMock(return_value=source_channel),
        get_guild=MagicMock(return_value=None),
    )
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
    forum_attachment = {}

    async def capture_forum_create(**kwargs):
        file = kwargs["file"]
        original_position = file.fp.tell()
        file.fp.seek(0)
        forum_attachment["bytes"] = file.fp.read()
        file.fp.seek(original_position)
        forum_attachment["filename"] = file.filename
        return SimpleNamespace(thread=thread)

    forum.create_thread.side_effect = capture_forum_create
    cog, bot = _cog(forum=forum)

    for source_message in sent_source_messages:
        attachments = []
        if source_message.attachment_bytes is not None:
            attachments = [
                SimpleNamespace(
                    filename=source_message.attachment_name,
                    read=AsyncMock(return_value=source_message.attachment_bytes),
                )
            ]
        msg = _message(
            bot,
            embeds=[] if source_message.embed is None else [source_message.embed],
            attachments=attachments,
        )
        msg.content = source_message.content
        await cog.log_rai_tracebacks(msg)

    cog.chat_completion_text.assert_awaited_once()
    forum.create_thread.assert_awaited_once()
    prompt_messages = cog.chat_completion_text.await_args.kwargs["messages"]
    assert any(full_traceback in str(message.get("content", "")) for message in prompt_messages)

    posted_parts = [str(forum.create_thread.await_args.kwargs.get("content", ""))]
    posted_parts.extend(str(call.args[0]) for call in thread.send.await_args_list if call.args)
    posted_text = "\n".join(posted_parts)
    assert "TRACEBACK-START-" in posted_text
    assert "TRACEBACK-END" in posted_text
    posted_traceback_chunks = [
        match.group(1)
        for part in posted_parts
        for match in re.finditer(r"```(?:py|python)\n(.*?)```", part, flags=re.DOTALL)
    ]
    assert "".join(posted_traceback_chunks) == full_traceback
    assert forum_attachment == {
        "bytes": final_source_message.attachment_bytes,
        "filename": _attachment_filename(),
    }
    _assert_mentions_disabled(forum.create_thread.await_args.kwargs["allowed_mentions"])
    assert thread.send.await_count >= 1
    for send_call in thread.send.await_args_list:
        _assert_mentions_disabled(send_call.kwargs["allowed_mentions"])


@pytest.mark.asyncio
async def test_concurrent_identical_tracebacks_publish_once(monkeypatch):
    _configure_source_channel(monkeypatch)
    forum, _thread = _forum_with_thread()
    cog, bot = _cog(forum=forum)
    msg = _message(bot)
    completion_started = asyncio.Event()
    release_completion = asyncio.Event()

    async def gated_completion(**_kwargs):
        completion_started.set()
        await release_completion.wait()
        return "Parsed traceback\nAI diagnosis"

    cog.chat_completion_text.side_effect = gated_completion
    first = asyncio.create_task(cog.log_rai_tracebacks(msg))
    await asyncio.wait_for(completion_started.wait(), timeout=1)
    second = asyncio.create_task(cog.log_rai_tracebacks(msg))
    await asyncio.sleep(0)
    release_completion.set()
    await asyncio.gather(first, second)

    assert cog.chat_completion_text.await_count == 1
    assert forum.create_thread.await_count == 1
    assert len(_dedupe_entries(bot)) == 1


@pytest.mark.asyncio
async def test_complete_legacy_fingerprint_suppresses_repost(monkeypatch):
    _configure_source_channel(monkeypatch)
    forum, _thread = _forum_with_thread()
    cog, bot = _cog(forum=forum)
    body = (
        'Traceback (most recent call last):\n'
        + ''.join(
            f'  File "/old/Rai/cogs/example.py", line {line}, in handler\n'
            f'    await operation_{line}()\n'
            for line in range(5)
        )
        + 'RuntimeError: legacy failure 123456\n'
    )
    msg = _message(bot, body=body)
    traceback_text = await cog.traceback_text_from_message(msg)
    legacy_segments = utils.split_text_into_segments(
        utils.compact_traceback_for_discord(traceback_text),
        1900,
    )
    assert len(legacy_segments) == 1
    bot.db["rai_tracebacks"] = [
        cog.traceback_fingerprint(f"\n{segment}")
        for segment in legacy_segments
    ]

    await cog.log_rai_tracebacks(msg)

    cog.chat_completion_text.assert_not_awaited()
    forum.create_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_flat_legacy_segments_do_not_suppress_new_composite_traceback(monkeypatch):
    _configure_source_channel(monkeypatch)
    forum, _thread = _forum_with_thread()
    cog, bot = _cog(forum=forum)
    body = (
        'Traceback (most recent call last):\n'
        + ''.join(
            f'  File "/old/Rai/cogs/example.py", line {line}, in handler\n'
            f'    await operation_{line}()\n'
            for line in range(80)
        )
        + 'RuntimeError: legacy failure 123456\n'
    )
    msg = _message(bot, body=body)
    traceback_text = await cog.traceback_text_from_message(msg)
    legacy_segments = utils.split_text_into_segments(
        utils.compact_traceback_for_discord(traceback_text),
        1900,
    )
    assert len(legacy_segments) > 1
    bot.db["rai_tracebacks"] = [
        cog.traceback_fingerprint(f"\n{segment}")
        for segment in legacy_segments
    ]

    await cog.log_rai_tracebacks(msg)

    cog.chat_completion_text.assert_awaited_once()
    forum.create_thread.assert_awaited_once()
    assert cog.traceback_fingerprint(traceback_text) in _dedupe_entries(bot)


@pytest.mark.asyncio
async def test_lossy_legacy_chain_fingerprint_does_not_suppress_new_outer_error(monkeypatch):
    _configure_source_channel(monkeypatch)
    forum, _thread = _forum_with_thread()
    cog, bot = _cog(forum=forum)
    body = (
        'Traceback (most recent call last):\n'
        '  File "/old/Rai/cogs/example.py", line 10, in inner\n'
        'ValueError: shared inner failure\n\n'
        f'{utils.TRACEBACK_CAUSE_SEPARATOR}\n\n'
        'Traceback (most recent call last):\n'
        '  File "/old/Rai/cogs/example.py", line 20, in outer\n'
        'RuntimeError: materially different outer failure\n'
    )
    msg = _message(bot, body=body)
    traceback_text = await cog.traceback_text_from_message(msg)
    legacy_inner = utils.compact_traceback_for_discord(traceback_text)
    assert len(utils.split_text_into_segments(legacy_inner, 1900)) == 1
    bot.db["rai_tracebacks"] = [
        cog.traceback_fingerprint(f"\n{legacy_inner}")
    ]

    await cog.log_rai_tracebacks(msg)

    cog.chat_completion_text.assert_awaited_once()
    forum.create_thread.assert_awaited_once()
    assert cog.traceback_fingerprint(traceback_text) in _dedupe_entries(bot)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["create_thread", "ai_comment"])
async def test_transient_discord_failure_is_retried_in_place(monkeypatch, failure_stage):
    _configure_source_channel(monkeypatch)
    monkeypatch.setattr(ai_module, "TRACEBACK_DISCORD_RETRY_DELAY_SECONDS", 0)
    thread = MagicMock(spec=discord.Thread)
    thread.send = AsyncMock()
    thread.delete = AsyncMock()
    forum = MagicMock(spec=discord.ForumChannel)
    forum.id = FORUM_CHANNEL_ID

    if failure_stage == "create_thread":
        forum.create_thread = AsyncMock(
            side_effect=[_http_error(), SimpleNamespace(thread=thread)],
        )
    else:
        forum.create_thread = AsyncMock(return_value=SimpleNamespace(thread=thread))
        thread.send.side_effect = [_http_error(), None]

    cog, bot = _cog(forum=forum)
    await cog.log_rai_tracebacks(_message(bot))

    assert len(_dedupe_entries(bot)) == 1
    thread.delete.assert_not_awaited()
    if failure_stage == "create_thread":
        assert forum.create_thread.await_count == 2
        assert thread.send.await_count == 1
    else:
        assert forum.create_thread.await_count == 1
        assert thread.send.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["create_thread", "ai_comment"])
async def test_persistent_publish_failure_is_not_committed_and_can_retry(monkeypatch, failure_stage):
    _configure_source_channel(monkeypatch)
    monkeypatch.setattr(ai_module, "TRACEBACK_DISCORD_RETRY_DELAY_SECONDS", 0)
    failed_thread = MagicMock(spec=discord.Thread)
    failed_thread.send = AsyncMock()
    failed_thread.delete = AsyncMock()
    successful_thread = MagicMock(spec=discord.Thread)
    successful_thread.send = AsyncMock()
    forum = MagicMock(spec=discord.ForumChannel)
    forum.id = FORUM_CHANNEL_ID

    if failure_stage == "create_thread":
        forum.create_thread = AsyncMock(side_effect=_http_error())
    else:
        failed_thread.send.side_effect = _http_error()
        forum.create_thread = AsyncMock(return_value=SimpleNamespace(thread=failed_thread))

    cog, bot = _cog(forum=forum)
    msg = _message(bot)

    with suppress(discord.HTTPException):
        await cog.log_rai_tracebacks(msg)

    assert _dedupe_entries(bot) == []
    if failure_stage == "ai_comment":
        failed_thread.delete.assert_awaited_once()
    else:
        failed_thread.delete.assert_not_awaited()

    forum.create_thread.side_effect = None
    forum.create_thread.return_value = SimpleNamespace(thread=successful_thread)
    await cog.log_rai_tracebacks(msg)

    assert len(_dedupe_entries(bot)) == 1
    expected_create_count = 3 if failure_stage == "create_thread" else 2
    assert forum.create_thread.await_count == expected_create_count
    assert successful_thread.send.await_count >= 1


@pytest.mark.asyncio
@pytest.mark.parametrize("target_kind", ["missing", "wrong_type"])
async def test_missing_or_wrong_type_traceback_forum_is_quietly_ignored(monkeypatch, target_kind):
    _configure_source_channel(monkeypatch)
    forum = None if target_kind == "missing" else MagicMock(spec=discord.TextChannel)
    cog, bot = _cog(forum=forum)

    await cog.log_rai_tracebacks(_message(bot))

    cog.chat_completion_text.assert_not_awaited()
    assert _dedupe_entries(bot) == []


@pytest.mark.asyncio
async def test_background_error_uses_shared_traceback_sender(monkeypatch):
    bot = SimpleNamespace()
    cog = Background.__new__(Background)
    cog.bot = bot
    send_error_embed = AsyncMock()
    monkeypatch.setattr(utils, "send_error_embed", send_error_embed)
    error = RuntimeError("background failure")

    await cog.handle_error(error)

    send_error_embed.assert_awaited_once_with(bot, "Background task", error)
