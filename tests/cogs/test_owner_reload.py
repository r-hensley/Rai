import pytest
from unittest.mock import AsyncMock

import cogs.owner as owner_module
from tests.discord_fakes import make_bot, make_context, make_message


def test_clear_imported_package_only_removes_requested_tree(monkeypatch):
    module_cache = {
        "web_admin": object(),
        "web_admin.auth": object(),
        "web_admin.views.components": object(),
        "web_admin_extra": object(),
        "cogs.web_admin": object(),
    }
    invalidated = []
    monkeypatch.setattr(owner_module.importlib, "invalidate_caches", lambda: invalidated.append(True))

    owner_module._clear_imported_package("web_admin", module_cache)

    assert module_cache == {
        "web_admin_extra": module_cache["web_admin_extra"],
        "cogs.web_admin": module_cache["cogs.web_admin"],
    }
    assert invalidated == [True]


@pytest.mark.asyncio
async def test_reload_web_admin_clears_package_before_extension(monkeypatch):
    events = []

    async def reload_success(_ctx, cog):
        events.append(("success", cog))

    monkeypatch.setattr(
        owner_module,
        "_clear_imported_package",
        lambda package_name: events.append(("clear", package_name)),
    )
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
        ("clear", "web_admin"),
        ("reload", "cogs.web_admin"),
        ("success", "web_admin"),
    ]
