import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest


_previous_rai_module = sys.modules.get("Rai")
if _previous_rai_module is None:
    rai_stub = types.ModuleType("Rai")
    rai_stub.Rai = type("Rai", (), {})
    sys.modules["Rai"] = rai_stub

from cogs.utils import helper_functions as hf  # noqa: E402

_previous_bot = hf.here.bot
hf.here.bot = SimpleNamespace(profiling_decorators=set())
try:
    from cogs import cnserver as cnserver_module  # noqa: E402
    from cogs import message as message_module  # noqa: E402
finally:
    hf.here.bot = _previous_bot
    if _previous_rai_module is None:
        sys.modules.pop("Rai", None)


SP_SERVER_ID = message_module.SP_SERVER_ID
TARGET_CHANNEL_ID = 1488588234471772230
TARGET_ROLE_ID = 1531353542084923572


def make_message(
        *,
        guild_id=SP_SERVER_ID,
        channel_id=TARGET_CHANNEL_ID,
        role_ids=(),
        content="This is a sufficiently long test message.",
        category_id=999,
):
    channel = Mock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.category = SimpleNamespace(id=category_id)
    guild = SimpleNamespace(id=guild_id, get_role=Mock(return_value=None))
    author = SimpleNamespace(
        bot=False,
        roles=[SimpleNamespace(id=role_id) for role_id in role_ids],
    )
    msg = Mock(spec=discord.Message)
    msg.guild = guild
    msg.channel = channel
    msg.author = author
    msg.content = content
    msg.reference = None
    return msg


def structured_rule(**overrides):
    rule = {
        "guild_id": SP_SERVER_ID,
        "channel_id": TARGET_CHANNEL_ID,
        "role_id": TARGET_ROLE_ID,
    }
    rule.update(overrides)
    return rule


def make_message_cog(*, forcehardcore, ignored=()):
    cog = object.__new__(message_module.Message)
    cog.bot = SimpleNamespace(
        db={
            "forcehardcore": forcehardcore,
            "hardcore": {str(SP_SERVER_ID): {"ignore": list(ignored)}},
        },
        stats={str(SP_SERVER_ID): {"enable": False}},
        langdetect=object(),
    )
    return cog


def test_legacy_channel_id_still_forces_everyone():
    msg = make_message(role_ids=())

    assert message_module.forced_hardcore_applies(msg, [TARGET_CHANNEL_ID]) is True


def test_structured_rule_requires_matching_guild_channel_and_role():
    msg = make_message(role_ids=[TARGET_ROLE_ID])

    assert message_module.forced_hardcore_applies(msg, [structured_rule()]) is True


@pytest.mark.parametrize(
    ("message_overrides", "rule_overrides"),
    [
        ({"guild_id": 1}, {}),
        ({"channel_id": 2}, {}),
        ({"role_ids": [3]}, {}),
        ({}, {"guild_id": 1}),
        ({}, {"channel_id": 2}),
        ({}, {"role_id": 3}),
    ],
)
def test_structured_rule_rejects_scope_mismatches(message_overrides, rule_overrides):
    message_options = {"role_ids": [TARGET_ROLE_ID], **message_overrides}
    msg = make_message(**message_options)

    assert message_module.forced_hardcore_applies(
        msg, [structured_rule(**rule_overrides)]) is False


def test_malformed_rules_are_skipped_without_hiding_later_valid_rule():
    msg = make_message(role_ids=[TARGET_ROLE_ID])
    rules = [
        None,
        "not-a-legacy-rule",
        {},
        {"channel_id": "invalid"},
        structured_rule(),
    ]

    assert message_module.forced_hardcore_applies(msg, rules) is True


def test_structured_rule_without_role_is_channel_wide():
    msg = make_message(role_ids=())
    rule = structured_rule()
    rule.pop("role_id")

    assert message_module.forced_hardcore_applies(msg, [rule]) is True


@pytest.mark.asyncio
async def test_spanish_forced_rule_bypasses_ignore_list_and_asterisk(monkeypatch):
    msg = make_message(
        role_ids=[TARGET_ROLE_ID],
        content="*This is a sufficiently long English message.",
        category_id=888,
    )
    cog = make_message_cog(
        forcehardcore=[structured_rule()],
        ignored=[TARGET_CHANNEL_ID, 888],
    )
    monkeypatch.setattr(message_module.hf, "detect_language", lambda _: "en")

    assert await message_module.Message.lang_check(cog, msg) == ("en", True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "msg",
    [
        make_message(role_ids=()),
        make_message(channel_id=123, role_ids=[TARGET_ROLE_ID]),
    ],
)
async def test_spanish_forced_rule_does_not_apply_without_full_scope(monkeypatch, msg):
    cog = make_message_cog(forcehardcore=[structured_rule()])
    monkeypatch.setattr(message_module.hf, "detect_language", lambda _: "en")

    assert await message_module.Message.lang_check(cog, msg) == (None, False)


@pytest.mark.asyncio
async def test_chinese_legacy_forcehardcore_still_bypasses_normal_role():
    msg = make_message(
        guild_id=cnserver_module.CH_SERVER_ID,
        channel_id=123,
        content="test message",
    )
    cog = object.__new__(cnserver_module.Cnserver)
    cog.bot = SimpleNamespace(db={"forcehardcore": [123], "hardcore": {}})
    cog.cn_lang_check = AsyncMock()

    await cnserver_module.Cnserver.on_message(cog, msg)

    cog.cn_lang_check.assert_awaited_once_with(msg, check_hardcore_role=False)


@pytest.mark.asyncio
async def test_missing_chinese_hardcore_config_does_not_erase_forced_rules():
    rule = structured_rule()
    msg = make_message(
        guild_id=cnserver_module.CH_SERVER_ID,
        channel_id=456,
        content="test message",
    )
    cog = object.__new__(cnserver_module.Cnserver)
    cog.bot = SimpleNamespace(db={"forcehardcore": [rule], "hardcore": {}})
    cog.cn_lang_check = AsyncMock()

    await cnserver_module.Cnserver.on_message(cog, msg)

    assert cog.bot.db["forcehardcore"] == [rule]
    cog.cn_lang_check.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("learning_role_id", "detected_lang", "content"),
    [
        (297415063302832128, "en", "This is English"),
        (247021017740869632, "es", "Este texto es español"),
    ],
)
async def test_spanish_hardcore_deletes_the_non_target_language(
        learning_role_id, detected_lang, content):
    roles = {
        role_id: SimpleNamespace(id=role_id)
        for role_id in (
            247021017740869632,
            297415063302832128,
            243853718758359040,
            247020385730691073,
        )
    }
    msg = SimpleNamespace(
        hardcore=True,
        guild=SimpleNamespace(get_role=lambda role_id: roles[role_id]),
        author=SimpleNamespace(roles=[roles[learning_role_id]]),
        detected_lang=detected_lang,
        content=content,
        delete=AsyncMock(),
    )
    cog = object.__new__(message_module.Message)

    await message_module.Message.spanish_server_hardcore.__wrapped__(cog, msg)

    msg.delete.assert_awaited_once_with()
