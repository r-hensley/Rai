import base64
import binascii
import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import time
from datetime import timedelta
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlencode, urlsplit

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands


SESSION_COOKIE = "rai_web_admin_session"
STATE_COOKIE = "rai_web_admin_oauth_state"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
STATE_MAX_AGE_SECONDS = 10 * 60
MIN_SESSION_SECRET_BYTES = 32
DISCORD_API_BASE_URL = "https://discord.com/api/v10"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
INVALID_CONFIG = object()
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    ),
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
WEAK_SESSION_SECRETS = {
    "changeme",
    "change-me",
    "password",
    "secret",
    "test",
}

log = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on"}


def _parse_int_set(value: Optional[str]) -> set[int]:
    if not value:
        return set()

    values: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            raise ValueError("empty integer")
        try:
            parsed = int(item)
        except ValueError as exc:
            raise ValueError("non-integer value") from exc
        if parsed <= 0:
            raise ValueError("IDs must be positive")
        values.add(parsed)
    return values


def _parse_guild_admins(value: Optional[str]) -> dict[int, set[int]]:
    if not value:
        return {}

    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("must be a JSON object")

    guild_admins: dict[int, set[int]] = {}
    for guild_id_value, user_id_values in payload.items():
        try:
            guild_id = int(guild_id_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("guild IDs must be integers") from exc
        if guild_id <= 0 or isinstance(guild_id_value, bool):
            raise ValueError("guild IDs must be positive integers")
        if not isinstance(user_id_values, list) or not user_id_values:
            raise ValueError("each guild must have a non-empty JSON list of administrators")

        user_ids: set[int] = set()
        for user_id_value in user_id_values:
            try:
                user_id = int(user_id_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("user IDs must be integers") from exc
            if user_id <= 0 or isinstance(user_id_value, bool):
                raise ValueError("user IDs must be positive integers")
            user_ids.add(user_id)
        guild_admins[guild_id] = user_ids

    return guild_admins


def _apply_security_headers(response: web.StreamResponse) -> web.StreamResponse:
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


@web.middleware
async def _security_headers_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    try:
        response = await handler(request)
    except web.HTTPException as response:
        pass
    except Exception:
        log.exception("Unhandled web admin request error")
        response = web.Response(text="Internal server error.", status=500, content_type="text/plain")
    return _apply_security_headers(response)


def _format_duration(value: Any) -> str:
    if value is None:
        return "unknown"
    try:
        return str(timedelta(seconds=int(value.total_seconds())))
    except AttributeError:
        return str(value)


def _format_bool(value: Any) -> str:
    return "enabled" if value else "disabled"


class WebAdmin(commands.Cog):
    """Read-only web dashboard for Rai diagnostics."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.enabled = _env_bool("WEB_ADMIN_ENABLED", False)
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
            self.allowed_guilds = _parse_int_set(os.getenv("WEB_ADMIN_ALLOWED_GUILDS"))
        except ValueError:
            self.allowed_guilds = set()
            self._config_parse_errors.append(
                "WEB_ADMIN_ALLOWED_GUILDS must be a comma-separated list of positive integer IDs"
            )
        try:
            self.guild_admins = _parse_guild_admins(os.getenv("WEB_ADMIN_GUILD_ADMINS"))
        except ValueError as exc:
            self.guild_admins = {}
            self._config_parse_errors.append(f"WEB_ADMIN_GUILD_ADMINS {exc}")
        self.cookie_secure = _env_bool("WEB_ADMIN_COOKIE_SECURE", True)
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.web_ready = False

    async def cog_load(self) -> None:
        if not self.enabled:
            print("Web admin dashboard disabled. Set WEB_ADMIN_ENABLED=true to enable it.")
            return

        config_errors = self._configuration_errors()
        if config_errors:
            log.error("Web admin dashboard not started: %s", "; ".join(config_errors))
            return

        try:
            app = web.Application(middlewares=[_security_headers_middleware])
            app.add_routes([
                web.get("/", self.dashboard),
                web.get("/login", self.login),
                web.get("/oauth/callback", self.oauth_callback),
                web.get("/logout", self.logout),
                web.get("/healthz", self.healthz),
            ])

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

    async def cog_unload(self) -> None:
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

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_base_url}/oauth/callback"

    async def healthz(self, _: web.Request) -> web.Response:
        ready = self.web_ready and bool(getattr(self.bot, "is_ready", lambda: False)())
        return web.json_response({"ok": ready}, status=200 if ready else 503)

    async def login(self, _: web.Request) -> web.Response:
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "identify",
            "state": state,
        }
        response = web.HTTPFound(f"https://discord.com/oauth2/authorize?{urlencode(params)}")
        self._set_signed_cookie(
            response,
            STATE_COOKIE,
            {"state": state, "iat": int(time.time())},
            max_age=STATE_MAX_AGE_SECONDS,
        )
        return response

    async def oauth_callback(self, request: web.Request) -> web.Response:
        error = request.query.get("error")
        if error:
            log.info("Web admin OAuth login did not complete")
            return self._oauth_error("Login Failed", "Discord did not complete the login.", 400)

        code = request.query.get("code")
        state = request.query.get("state")
        state_payload = self._read_signed_cookie(request, STATE_COOKIE, max_age=STATE_MAX_AGE_SECONDS)
        if not code or not state or not state_payload or state_payload.get("state") != state:
            log.warning("Web admin OAuth state validation failed")
            return self._oauth_error("Login Failed", "OAuth state check failed.", 400)

        try:
            user = await self._fetch_discord_user(code)
        except (aiohttp.ClientError, KeyError, TimeoutError, TypeError, ValueError) as exc:
            log.warning("Web admin OAuth request failed: %s", type(exc).__name__)
            return self._oauth_error("Login Failed", "Discord OAuth request failed.", 502)

        try:
            user_id = int(user["id"])
        except (KeyError, TypeError, ValueError):
            return self._oauth_error("Login Failed", "Discord did not return a valid user.", 502)

        if not self._authorized_guild_ids(user_id):
            log.warning("Web admin login denied for Discord user %s", user_id)
            return self._oauth_error("Access Denied", "Your Discord account is not allowlisted.", 403)

        session = {
            "user_id": user_id,
            "username": user.get("global_name") or user.get("username") or str(user_id),
            "iat": int(time.time()),
        }
        response = web.HTTPFound("/")
        self._delete_cookie(response, STATE_COOKIE)
        self._set_signed_cookie(response, SESSION_COOKIE, session, max_age=SESSION_MAX_AGE_SECONDS)
        log.info("Web admin login accepted for Discord user %s", user_id)
        return response

    async def logout(self, _: web.Request) -> web.Response:
        response = web.HTTPFound("/")
        self._delete_cookie(response, SESSION_COOKIE)
        self._delete_cookie(response, STATE_COOKIE)
        return response

    async def dashboard(self, request: web.Request) -> web.Response:
        session = self._read_signed_cookie(request, SESSION_COOKIE, max_age=SESSION_MAX_AGE_SECONDS)
        authorized_guild_ids: set[int] = set()
        if session:
            try:
                authorized_guild_ids = self._authorized_guild_ids(int(session["user_id"]))
            except (KeyError, TypeError, ValueError):
                session = None

        if not session or not authorized_guild_ids:
            body = self._page(
                "Rai Admin",
                "<p>This dashboard is read-only and requires Discord login.</p>"
                '<p><a class="button" href="/login">Log in with Discord</a></p>',
            )
            response = self._html_response("Rai Admin", body)
            if request.cookies.get(SESSION_COOKIE):
                self._delete_cookie(response, SESSION_COOKIE)
            return response

        body = self._page(
            "Rai Admin",
            self._render_dashboard(session, authorized_guild_ids),
            user_label=html.escape(str(session.get("username", session.get("user_id", "unknown")))),
            refresh_seconds=30,
        )
        return self._html_response("Rai Admin", body)

    async def _fetch_discord_user(self, code: str) -> dict[str, Any]:
        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{DISCORD_API_BASE_URL}/oauth2/token",
                data=token_data,
                headers=headers,
            ) as response:
                response.raise_for_status()
                token_payload = await response.json()

            access_token = token_payload["access_token"]
            user_headers = {"Authorization": f"Bearer {access_token}"}
            async with session.get(f"{DISCORD_API_BASE_URL}/users/@me", headers=user_headers) as response:
                response.raise_for_status()
                return await response.json()

    def _set_signed_cookie(
        self,
        response: web.StreamResponse,
        name: str,
        payload: dict[str, Any],
        max_age: int,
    ) -> None:
        response.set_cookie(
            name,
            self._sign_payload(payload),
            max_age=max_age,
            path="/",
            httponly=True,
            secure=self.cookie_secure,
            samesite="Lax",
        )

    def _delete_cookie(self, response: web.StreamResponse, name: str) -> None:
        response.del_cookie(
            name,
            path="/",
            httponly=True,
            secure=self.cookie_secure,
            samesite="Lax",
        )

    def _oauth_error(self, title: str, message: str, status: int) -> web.Response:
        body = self._page(title, f"<p>{html.escape(message)}</p>")
        response = self._html_response(title, body, status)
        self._delete_cookie(response, STATE_COOKIE)
        return response

    def _authorized_guild_ids(self, user_id: int) -> set[int]:
        return {
            guild_id
            for guild_id in self.allowed_guilds
            if user_id in self.guild_admins.get(guild_id, set())
        }

    def _sign_payload(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        signature = hmac.new(self.session_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return f"{encoded}.{encoded_signature}"

    def _read_signed_cookie(self, request: web.Request, name: str, max_age: int) -> Optional[dict[str, Any]]:
        value = request.cookies.get(name)
        if not value:
            return None

        try:
            encoded, encoded_signature = value.split(".", 1)
        except ValueError:
            return None

        expected = hmac.new(self.session_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        expected_signature = base64.urlsafe_b64encode(expected).decode("ascii").rstrip("=")
        if not hmac.compare_digest(encoded_signature, expected_signature):
            return None

        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            payload = json.loads(raw)
        except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return None

        if not isinstance(payload, dict):
            return None

        issued_at = payload.get("iat")
        age = time.time() - issued_at if isinstance(issued_at, int) else None
        if age is None or age < -60 or age > max_age:
            return None

        return payload

    def _render_dashboard(self, session: dict[str, Any], guild_ids: set[int]) -> str:
        cards = [
            self._card("Bot", self._bot_rows(guild_ids)),
            self._card("Background Tasks", self._background_task_rows()),
            self._card("Message Queue", self._message_queue_rows()),
            self._card("Guilds", self._guild_rows(guild_ids)),
            self._card("Config Health", self._config_health_rows(guild_ids)),
        ]
        user_id = html.escape(str(session.get("user_id", "unknown")))
        return (
            f"<p class=\"muted\">Logged in as Discord user <code>{user_id}</code>. "
            "This page is read-only and refreshes every 30 seconds.</p>"
            + "".join(cards)
        )

    def _bot_rows(self, guild_ids: set[int]) -> list[tuple[str, str]]:
        user = getattr(self.bot, "user", None)
        started = getattr(self.bot, "t_start_monotonic", None)
        uptime = None
        if isinstance(started, (int, float)):
            uptime = timedelta(seconds=max(0, time.monotonic() - started))
        live_latency = getattr(self.bot, "live_latency", None)
        return [
            ("Bot user", self._safe_text(f"{user} ({user.id})") if user else "not ready"),
            ("Ready", self._safe_text(str(getattr(self.bot, "is_ready", lambda: False)()))),
            ("Uptime", self._safe_text(_format_duration(uptime))),
            ("Dashboard guild count", self._safe_text(str(len(guild_ids)))),
            ("Loaded cogs", self._safe_text(str(len(getattr(self.bot, "cogs", {}))))),
            ("Gateway latency", self._safe_text(f"{getattr(self.bot, 'latency', 0) * 1000:.0f} ms")),
            (
                "Live latency",
                self._safe_text(f"{live_latency * 1000:.0f} ms") if live_latency is not None else "unknown",
            ),
        ]

    def _background_task_rows(self) -> list[tuple[str, str]]:
        tasks = sorted(getattr(self.bot, "bg_tasks", []), key=lambda task: task.coro.__name__)
        if not tasks:
            return [("Background tasks", "not loaded")]

        rows = []
        for task in tasks:
            status = "running" if task.is_running() else "stopped"
            try:
                if task.failed():
                    status = "failed"
            except AttributeError:
                pass
            rows.append((task.coro.__name__, self._safe_text(status)))
        return rows

    def _message_queue_rows(self) -> list[tuple[str, str]]:
        queue = getattr(self.bot, "message_queue", None)
        if queue is None:
            return [("Message queue", "not loaded")]

        return [
            ("Length", self._safe_text(str(len(queue)))),
            ("Depth", self._safe_text(getattr(queue, "depth", "unknown"))),
            ("Memory", self._safe_text(getattr(queue, "memory_usage", "unknown"))),
        ]

    def _guild_rows(self, guild_ids: set[int]) -> list[tuple[str, str]]:
        rows = []
        for guild_id in sorted(guild_ids):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                rows.append((str(guild_id), "not visible to bot"))
                continue
            rows.append((
                f"{guild.name} ({guild.id})",
                self._safe_text(
                    f"{guild.member_count} members, "
                    f"{len(guild.text_channels)} text channels, "
                    f"{len(guild.voice_channels)} voice channels"
                ),
            ))
        return rows or [("Guilds", "none configured")]

    def _config_health_rows(self, guild_ids: set[int]) -> list[tuple[str, str]]:
        rows = []
        for guild_id in sorted(guild_ids):
            guild = self.bot.get_guild(guild_id)
            label = guild.name if guild else str(guild_id)
            rows.extend(self._guild_config_health_rows(str(guild_id), label, guild))
        return rows or [("Config", "none")]

    def _guild_config_health_rows(
        self,
        guild_id: str,
        label: str,
        guild: Optional[discord.Guild],
    ) -> list[tuple[str, str]]:
        db = getattr(self.bot, "db", {})
        stats = getattr(self.bot, "stats", {})
        rows = []

        mod_channel = self._guild_config_entry(db, "mod_channel", guild_id)
        mod_role = self._guild_config_entry(db, "mod_role", guild_id)
        submod_role = self._guild_config_entry(db, "submod_role", guild_id)
        mod_role_ids = mod_role.get("id") if isinstance(mod_role, dict) else (
            mod_role if mod_role is None or mod_role is INVALID_CONFIG else INVALID_CONFIG
        )
        submod_role_ids = submod_role.get("id") if isinstance(submod_role, dict) else (
            submod_role if submod_role is None or submod_role is INVALID_CONFIG else INVALID_CONFIG
        )
        rows.append((f"{label}: mod channel", self._safe_text(self._channel_status(guild, mod_channel))))
        rows.append((f"{label}: mod role", self._safe_text(self._role_status(guild, mod_role_ids))))
        rows.append((f"{label}: submod role", self._safe_text(self._role_status(guild, submod_role_ids))))

        modules = (
            "deletes", "edits", "joins", "leaves", "kicks", "bans",
            "nicknames", "reactions", "voice", "channels",
        )
        for module in modules:
            config = self._guild_config_entry(db, module, guild_id)
            rows.append((f"{label}: {module}", self._module_status(guild, config)))

        captcha = self._guild_config_entry(db, "captcha", guild_id)
        if captcha is INVALID_CONFIG or (captcha is not None and not isinstance(captcha, dict)):
            rows.append((f"{label}: captcha", "invalid config"))
        elif captcha:
            channel_status = self._channel_status(guild, captcha.get("channel"))
            role_status = self._role_status(guild, captcha.get("role"))
            rows.append((
                f"{label}: captcha",
                self._safe_text(
                    f"{_format_bool(captcha.get('enable'))}; "
                    f"channel {channel_status}; role {role_status}"
                ),
            ))
        else:
            rows.append((f"{label}: captcha", "not configured"))

        antispam = self._guild_config_entry(db, "antispam", guild_id)
        if antispam is INVALID_CONFIG or (antispam is not None and not isinstance(antispam, dict)):
            rows.append((f"{label}: antispam", "invalid config"))
        elif antispam:
            rows.append((
                f"{label}: antispam",
                self._safe_text(
                    f"{_format_bool(antispam.get('enable'))}; "
                    f"action {antispam.get('action') or 'unset'}; "
                    f"ignored channels {self._item_count(antispam.get('ignored', []))}"
                ),
            ))
        else:
            rows.append((f"{label}: antispam", "not configured"))

        wordfilter = self._guild_config_entry(db, "wordfilter", guild_id)
        if wordfilter is INVALID_CONFIG or (wordfilter is not None and not isinstance(wordfilter, dict)):
            rows.append((f"{label}: wordfilter", "invalid config"))
        else:
            rows.append((f"{label}: wordfilter", self._safe_text(f"{self._item_count(wordfilter or {})} entries")))

        guild_stats = self._mapping_entry(stats, guild_id)
        if guild_stats is INVALID_CONFIG or (guild_stats is not None and not isinstance(guild_stats, dict)):
            rows.append((f"{label}: stats", "invalid config"))
        elif guild_stats:
            rows.append((
                f"{label}: stats",
                self._safe_text(
                    f"{_format_bool(guild_stats.get('enable'))}; "
                    f"hidden channels {self._item_count(guild_stats.get('hidden', []))}"
                ),
            ))
        else:
            rows.append((f"{label}: stats", "not configured"))

        if guild_id == "243838819743432704":
            hardcore = self._guild_config_entry(db, "hardcore", guild_id)
            if hardcore is INVALID_CONFIG or (hardcore is not None and not isinstance(hardcore, dict)):
                rows.append((f"{label}: hardcore", "invalid config"))
            else:
                hardcore = hardcore or {}
                rows.append((
                    f"{label}: hardcore",
                    self._safe_text(
                        f"users {self._item_count(hardcore.get('users', {}))}; "
                        f"ignored channels {self._item_count(hardcore.get('ignore', []))}"
                    ),
                ))

        if guild_id == "189571157446492161":
            uhc = self._mapping_entry(db, "ultraHardcore")
            if uhc is INVALID_CONFIG or (uhc is not None and not isinstance(uhc, dict)):
                rows.append((f"{label}: ultra hardcore", "invalid config"))
            else:
                uhc = uhc or {}
                users = uhc.get("users", {})
                active = (
                    sum(1 for entry in users.values() if isinstance(entry, list) and entry and entry[0])
                    if isinstance(users, dict)
                    else "invalid"
                )
                rows.append((
                    f"{label}: ultra hardcore",
                    self._safe_text(
                        f"active users {active}; ignored channels {self._item_count(uhc.get('ignore', []))}"
                    ),
                ))

        return rows

    @staticmethod
    def _mapping_entry(mapping: Any, key: str) -> Any:
        if not isinstance(mapping, dict):
            return INVALID_CONFIG
        return mapping.get(key)

    @classmethod
    def _guild_config_entry(cls, mapping: Any, section: str, guild_id: str) -> Any:
        section_mapping = cls._mapping_entry(mapping, section)
        if section_mapping is None:
            return None
        if not isinstance(section_mapping, dict):
            return INVALID_CONFIG
        return section_mapping.get(guild_id)

    @staticmethod
    def _item_count(value: Any) -> Any:
        try:
            return len(value)
        except TypeError:
            return "invalid"

    def _module_status(self, guild: Optional[discord.Guild], config: Any) -> str:
        if config is INVALID_CONFIG or (config is not None and not isinstance(config, dict)):
            return "invalid config"
        if not config:
            return "not configured"
        enabled = config.get("enable")
        channel = config.get("channel")
        if enabled:
            return self._safe_text(f"enabled; channel {self._channel_status(guild, channel)}")
        if channel:
            return self._safe_text(f"disabled; channel {self._channel_status(guild, channel)}")
        return "disabled; no channel"

    def _channel_status(self, guild: Optional[discord.Guild], channel_id: Any) -> str:
        if channel_id is INVALID_CONFIG:
            return "invalid config"
        if not channel_id:
            return "not configured"
        try:
            channel_id = int(channel_id)
        except (TypeError, ValueError):
            return "invalid id"
        if not guild:
            return f"{channel_id} (guild unavailable)"
        channel = guild.get_channel_or_thread(channel_id)
        if not channel:
            return f"{channel_id} (missing)"
        return f"#{channel.name} ({channel_id})"

    def _role_status(self, guild: Optional[discord.Guild], role_payload: Any) -> str:
        if role_payload is INVALID_CONFIG:
            return "invalid config"
        if not role_payload:
            return "not configured"
        role_ids = role_payload if isinstance(role_payload, list) else [role_payload]
        statuses = []
        for role_id in role_ids:
            try:
                role_id = int(role_id)
            except (TypeError, ValueError):
                statuses.append("invalid id")
                continue
            if not guild:
                statuses.append(f"{role_id} (guild unavailable)")
                continue
            role = guild.get_role(role_id)
            statuses.append(f"@{role.name} ({role_id})" if role else f"{role_id} (missing)")
        return "; ".join(statuses)

    def _card(self, title: str, rows: list[tuple[str, str]]) -> str:
        rendered_rows = "".join(
            f"<tr><th>{html.escape(key)}</th><td>{value}</td></tr>"
            for key, value in rows
        )
        return f"<section class=\"card\"><h2>{html.escape(title)}</h2><table>{rendered_rows}</table></section>"

    def _page(
        self,
        title: str,
        body: str,
        user_label: Optional[str] = None,
        refresh_seconds: Optional[int] = None,
    ) -> str:
        user_html = f"<span>{user_label}</span><a href=\"/logout\">Logout</a>" if user_label else ""
        refresh_html = (
            f'<meta http-equiv="refresh" content="{int(refresh_seconds)}">'
            if refresh_seconds is not None
            else ""
        )
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh_html}
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f5f7f8;
      --panel: #ffffff;
      --text: #172026;
      --muted: #5b6770;
      --line: #d8e0e5;
      --accent: #0f766e;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #111417;
        --panel: #1b2025;
        --text: #eef3f5;
        --muted: #a8b3ba;
        --line: #303940;
        --accent: #2dd4bf;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    main {{
      width: min(1120px, calc(100vw - 32px));
      margin: 24px auto;
      display: grid;
      gap: 16px;
    }}
    h1, h2 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 22px; }}
    h2 {{ font-size: 16px; margin-bottom: 12px; }}
    a {{ color: var(--accent); }}
    code {{
      padding: 1px 5px;
      border: 1px solid var(--line);
      border-radius: 4px;
    }}
    .top-actions {{
      display: flex;
      align-items: center;
      gap: 12px;
      color: var(--muted);
    }}
    .button {{
      display: inline-block;
      padding: 8px 12px;
      border: 1px solid var(--accent);
      border-radius: 6px;
      text-decoration: none;
      font-weight: 600;
    }}
    .muted {{ color: var(--muted); }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 8px 6px;
      border-top: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      width: 32%;
      color: var(--muted);
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <nav class="top-actions">{user_html}</nav>
  </header>
  <main>{body}</main>
</body>
</html>"""

    def _html_response(self, title: str, body: str, status: int = 200) -> web.Response:
        return web.Response(text=body, status=status, content_type="text/html")

    @staticmethod
    def _safe_text(value: Any) -> str:
        return html.escape(str(value))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebAdmin(bot))
