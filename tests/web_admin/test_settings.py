import json
import time
from copy import deepcopy
from types import SimpleNamespace

import pytest
from aiohttp import web
from multidict import MultiDict

from web_admin import config as web_config
from web_admin import security as web_security
from web_admin import settings as web_settings
from web_admin.site import WebAdminSite


GUILD_ID = web_config.SPANISH_GUILD_ID
OWNER_ID = 10
ADMIN_ID = 20
MODERATOR_ID = 30
ADMIN_ROLE_ID = web_config.SPANISH_ADMINISTRATOR_ROLE_ID
MODERATOR_ROLE_ID = 1483184760804347966


class DummyGuild:
    def __init__(self):
        self.id = GUILD_ID
        self.name = "Spanish Server"
        self.text_channels = [
            SimpleNamespace(id=101, name="mod-room"),
            SimpleNamespace(id=102, name="logs"),
            SimpleNamespace(id=103, name="general"),
        ]
        self.roles = [
            SimpleNamespace(id=GUILD_ID, name="@everyone"),
            SimpleNamespace(id=591745589054668817, name="Trial Staff Helper"),
            SimpleNamespace(id=MODERATOR_ROLE_ID, name="Moderator"),
            SimpleNamespace(id=ADMIN_ROLE_ID, name="Administrator"),
            SimpleNamespace(id=777, name="Trusted Member"),
        ]
        self.members = {
            OWNER_ID: SimpleNamespace(id=OWNER_ID, roles=[]),
            ADMIN_ID: SimpleNamespace(
                id=ADMIN_ID,
                roles=[self.get_role(ADMIN_ROLE_ID)],
            ),
            MODERATOR_ID: SimpleNamespace(
                id=MODERATOR_ID,
                roles=[self.get_role(MODERATOR_ROLE_ID)],
            ),
        }

    def get_member(self, user_id):
        return self.members.get(user_id)

    def get_role(self, role_id):
        return next((role for role in self.roles if role.id == role_id), None)

    def get_channel_or_thread(self, channel_id):
        return next((channel for channel in self.text_channels if channel.id == channel_id), None)


class DummyBot:
    def __init__(self, guild):
        self.guild = guild
        self.owner_id = OWNER_ID
        self.owner_ids = None
        self.db = {
            "mod_channel": {},
            "mod_role": {},
            "submod_role": {},
            "antispam": {},
            **{module: {} for module, _label in web_config.LOGGING_MODULES},
        }

    def get_guild(self, guild_id):
        return self.guild if guild_id == self.guild.id else None


class FakeRequest:
    def __init__(self, cookie, *, form=None, query=None, guild_id=GUILD_ID):
        self.cookies = {web_security.SESSION_COOKIE: cookie}
        self.match_info = {"guild_id": str(guild_id)}
        self.query = query or {}
        self._form = form or MultiDict()

    async def post(self):
        return self._form


