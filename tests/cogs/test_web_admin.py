import json
import time as stdlib_time

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

import cogs.web_admin as web_admin


WEB_ENV = {
    "WEB_ADMIN_ENABLED": "true",
    "WEB_ADMIN_BIND_HOST": "127.0.0.1",
    "WEB_ADMIN_PORT": "8765",
    "WEB_ADMIN_PUBLIC_BASE_URL": "https://admin.example.com",
    "WEB_ADMIN_SESSION_SECRET": "test-only-session-secret-with-at-least-32-bytes",
    "WEB_ADMIN_ALLOWED_GUILDS": "1,2",
    "WEB_ADMIN_GUILD_ADMINS": json.dumps({"1": [10], "2": [20]}),
    "WEB_ADMIN_COOKIE_SECURE": "true",
    "DISCORD_CLIENT_ID": "client-id",
    "DISCORD_CLIENT_SECRET": "client-secret",
}


class DummyBot:
    def __init__(self):
        self.ready = True
        self.user = None
        self.guilds = []
        self.cogs = {}
        self.bg_tasks = []
        self.db = {}
        self.stats = {}
        self.latency = 0.0
        self.live_latency = None
        self.t_start_monotonic = stdlib_time.monotonic()

    def is_ready(self):
        return self.ready

    def get_guild(self, _guild_id):
        return None


def make_cog(monkeypatch, **overrides):
    values = WEB_ENV | overrides
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return web_admin.WebAdmin(DummyBot())


def request_with_cookie(name, value):
    return make_mocked_request("GET", "/", headers={"Cookie": f"{name}={value}"})


def test_guild_scope_has_no_default_fallback(monkeypatch):
    cog = make_cog(monkeypatch, WEB_ADMIN_ALLOWED_GUILDS=None)

    assert cog.allowed_guilds == set()
    assert "WEB_ADMIN_ALLOWED_GUILDS is required" in cog._configuration_errors()


def test_invalid_guild_scope_fails_closed(monkeypatch):
    cog = make_cog(monkeypatch, WEB_ADMIN_ALLOWED_GUILDS="1,not-an-id")

    assert cog.allowed_guilds == set()
    assert any("WEB_ADMIN_ALLOWED_GUILDS" in error for error in cog._configuration_errors())


def test_weak_session_secret_is_rejected(monkeypatch):
    cog = make_cog(
        monkeypatch,
        WEB_ADMIN_SESSION_SECRET="replace-with-a-long-random-string-that-is-not-random",
    )

    assert any("randomly generated" in error for error in cog._configuration_errors())


def test_public_configuration_requires_loopback_https_and_secure_cookies(monkeypatch):
    cog = make_cog(
        monkeypatch,
        WEB_ADMIN_BIND_HOST="0.0.0.0",
        WEB_ADMIN_PUBLIC_BASE_URL="http://admin.example.com",
        WEB_ADMIN_COOKIE_SECURE="false",
    )

    errors = cog._configuration_errors()
    assert "WEB_ADMIN_BIND_HOST must be a loopback host" in errors
    assert "WEB_ADMIN_PUBLIC_BASE_URL must use HTTPS except for local testing" in errors


def test_malformed_public_url_is_a_config_error(monkeypatch):
    cog = make_cog(monkeypatch, WEB_ADMIN_PUBLIC_BASE_URL="https://[invalid")

    assert any("WEB_ADMIN_PUBLIC_BASE_URL must contain only" in error for error in cog._configuration_errors())


def test_authorization_is_scoped_per_guild(monkeypatch):
    cog = make_cog(monkeypatch)

    assert cog._authorized_guild_ids(10) == {1}
    assert cog._authorized_guild_ids(20) == {2}
    assert cog._authorized_guild_ids(30) == set()
    assert cog._guild_rows({1}) == [("1", "not visible to bot")]


@pytest.mark.asyncio
async def test_dashboard_rechecks_authorization_for_existing_session(monkeypatch):
    cog = make_cog(monkeypatch)
    session_cookie = cog._sign_payload({"user_id": 10, "username": "Admin", "iat": int(stdlib_time.time())})
    request = request_with_cookie(web_admin.SESSION_COOKIE, session_cookie)

    authorized_response = await cog.dashboard(request)
    assert "Dashboard guild count" in authorized_response.text
    assert '<meta http-equiv="refresh" content="30">' in authorized_response.text

    cog.guild_admins[1].remove(10)
    revoked_response = await cog.dashboard(request)
    assert "Log in with Discord" in revoked_response.text
    assert revoked_response.cookies[web_admin.SESSION_COOKIE]["max-age"] == "0"


