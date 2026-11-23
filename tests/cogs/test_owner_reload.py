from unittest.mock import AsyncMock

import pytest

import cogs.owner as owner_module
from tests.discord_fakes import make_bot, make_context, make_message


@pytest.mark.asyncio
async def test_reload_utils_reloads_views_after_bot_utils(monkeypatch):
    events = []

    def reload_module(module):
        events.append(("reload", module.__name__))
        return module

    def setup_utils(*, bot, loop):
        assert bot is owner.bot
        assert loop is not None
        events.append(("setup", "bot_utils"))

    async def reload_success(_ctx, cog):
        events.append(("success", cog))

    monkeypatch.setattr(owner_module.importlib, "reload", reload_module)
    monkeypatch.setattr(owner_module.utils, "setup", setup_utils)
    bot = make_bot()
    message = make_message(
        delete=AsyncMock(side_effect=lambda: events.append(("delete", None))),
    )
    owner = owner_module.Owner(bot)
    monkeypatch.setattr(owner, "reload_success", reload_success)
    ctx = make_context(message=message)

    await owner_module.Owner.reload.callback(owner, ctx, cogs="utils")

    assert events == [
        ("delete", None),
        ("reload", "cogs.utils.BotUtils.git_utils"),
        ("reload", "cogs.utils.BotUtils.bot_utils"),
        ("setup", "bot_utils"),
        ("reload", "cogs.utils.views"),
        ("success", "utils"),
    ]


@pytest.mark.asyncio
async def test_owner_reloads_web_admin_through_bot(monkeypatch):
    events = []

    async def reload_success(_ctx, cog):
        events.append(("success", cog))

    bot = make_bot(
        reload_extension=AsyncMock(
            side_effect=lambda extension_name: events.append(
                ("reload", extension_name)
            ),
        ),
    )
    message = make_message(
        delete=AsyncMock(side_effect=lambda: events.append(("delete", None))),
    )
    owner = owner_module.Owner(bot)
    monkeypatch.setattr(owner, "reload_success", reload_success)
    ctx = make_context(message=message)

    await owner_module.Owner.reload.callback(owner, ctx, cogs="web_admin")

    assert events == [
        ("delete", None),
        ("reload", "cogs.web_admin"),
        ("success", "web_admin"),
    ]
