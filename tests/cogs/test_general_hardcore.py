from unittest.mock import AsyncMock

import pytest

from cogs import general as general_module
from tests.discord_fakes import make_bot, make_context, make_guild, make_member, make_role


SP_SERVER_ID = general_module.SP_SERVER_ID
LEARNING_ENGLISH_ROLE_ID = 247021017740869632
NIGHTMARE_HARDCORE_ROLE_ID = general_module.SP_NIGHTMARE_HARDCORE_ROLE_ID
TRIAL_STAFF_ROLE_ID = general_module.SP_TRIAL_STAFF_ROLE_ID
SERVER_STAFF_ROLE_ID = general_module.SP_SERVER_STAFF_ROLE_ID


def make_role_map(*role_ids):
    return {
        role_id: make_role(role_id=role_id)
        for role_id in role_ids
    }


@pytest.mark.parametrize("staff_role_id", [TRIAL_STAFF_ROLE_ID, SERVER_STAFF_ROLE_ID])
def test_hardcore_staff_check_allows_spanish_trial_and_server_staff(monkeypatch, staff_role_id):
    staff_role = make_role(role_id=staff_role_id)
    guild = make_guild(guild_id=SP_SERVER_ID, roles=[staff_role])
    author = make_member(member_id=42, guild=guild, roles=[staff_role])
    ctx = make_context(author=author, guild=guild)
    monkeypatch.setattr(general_module.hf, "admin_check", lambda _: False)

    assert general_module.hardcore_staff_check(ctx) is True


def test_hardcore_staff_check_preserves_admin_access_in_other_guilds(monkeypatch):
    guild = make_guild(guild_id=general_module.CH_SERVER_ID)
    author = make_member(member_id=42, guild=guild)
    ctx = make_context(author=author, guild=guild)
    monkeypatch.setattr(general_module.hf, "admin_check", lambda _: True)

    assert general_module.hardcore_staff_check(ctx) is True


def test_hardcore_staff_check_rejects_nonstaff_and_nonspanish_staff_role(monkeypatch):
    monkeypatch.setattr(general_module.hf, "admin_check", lambda _: False)

    spanish_guild = make_guild(guild_id=SP_SERVER_ID)
    ordinary_member = make_member(member_id=42, guild=spanish_guild)
    ordinary_ctx = make_context(author=ordinary_member, guild=spanish_guild)
    assert general_module.hardcore_staff_check(ordinary_ctx) is False

    trial_role = make_role(role_id=TRIAL_STAFF_ROLE_ID)
    other_guild = make_guild(guild_id=general_module.CH_SERVER_ID, roles=[trial_role])
    other_member = make_member(member_id=43, guild=other_guild, roles=[trial_role])
    other_ctx = make_context(author=other_member, guild=other_guild)
    assert general_module.hardcore_staff_check(other_ctx) is False


def test_hardcore_staff_check_is_applied_to_remove_and_list_commands():
    assert general_module.hardcore_staff_check in general_module.General.hardcore_remove.checks
    assert general_module.hardcore_staff_check in general_module.General.list_channels.checks


@pytest.mark.asyncio
async def test_admin_remove_recognizes_nightmare_hardcore(monkeypatch):
    roles = make_role_map(*general_module.SP_HARDCORE_ROLE_IDS)
    nightmare_role = roles[NIGHTMARE_HARDCORE_ROLE_ID]
    guild = make_guild(
        guild_id=SP_SERVER_ID,
        name="Spanish-English Language Exchange",
        roles=roles.values(),
    )
    member = make_member(
        member_id=42,
        guild=guild,
        roles=[nightmare_role],
        remove_roles=AsyncMock(),
        send=AsyncMock(),
    )
    moderator = make_member(member_id=99, guild=guild)
    ctx = make_context(
        author=moderator,
        guild=guild,
    )
    cog = object.__new__(general_module.General)
    cog.bot = make_bot(
        db={
            "hardcore": {
                str(SP_SERVER_ID): {
                    "users": {
                        str(member.id): {
                            "threshold": 100,
                            "target_lang": "en",
                        },
                    },
                },
            },
        },
    )
    safe_send = AsyncMock()
    monkeypatch.setattr(general_module.utils, "safe_send", safe_send)

    await general_module.General.hardcore_remove.callback(cog, ctx, member)

    member.remove_roles.assert_awaited_once_with(nightmare_role)
    assert cog.bot.db["hardcore"][str(SP_SERVER_ID)]["users"] == {}
    safe_send.assert_awaited_once_with(
        ctx,
        f"Removed hardcore from {member.mention} and cleared any threshold lock.",
    )


@pytest.mark.asyncio
async def test_self_service_hardcore_removes_nightmare_without_adding_standard_role(monkeypatch):
    roles = make_role_map(
        *general_module.SP_HARDCORE_ROLE_IDS,
        LEARNING_ENGLISH_ROLE_ID,
    )
    nightmare_role = roles[NIGHTMARE_HARDCORE_ROLE_ID]
    learning_role = roles[LEARNING_ENGLISH_ROLE_ID]
    guild = make_guild(
        guild_id=SP_SERVER_ID,
        roles=roles.values(),
    )
    author = make_member(
        member_id=42,
        guild=guild,
        roles=[nightmare_role, learning_role],
        add_roles=AsyncMock(),
        remove_roles=AsyncMock(),
    )
    ctx = make_context(author=author, guild=guild)
    cog = object.__new__(general_module.General)
    cog.bot = make_bot(
        db={
            "hardcore": {
                str(SP_SERVER_ID): {
                    "users": {},
                },
            },
        },
    )
    safe_send = AsyncMock()
    monkeypatch.setattr(general_module.utils, "safe_send", safe_send)

    await general_module.General.hardcore_spanish_serv(cog, ctx, 0)

    author.remove_roles.assert_awaited_once_with(nightmare_role)
    author.add_roles.assert_not_awaited()
    safe_send.assert_awaited_once_with(ctx, "I've removed hardcore from you.")
