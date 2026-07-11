import asyncio
import logging
import os
from typing import Optional
from urllib.parse import urlsplit

from aiohttp import web
from discord.ext import commands

from .auth import AuthMixin
from .config import (
    LOCAL_HOSTS,
    MIN_SESSION_SECRET_BYTES,
    WEAK_SESSION_SECRETS,
    env_bool,
    parse_guild_admins,
    parse_int_set,
)
from .diagnostics import DiagnosticsMixin
from .rendering import STATIC_DIR, TemplateRenderer
from .security import (
    SESSION_COOKIE,
    security_headers_middleware,
)
from .settings import SettingsMixin
from .views import DashboardViewMixin


log = logging.getLogger(__name__)


class WebAdminSite(AuthMixin, DashboardViewMixin, SettingsMixin, DiagnosticsMixin):
    """Authenticated web dashboard for Rai diagnostics and controlled configuration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.renderer = TemplateRenderer()
        self.enabled = env_bool("WEB_ADMIN_ENABLED", False)
        self.host = os.getenv("WEB_ADMIN_BIND_HOST", "127.0.0.1")
        self._config_parse_errors: list[str] = []
        try:
            self.port = int(os.getenv("WEB_ADMIN_PORT", "8765"))
        except ValueError:
            self.port = 8765
            self._config_parse_errors.append("WEB_ADMIN_PORT must be an integer")
        self.public_base_url = os.getenv("WEB_ADMIN_PUBLIC_BASE_URL", "").rstrip("/")
        self.client_id = os.getenv("DISCORD_CLIENT_ID", "")
        self.client_secret = os.getenv("DISCORD_CLIENT_SECRET", "")
        self.session_secret = os.getenv("WEB_ADMIN_SESSION_SECRET", "")
        try:
            self.allowed_guilds = parse_int_set(os.getenv("WEB_ADMIN_ALLOWED_GUILDS"))
        except ValueError:
            self.allowed_guilds = set()
            self._config_parse_errors.append(
                "WEB_ADMIN_ALLOWED_GUILDS must be a comma-separated list of positive integer IDs"
            )
        try:
            self.guild_admins = parse_guild_admins(os.getenv("WEB_ADMIN_GUILD_ADMINS"))
        except ValueError as exc:
            self.guild_admins = {}
            self._config_parse_errors.append(f"WEB_ADMIN_GUILD_ADMINS {exc}")
        try:
            self.owner_users = parse_int_set(
                os.getenv("WEB_ADMIN_OWNER_USERS") or os.getenv("OWNER_ID")
            )
        except ValueError:
            self.owner_users = set()
            self._config_parse_errors.append(
                "WEB_ADMIN_OWNER_USERS or OWNER_ID must contain positive integer IDs"
            )
        self.cookie_secure = env_bool("WEB_ADMIN_COOKIE_SECURE", True)
        self.config_write_lock = asyncio.Lock()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.web_ready = False

    async def start(self) -> None:
        if not self.enabled:
            print("Web admin dashboard disabled. Set WEB_ADMIN_ENABLED=true to enable it.")
            return

        config_errors = self._configuration_errors()
        if config_errors:
            log.error("Web admin dashboard not started: %s", "; ".join(config_errors))
            return

        try:
            app = web.Application(
                middlewares=[security_headers_middleware],
                client_max_size=64 * 1024,
            )
            app.add_routes([
                web.get("/", self.dashboard),
                web.get("/login", self.login),
                web.get("/oauth/callback", self.oauth_callback),
                web.get("/logout", self.logout),
                web.get("/healthz", self.healthz),
                web.get("/settings", self.settings_index),
                web.get(r"/settings/{guild_id:\d+}", self.settings_detail),
                web.post(r"/settings/{guild_id:\d+}/staff", self.update_staff_settings),
                web.post(r"/settings/{guild_id:\d+}/logging", self.update_logging_settings),
                web.post(r"/settings/{guild_id:\d+}/antispam", self.update_antispam_settings),
            ])
            app.router.add_static("/static/", STATIC_DIR, show_index=False)

            # The OAuth callback query contains a short-lived authorization code.
            self.runner = web.AppRunner(app, access_log=None)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
        except Exception:
            log.exception("Web admin dashboard failed to start; Rai will continue without it")
            await self._stop_server()
            return

        self.web_ready = True
        log.info("Web admin dashboard listening on http://%s:%s", self.host, self.port)

    async def stop(self) -> None:
        await self._stop_server()

    async def _stop_server(self) -> None:
        self.web_ready = False
        self.site = None
        if self.runner:
            try:
                await self.runner.cleanup()
            except Exception:
                log.exception("Web admin dashboard cleanup failed")
            finally:
                self.runner = None

    def _configuration_errors(self) -> list[str]:
        errors = list(self._config_parse_errors)
        required = {
            "WEB_ADMIN_PUBLIC_BASE_URL": self.public_base_url,
            "WEB_ADMIN_SESSION_SECRET": self.session_secret,
            "WEB_ADMIN_ALLOWED_GUILDS": self.allowed_guilds,
            "WEB_ADMIN_GUILD_ADMINS": self.guild_admins,
            "DISCORD_CLIENT_ID": self.client_id,
            "DISCORD_CLIENT_SECRET": self.client_secret,
        }
        errors.extend(f"{name} is required" for name, value in required.items() if not value)

        if self.port < 1 or self.port > 65535:
            errors.append("WEB_ADMIN_PORT must be between 1 and 65535")
        if self.host.casefold() not in LOCAL_HOSTS:
            errors.append("WEB_ADMIN_BIND_HOST must be a loopback host")

        try:
            parsed_url = urlsplit(self.public_base_url)
            public_hostname = parsed_url.hostname
            _ = parsed_url.port
        except ValueError:
            parsed_url = None
            public_hostname = None

        if parsed_url is None or (
            not public_hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
            or parsed_url.path not in {"", "/"}
        ):
            errors.append("WEB_ADMIN_PUBLIC_BASE_URL must contain only a scheme, host, and optional port")
        else:
            local_public_url = public_hostname in LOCAL_HOSTS
            if parsed_url.scheme != "https" and not (parsed_url.scheme == "http" and local_public_url):
                errors.append("WEB_ADMIN_PUBLIC_BASE_URL must use HTTPS except for local testing")
            elif parsed_url.scheme == "https" and not self.cookie_secure:
                errors.append("WEB_ADMIN_COOKIE_SECURE must remain enabled for HTTPS")
            elif parsed_url.scheme == "http" and local_public_url and self.cookie_secure:
                errors.append("WEB_ADMIN_COOKIE_SECURE must be false for local HTTP testing")

        normalized_secret = self.session_secret.strip().casefold()
        if self.session_secret and len(self.session_secret.encode("utf-8")) < MIN_SESSION_SECRET_BYTES:
            errors.append(f"WEB_ADMIN_SESSION_SECRET must be at least {MIN_SESSION_SECRET_BYTES} bytes")
        if normalized_secret in WEAK_SESSION_SECRETS or normalized_secret.startswith("replace-with"):
            errors.append("WEB_ADMIN_SESSION_SECRET must be randomly generated, not a placeholder")

        if self.allowed_guilds and self.guild_admins:
            missing_guilds = self.allowed_guilds - self.guild_admins.keys()
            extra_guilds = self.guild_admins.keys() - self.allowed_guilds
            if missing_guilds:
                errors.append("WEB_ADMIN_GUILD_ADMINS must list every allowed guild")
            if extra_guilds:
                errors.append("WEB_ADMIN_GUILD_ADMINS contains a guild that is not allowed")

        return list(dict.fromkeys(errors))

    async def healthz(self, _: web.Request) -> web.Response:
        ready = self.web_ready and bool(getattr(self.bot, "is_ready", lambda: False)())
        return web.json_response({"ok": ready}, status=200 if ready else 503)

    async def dashboard(self, request: web.Request) -> web.Response:
        session, authorized_guild_ids = self._authorized_session(request)

        if not session or not authorized_guild_ids:
            body = self.renderer.render(
                "login.html",
                title="Rai Admin",
                user_label=None,
                refresh_seconds=None,
            )
            response = self._html_response("Rai Admin", body)
            if request.cookies.get(SESSION_COOKIE):
                self._delete_cookie(response, SESSION_COOKIE)
            return response

        body = self._render_dashboard(
            session,
            authorized_guild_ids,
            refresh_seconds=None if request.query.get("refresh") == "off" else 30,
        )
        return self._html_response("Rai Operations", body)

    def _html_response(self, title: str, body: str, status: int = 200) -> web.Response:
        return web.Response(text=body, status=status, content_type="text/html")