@pytest.fixture
def settings_site(monkeypatch):
    environment = {
        "WEB_ADMIN_ENABLED": "true",
        "WEB_ADMIN_BIND_HOST": "127.0.0.1",
        "WEB_ADMIN_PORT": "8765",
        "WEB_ADMIN_PUBLIC_BASE_URL": "https://admin.example.com",
        "WEB_ADMIN_SESSION_SECRET": "test-only-session-secret-with-at-least-32-bytes",
        "WEB_ADMIN_ALLOWED_GUILDS": str(GUILD_ID),
        "WEB_ADMIN_GUILD_ADMINS": json.dumps({str(GUILD_ID): [OWNER_ID]}),
        "WEB_ADMIN_OWNER_USERS": str(OWNER_ID),
        "WEB_ADMIN_COOKIE_SECURE": "true",
        "DISCORD_CLIENT_ID": "client-id",
        "DISCORD_CLIENT_SECRET": "client-secret",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    guild = DummyGuild()
    return WebAdminSite(DummyBot(guild))


def session_request(site, user_id, *, form=None, query=None, csrf=True):
    session = {
        "user_id": user_id,
        "username": f"User {user_id}",
        "iat": int(time.time()),
    }
    if form is not None and csrf:
        form.add("csrf_token", site._csrf_token(session, GUILD_ID))
    cookie = site._sign_payload(session)
    return FakeRequest(cookie, form=form, query=query), session


async def successful_dump(_name):
    return None


def test_only_owner_and_administrator_can_manage_settings(settings_site):
    assert settings_site._can_manage_guild(GUILD_ID, OWNER_ID) is True
    assert settings_site._can_manage_guild(GUILD_ID, ADMIN_ID) is True
    assert settings_site._can_manage_guild(GUILD_ID, MODERATOR_ID) is False


def test_csrf_token_is_bound_to_session_and_guild(settings_site):
    session = {"user_id": OWNER_ID, "iat": 1_000}
    token = settings_site._csrf_token(session, GUILD_ID)

    assert settings_site._valid_csrf_token(session, GUILD_ID, token) is True
    assert settings_site._valid_csrf_token(session, GUILD_ID + 1, token) is False
    assert settings_site._valid_csrf_token({"user_id": ADMIN_ID, "iat": 1_000}, GUILD_ID, token) is False
    assert settings_site._valid_csrf_token(session, GUILD_ID, "tampered") is False


@pytest.mark.asyncio
async def test_moderator_sees_read_only_settings(settings_site):
    request, _session = session_request(settings_site, MODERATOR_ID)

    response = await settings_site.settings_detail(request)

    assert response.status == 200
    assert "Read-only access" in response.text
    assert "Save staff settings" not in response.text
    assert "Save antispam settings" not in response.text


@pytest.mark.asyncio
async def test_moderator_cannot_post_settings(settings_site, monkeypatch):
    called = False

    async def dump(_name):
        nonlocal called
        called = True

    monkeypatch.setattr(web_settings.utils, "dump_json", dump)
    form = MultiDict({"mod_channel": "101"})
    request, _session = session_request(settings_site, MODERATOR_ID, form=form)

    response = await settings_site.update_staff_settings(request)

    assert response.status == 403
    assert called is False
    assert settings_site.bot.db["mod_channel"] == {}


@pytest.mark.asyncio
async def test_administrator_role_is_rechecked_before_each_write(settings_site, monkeypatch):
    monkeypatch.setattr(web_settings.utils, "dump_json", successful_dump)
    form = MultiDict({"mod_channel": "101"})
    request, _session = session_request(settings_site, ADMIN_ID, form=form)
    settings_site.bot.guild.members[ADMIN_ID].roles = [
        settings_site.bot.guild.get_role(MODERATOR_ROLE_ID),
    ]

    response = await settings_site.update_staff_settings(request)

    assert response.status == 403
    assert settings_site.bot.db["mod_channel"] == {}


@pytest.mark.asyncio
async def test_invalid_csrf_rejects_configuration_write(settings_site, monkeypatch):
    called = False

    async def dump(_name):
        nonlocal called
        called = True

    monkeypatch.setattr(web_settings.utils, "dump_json", dump)
    form = MultiDict({"mod_channel": "101", "csrf_token": "invalid"})
    request, _session = session_request(settings_site, ADMIN_ID, form=form, csrf=False)

    response = await settings_site.update_staff_settings(request)

    assert response.status == 403
    assert called is False
    assert settings_site.bot.db["mod_channel"] == {}


@pytest.mark.asyncio
async def test_staff_settings_save_existing_database_shapes(settings_site, monkeypatch):
    calls = []

    async def dump(name):
        calls.append(name)

    monkeypatch.setattr(web_settings.utils, "dump_json", dump)
    form = MultiDict([
        ("mod_channel", "101"),
        ("mod_roles", str(ADMIN_ROLE_ID)),
        ("mod_roles", str(MODERATOR_ROLE_ID)),
        ("submod_roles", "591745589054668817"),
    ])
    request, _session = session_request(settings_site, ADMIN_ID, form=form)

    response = await settings_site.update_staff_settings(request)

    guild_key = str(GUILD_ID)
    assert response.status == 303
    assert response.headers["Location"] == f"/settings/{GUILD_ID}?saved=staff"
    assert settings_site.bot.db["mod_channel"][guild_key] == 101
    assert settings_site.bot.db["mod_role"][guild_key]["id"] == [ADMIN_ROLE_ID, MODERATOR_ROLE_ID]
    assert settings_site.bot.db["submod_role"][guild_key]["id"] == [591745589054668817]
    assert calls == ["db"]


@pytest.mark.asyncio
async def test_logging_settings_preserve_module_specific_data(settings_site, monkeypatch):
    monkeypatch.setattr(web_settings.utils, "dump_json", successful_dump)
    guild_key = str(GUILD_ID)
    settings_site.bot.db["joins"][guild_key] = {
        "enable": True,
        "channel": 101,
        "invites_enable": True,
        "readd_roles": {"enable": True},
    }
    form = MultiDict([
        ("deletes_enabled", "on"),
        ("deletes_channel", "102"),
        ("joins_channel", "103"),
    ])
    request, _session = session_request(settings_site, OWNER_ID, form=form)

    response = await settings_site.update_logging_settings(request)

    assert response.status == 303
    assert settings_site.bot.db["deletes"][guild_key] == {"enable": True, "channel": 102}
    assert settings_site.bot.db["joins"][guild_key] == {
        "enable": False,
        "channel": 103,
        "invites_enable": True,
        "readd_roles": {"enable": True},
    }


@pytest.mark.asyncio
async def test_antispam_settings_save_ignored_channels_and_exempt_roles(settings_site, monkeypatch, caplog):
    monkeypatch.setattr(web_settings.utils, "dump_json", successful_dump)
    form = MultiDict([
        ("enabled", "on"),
        ("action", "mute"),
        ("message_threshold", "5"),
        ("time_threshold", "12"),
        ("ban_override", "30"),
        ("ignored_channels", "102"),
        ("ignored_channels", "103"),
        ("exempt_roles", "777"),
    ])
    request, _session = session_request(settings_site, ADMIN_ID, form=form)

    with caplog.at_level("WARNING", logger="rai.web_admin.audit"):
        response = await settings_site.update_antispam_settings(request)

    assert response.status == 303
    assert settings_site.bot.db["antispam"][str(GUILD_ID)] == {
        "enable": True,
        "action": "mute",
        "message_threshold": 5,
        "time_threshold": 12,
        "ban_override": 30,
        "ignored": [102, 103],
        "exempt_roles": [777],
    }
    assert f"actor_user_id={ADMIN_ID}" in caplog.text
    assert f"guild_id={GUILD_ID}" in caplog.text
    assert "area=antispam" in caplog.text


@pytest.mark.asyncio
async def test_invalid_server_selection_is_rejected_without_saving(settings_site, monkeypatch):
    called = False

    async def dump(_name):
        nonlocal called
        called = True

    monkeypatch.setattr(web_settings.utils, "dump_json", dump)
    form = MultiDict([
        ("action", "ban"),
        ("message_threshold", "5"),
        ("time_threshold", "10"),
        ("ban_override", "0"),
        ("ignored_channels", "999999"),
    ])
    request, _session = session_request(settings_site, OWNER_ID, form=form)

    response = await settings_site.update_antispam_settings(request)

    assert response.status == 400
    assert "invalid server selection" in response.text
    assert called is False
    assert settings_site.bot.db["antispam"] == {}


@pytest.mark.asyncio
async def test_failed_persistence_restores_previous_configuration(settings_site, monkeypatch):
    guild_key = str(GUILD_ID)
    original = {
        "enable": False,
        "action": "kick",
        "message_threshold": 8,
        "time_threshold": 20,
        "ignored": [101],
        "exempt_roles": [],
        "ban_override": 0,
    }
    settings_site.bot.db["antispam"][guild_key] = deepcopy(original)

    async def fail_dump(_name):
        raise OSError("disk unavailable")

    monkeypatch.setattr(web_settings.utils, "dump_json", fail_dump)
    form = MultiDict([
        ("enabled", "on"),
        ("action", "ban"),
        ("message_threshold", "3"),
        ("time_threshold", "4"),
        ("ban_override", "5"),
    ])
    request, _session = session_request(settings_site, OWNER_ID, form=form)

    response = await settings_site.update_antispam_settings(request)

    assert response.status == 503
    assert settings_site.bot.db["antispam"][guild_key] == original


@pytest.mark.asyncio
async def test_malformed_existing_configuration_is_not_overwritten(settings_site, monkeypatch):
    called = False

    async def dump(_name):
        nonlocal called
        called = True

    monkeypatch.setattr(web_settings.utils, "dump_json", dump)
    guild_key = str(GUILD_ID)
    settings_site.bot.db["antispam"][guild_key] = ["malformed"]
    form = MultiDict([
        ("action", "mute"),
        ("message_threshold", "5"),
        ("time_threshold", "10"),
        ("ban_override", "0"),
    ])
    request, _session = session_request(settings_site, OWNER_ID, form=form)

    response = await settings_site.update_antispam_settings(request)

    assert response.status == 400
    assert called is False
    assert settings_site.bot.db["antispam"][guild_key] == ["malformed"]


@pytest.mark.asyncio
async def test_settings_template_escapes_discord_names(settings_site):
    settings_site.bot.guild.text_channels[0].name = '<script>alert("channel")</script>'
    settings_site.bot.guild.roles[-1].name = '<script>alert("role")</script>'
    request, _session = session_request(settings_site, OWNER_ID)

    response = await settings_site.settings_detail(request)

    assert response.status == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


@pytest.mark.asyncio
async def test_settings_routes_are_registered_with_bounded_request_body(settings_site, monkeypatch):
    async def no_op_start(_site):
        return None

    monkeypatch.setattr(web.TCPSite, "start", no_op_start)
    await settings_site.start()
    try:
        routes = {
            (route.method, route.resource.canonical)
            for route in settings_site.runner.app.router.routes()
        }
        assert ("GET", "/settings") in routes
        assert ("GET", "/settings/{guild_id}") in routes
        assert ("POST", "/settings/{guild_id}/staff") in routes
        assert ("POST", "/settings/{guild_id}/logging") in routes
        assert ("POST", "/settings/{guild_id}/antispam") in routes
        assert settings_site.runner.app._client_max_size == 64 * 1024
    finally:
        await settings_site.stop()
