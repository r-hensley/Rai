import asyncio
import types
from unittest.mock import AsyncMock, Mock

import pytest
import requests

from cogs import message as message_module
from tests.discord_fakes import make_bot, make_channel, make_guild, make_message


def make_response(payload):
    response = Mock(spec_set=requests.Response)
    response.json.return_value = payload
    return response


def test_translate_text_parses_google_json_response(monkeypatch):
    response = make_response([["test in another language", "ca"]])
    get = Mock(return_value=response)
    monkeypatch.setattr(message_module.requests, "get", get)

    translated = message_module.translate_text("test en una altra llengua", "en")

    assert translated == "test in another language"
    response.raise_for_status.assert_called_once_with()
    get.assert_called_once_with(
        message_module.GOOGLE_TRANSLATE_ENDPOINT,
        params={
            "client": "dict-chrome-ex",
            "sl": "auto",
            "tl": "en",
            "q": "test en una altra llengua",
        },
        timeout=10,
    )


def test_translate_text_rejects_google_error_page(monkeypatch):
    error_page = (
        "Error 500 (Server Error)!!1 500. That's an error. There was an error. "
        "Please try again later. That's all we know."
    )
    monkeypatch.setattr(
        message_module.requests,
        "get",
        Mock(return_value=make_response([[error_page, "ca"]])),
    )

    with pytest.raises(ValueError, match="error page"):
        message_module.translate_text("test en una altra llengua", "en")


@pytest.mark.parametrize("payload", [
    "hello", ["hello"], None, {}, [], [[]], [None],
    [{"0": "hello"}], [[None]], [[123]], [[{"text": "hello"}]],
])
def test_translate_text_rejects_invalid_response_shapes(monkeypatch, payload):
    monkeypatch.setattr(message_module.requests, "get", Mock(return_value=make_response(payload)))

    with pytest.raises(ValueError, match="invalid response"):
        message_module.translate_text("bonjour", "en")


@pytest.mark.parametrize("translated", ["", " ", "\n\t"])
def test_translate_text_rejects_blank_translation(monkeypatch, translated):
    get = Mock(return_value=make_response([[translated, "fr"]]))
    monkeypatch.setattr(message_module.requests, "get", get)
    monkeypatch.setattr(message_module, "GOOGLE_TRANSLATE_BLANK_RETRY_DELAY", 0)

    with pytest.raises(ValueError, match="empty response") as failure:
        message_module.translate_text("bonjour", "en")

    assert get.call_count == 2
    assert failure.value.__notes__ == [
        "Both attempts returned a blank translation. Target=en, detected source=fr, input characters=7."
    ]


def test_translate_text_rejects_non_json_response(monkeypatch):
    response = make_response(None)
    response.json.side_effect = ValueError("not JSON")
    monkeypatch.setattr(message_module.requests, "get", Mock(return_value=response))

    with pytest.raises(ValueError, match="invalid response"):
        message_module.translate_text("bonjour", "en")


def test_translate_text_checks_http_status_before_parsing(monkeypatch):
    response = make_response([["hello", "fr"]])
    response.raise_for_status.side_effect = message_module.requests.exceptions.HTTPError("500")
    monkeypatch.setattr(message_module.requests, "get", Mock(return_value=response))

    with pytest.raises(message_module.requests.exceptions.HTTPError):
        message_module.translate_text("bonjour", "en")
    response.json.assert_not_called()


def test_translate_text_propagates_timeout(monkeypatch):
    monkeypatch.setattr(message_module.requests, "get", Mock(side_effect=message_module.requests.exceptions.Timeout()))

    with pytest.raises(message_module.requests.exceptions.Timeout):
        message_module.translate_text("bonjour", "en")


def make_translation_handler():
    guild = make_guild(guild_id=message_module.SP_SERVER_ID)
    source_channel = make_channel(channel_id=817074401680818186, guild=guild)
    log_channel = make_channel(
        channel_id=1351961859070103637,
        guild=guild,
        permissions_for=Mock(return_value=types.SimpleNamespace(read_messages=False)),
        send=AsyncMock(),
    )
    cog = object.__new__(message_module.Message)
    cog.bot = make_bot(guilds=[guild])
    # The exact type check rejects both make_member() and spec mocks. Keep this
    # minimal real Member local; the shared factories intentionally use fakes.
    author = object.__new__(message_module.discord.Member)
    author._user = types.SimpleNamespace(id=42, name="test-user")
    author.guild = guild
    author._roles = []
    msg = make_message(
        channel=source_channel,
        author=author,
        content="Tudo vai estar bem não te preocupes",
    )
    return cog, msg, log_channel


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_target", ["en", "es"])
async def test_translation_failure_is_reported_without_posting(monkeypatch, failed_target):
    cog, msg, log_channel = make_translation_handler()
    reported = asyncio.Event()

    async def report(*args, **kwargs):
        reported.set()

    reporter = AsyncMock(side_effect=report)
    reporter.__qualname__ = "report_translation_error"
    monkeypatch.setattr(message_module.utils, "send_error_embed", reporter)
    monkeypatch.setattr(message_module.utils.here, "bot", cog.bot)

    def get_response(*args, params, **kwargs):
        if params["tl"] == failed_target:
            return make_response(["malformed response"])
        return make_response([["Everything will be fine", "pt"]])

    monkeypatch.setattr(message_module.requests, "get", Mock(side_effect=get_response))
    await message_module.Message.translate_other_lang_channel.__wrapped__(cog, msg)
    await asyncio.wait_for(reported.wait(), timeout=2)

    log_channel.send.assert_not_awaited()
    reporter.assert_awaited_once()
    assert isinstance(reporter.await_args.args[2], ValueError)