def test_signed_cookie_rejects_tampering_expiry_and_future_issue_time(monkeypatch):
    cog = make_cog(monkeypatch)
    monkeypatch.setattr(web_admin.time, "time", lambda: 1_000)

    valid = cog._sign_payload({"iat": 900, "user_id": 10})
    assert cog._read_signed_cookie(request_with_cookie("test", valid), "test", 200)["user_id"] == 10

    tampered = f"{valid[:-1]}{'A' if valid[-1] != 'A' else 'B'}"
    assert cog._read_signed_cookie(request_with_cookie("test", tampered), "test", 200) is None

    expired = cog._sign_payload({"iat": 700, "user_id": 10})
    assert cog._read_signed_cookie(request_with_cookie("test", expired), "test", 200) is None

    future = cog._sign_payload({"iat": 1_100, "user_id": 10})
    assert cog._read_signed_cookie(request_with_cookie("test", future), "test", 200) is None


def test_refresh_is_only_present_when_requested(monkeypatch):
    cog = make_cog(monkeypatch)

    assert "http-equiv=\"refresh\"" not in cog._page("Login Failed", "<p>failed</p>")
    assert '<meta http-equiv="refresh" content="30">' in cog._page(
        "Rai Admin",
        "<p>ready</p>",
        refresh_seconds=30,
    )


@pytest.mark.asyncio
async def test_security_headers_apply_to_responses(monkeypatch):
    make_cog(monkeypatch)

    async def handler(_request):
        return web.Response(text="ok")

    response = await web_admin._security_headers_middleware(
        make_mocked_request("GET", "/"),
        handler,
    )

    for name, value in web_admin.SECURITY_HEADERS.items():
        assert response.headers[name] == value


@pytest.mark.asyncio
async def test_security_headers_apply_to_internal_errors(monkeypatch):
    make_cog(monkeypatch)

    async def handler(_request):
        raise RuntimeError("diagnostic failure")

    response = await web_admin._security_headers_middleware(
        make_mocked_request("GET", "/"),
        handler,
    )

    assert response.status == 500
    assert response.text == "Internal server error."
    for name, value in web_admin.SECURITY_HEADERS.items():
        assert response.headers[name] == value


@pytest.mark.asyncio
async def test_healthz_is_generic_and_reports_readiness(monkeypatch):
    cog = make_cog(monkeypatch)

    unavailable = await cog.healthz(make_mocked_request("GET", "/healthz"))
    assert unavailable.status == 503
    assert json.loads(unavailable.text) == {"ok": False}
    assert "guild" not in unavailable.text

    cog.web_ready = True
    available = await cog.healthz(make_mocked_request("GET", "/healthz"))
    assert available.status == 200
    assert json.loads(available.text) == {"ok": True}


@pytest.mark.asyncio
async def test_startup_failure_does_not_escape_cog(monkeypatch):
    cog = make_cog(monkeypatch)

    async def fail_start(_site):
        raise OSError("address unavailable")

    monkeypatch.setattr(web.TCPSite, "start", fail_start)
    await cog.cog_load()

    assert cog.web_ready is False
    assert cog.runner is None
    assert cog.site is None


def test_uptime_uses_monotonic_clock(monkeypatch):
    cog = make_cog(monkeypatch)
    cog.bot.t_start_monotonic = 100.0
    monkeypatch.setattr(web_admin.time, "monotonic", lambda: 190.0)

    rows = dict(cog._bot_rows({1}))
    assert rows["Uptime"] == "0:01:30"


def test_malformed_diagnostics_are_reported_instead_of_raising(monkeypatch):
    cog = make_cog(monkeypatch)
    cog.bot.db = {
        "mod_role": {"1": []},
        "antispam": {"1": {"enable": True, "ignored": None}},
        "wordfilter": {"1": []},
    }
    cog.bot.stats = []

    rows = cog._guild_config_health_rows("1", "Guild", None)

    assert ("Guild: mod role", "invalid config") in rows
    assert ("Guild: wordfilter", "invalid config") in rows
    assert ("Guild: stats", "invalid config") in rows
    assert any(key == "Guild: antispam" and "ignored channels invalid" in value for key, value in rows)
