import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


_previous_rai_module = sys.modules.get("Rai")
if _previous_rai_module is None:
    rai_stub = types.ModuleType("Rai")
    rai_stub.Rai = type("Rai", (), {})
    sys.modules["Rai"] = rai_stub

from cogs import general as general_module  # noqa: E402

if _previous_rai_module is None:
    sys.modules.pop("Rai", None)


SP_SERVER_ID = general_module.SP_SERVER_ID
LEARNING_ENGLISH_ROLE_ID = 247021017740869632
NIGHTMARE_HARDCORE_ROLE_ID = general_module.SP_NIGHTMARE_HARDCORE_ROLE_ID


def make_role_map(*role_ids):
    return {
        role_id: SimpleNamespace(id=role_id)
        for role_id in role_ids
    }


@pytest.mark.asyncio
async def test_admin_remove_recognizes_nightmare_hardcore(monkeypatch):
    roles = make_role_map(*general_module.SP_HARDCORE_ROLE_IDS)
    nightmare_role = roles[NIGHTMARE_HARDCORE_ROLE_ID]
    guild = SimpleNamespace(
        id=SP_SERVER_ID,
        name="Spanish-English Language Exchange",
        get_role=Mock(side_effect=roles.get),
    )
    member = SimpleNamespace(
        id=42,
        mention="<@42>",
        roles=[nightmare_role],
        remove_roles=AsyncMock(),
        send=AsyncMock(),
    )
    ctx = SimpleNamespace(
        author=SimpleNamespace(id=99),
        guild=guild,
    )
    cog = object.__new__(general_module.General)
    cog.bot = SimpleNamespace(
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
    guild = SimpleNamespace(
        id=SP_SERVER_ID,
        get_role=Mock(side_effect=roles.get),
    )
    author = SimpleNamespace(
        id=42,
        roles=[nightmare_role, learning_role],
        add_roles=AsyncMock(),
        remove_roles=AsyncMock(),
    )
    ctx = SimpleNamespace(author=author, guild=guild)
    cog = object.__new__(general_module.General)
    cog.bot = SimpleNamespace(
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
