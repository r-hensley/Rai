from types import SimpleNamespace

import pytest

import cogs.owner as owner_module


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

    class FakeBot:
        async def reload_extension(self, extension_name):
            events.append(("reload", extension_name))

    class FakeMessage:
        async def delete(self):
            events.append(("delete", None))

    async def reload_success(_ctx, cog):
        events.append(("success", cog))

    monkeypatch.setattr(
        owner_module,
        "_clear_imported_package",
        lambda package_name: events.append(("clear", package_name)),
    )
    owner = owner_module.Owner(FakeBot())
    monkeypatch.setattr(owner, "reload_success", reload_success)
    ctx = SimpleNamespace(message=FakeMessage())

    await owner_module.Owner.reload.callback(owner, ctx, cogs="web_admin")

    assert events == [
        ("delete", None),
        ("clear", "web_admin"),
        ("reload", "cogs.web_admin"),
        ("success", "web_admin"),
    ]