@pytest.mark.asyncio
async def test_translation_success_posts_original_and_english(monkeypatch):
    cog, msg, log_channel = make_translation_handler()
    translations = {"en": "Everything will be fine, don't worry", "es": "Todo estará bien, no te preocupes"}

    def get_response(*args, params, **kwargs):
        return make_response([[translations[params["tl"]], "pt"]])

    monkeypatch.setattr(message_module.requests, "get", Mock(side_effect=get_response))
    await message_module.Message.translate_other_lang_channel.__wrapped__(cog, msg)

    log_channel.send.assert_awaited_once()
    posted = log_channel.send.await_args.args[0]
    assert msg.content in posted
    assert translations["en"] in posted
    assert translations["es"] not in posted


@pytest.mark.asyncio
@pytest.mark.parametrize("blank_target", ["en", "es"])
async def test_blank_target_retries_and_handler_still_posts(monkeypatch, caplog, blank_target):
    cog, msg, log_channel = make_translation_handler()
    targets = {"en": "Everything will be fine", "es": "Todo va a salir bien"}
    attempts = {"en": 0, "es": 0}
    reporter = AsyncMock()
    monkeypatch.setattr(message_module.utils, "send_error_embed", reporter)
    monkeypatch.setattr(message_module, "GOOGLE_TRANSLATE_BLANK_RETRY_DELAY", 0)

    def get_response(*args, params, **kwargs):
        target = params["tl"]
        attempts[target] += 1
        value = "" if target == blank_target and attempts[target] == 1 else targets[target]
        return make_response([[value, "pt"]])

    monkeypatch.setattr(message_module.requests, "get", Mock(side_effect=get_response))
    await message_module.Message.translate_other_lang_channel.__wrapped__(cog, msg)

    assert attempts == {target: 2 if target == blank_target else 1 for target in targets}
    reporter.assert_not_awaited()
    log_channel.send.assert_awaited_once()
    assert targets["en"] in log_channel.send.await_args.args[0]
    assert f"target={blank_target} outcome=recovered" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["identical", "punctuation", "two_letters"])
async def test_english_skip_avoids_spanish_request(monkeypatch, change):
    cog, msg, log_channel = make_translation_handler()
    values = {"identical": msg.content, "punctuation": msg.content + "!!!",
              "two_letters": msg.content + "ab"}
    get = Mock(return_value=make_response([[values[change], "pt"]]))
    monkeypatch.setattr(message_module.requests, "get", get)

    await message_module.Message.translate_other_lang_channel.__wrapped__(cog, msg)

    get.assert_called_once()
    assert get.call_args.kwargs["params"]["tl"] == "en"
    log_channel.send.assert_not_awaited()


@pytest.mark.parametrize("second", ["blank", "timeout", "invalid", "recovered"])
def test_production_blank_shape_retries_once_and_logs_outcome(monkeypatch, caplog, second):
    responses = {"blank": make_response([[""]]), "timeout": requests.Timeout("private text"),
                 "invalid": make_response([]), "recovered": make_response([["hello", "fr"]])}
    get = Mock(side_effect=[make_response([[""]]), responses[second]])
    sleep = Mock()
    monkeypatch.setattr(message_module.requests, "get", get)
    monkeypatch.setattr(message_module.time, "sleep", sleep)
    if second == "recovered":
        assert message_module.translate_text("bonjour", "en") == "hello"
    else:
        with pytest.raises((ValueError, requests.Timeout)):
            message_module.translate_text("bonjour", "en")
    assert get.call_count == 2
    sleep.assert_called_once_with(0.5)
    outcome = second if second in ("blank", "recovered") else "error"
    assert f"target=en outcome={outcome}" in caplog.text
    assert "private text" not in caplog.text
    assert "bonjour" not in caplog.text
