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
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
ACTIVITY_WINDOW_MINUTES = 60
ACTIVITY_BUCKET_MINUTES = 5
LOG_MODULES = (
    "deletes", "edits", "joins", "leaves", "kicks", "bans",
    "nicknames", "reactions", "voice", "channels",
)
CORE_DB_SECTIONS = (
    "mod_channel", "mod_role", "submod_role", "deletes", "edits",
    "joins", "leaves", "kicks", "bans", "nicknames", "reactions",
    "voice", "channels", "captcha", "antispam", "wordfilter",
)

try:
    CHICAGO_TIMEZONE: Optional[ZoneInfo] = ZoneInfo("America/Chicago")
except ZoneInfoNotFoundError:
    CHICAGO_TIMEZONE = None

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActivitySnapshot:
    bucket_labels: tuple[str, ...]
    bucket_counts: tuple[int, ...]
    total_messages: int
    active_users: int
    active_channels: int
    coverage_minutes: int
    top_channels: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class HealthCheck:
    label: str
    detail: str
    level: str


@dataclass(frozen=True)
class TaskSnapshot:
    name: str
    state: str
    level: str
    next_run: str
    iterations: int


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


def _format_relative_seconds(value: float, *, future: bool = False) -> str:
    seconds = max(0, int(value))
    if seconds < 60:
        text = f"{seconds}s"
    elif seconds < 60 * 60:
        minutes, remaining = divmod(seconds, 60)
        text = f"{minutes}m {remaining}s" if remaining else f"{minutes}m"
    elif seconds < 24 * 60 * 60:
        hours, remainder = divmod(seconds, 60 * 60)
        minutes = remainder // 60
        text = f"{hours}h {minutes}m" if minutes else f"{hours}h"
    else:
        days, remainder = divmod(seconds, 24 * 60 * 60)
        hours = remainder // (60 * 60)
        text = f"{days}d {hours}h" if hours else f"{days}d"
    return f"in {text}" if future else f"{text} ago"


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
        try:
            self.owner_users = _parse_int_set(
                os.getenv("WEB_ADMIN_OWNER_USERS") or os.getenv("OWNER_ID")
            )
        except ValueError:
            self.owner_users = set()
            self._config_parse_errors.append(
                "WEB_ADMIN_OWNER_USERS or OWNER_ID must contain positive integer IDs"
            )
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
            "Rai Operations",
            self._render_dashboard(session, authorized_guild_ids),
            user_label=html.escape(str(session.get("username", session.get("user_id", "unknown")))),
            refresh_seconds=None if request.query.get("refresh") == "off" else 30,
        )
        return self._html_response("Rai Operations", body)

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

    def _is_owner_user(self, user_id: int) -> bool:
        owner_ids = set(self.owner_users)
        bot_owner_id = getattr(self.bot, "owner_id", None)
        if isinstance(bot_owner_id, int):
            owner_ids.add(bot_owner_id)
        configured_owner_ids = getattr(self.bot, "owner_ids", None)
        if configured_owner_ids:
            owner_ids.update(configured_owner_ids)
        return user_id in owner_ids

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
        try:
            user_id = int(session["user_id"])
        except (KeyError, TypeError, ValueError):
            user_id = 0
        if not self._is_owner_user(user_id):
            return self._render_guild_dashboard(guild_ids)

        activity = self._activity_snapshot(guild_ids)
        tasks = self._task_snapshots()
        health_checks = self._database_health_checks(guild_ids)
        latency_ms, latency_level = self._latency_snapshot()
        overall_level, overall_title, overall_detail = self._overall_health(
            tasks,
            health_checks,
            latency_level,
        )

        running_tasks = sum(task.level == "ok" for task in tasks)
        passing_checks = sum(check.level == "ok" for check in health_checks)
        warning_checks = sum(check.level == "warning" for check in health_checks)
        error_checks = sum(check.level == "error" for check in health_checks)
        queue = getattr(self.bot, "message_queue", None)
        queue_length = len(queue) if queue is not None else 0
        queue_maxlen = getattr(queue, "maxlen", None)
        if isinstance(queue_maxlen, int) and queue_maxlen > 0:
            queue_detail = f"{queue_length / queue_maxlen:.0%} of {queue_maxlen:,} rolling capacity"
        else:
            queue_detail = "Rolling capacity unavailable"

        server_now = self._server_time(discord.utils.utcnow())
        timezone_label = server_now.tzname() or "server time"
        metrics = "".join((
            self._metric("Queued messages · 60m", f"{activity.total_messages:,}", "Allowed guilds only"),
            self._metric("Active members · 60m", f"{activity.active_users:,}", "Unique message authors"),
            self._metric("Active channels · 60m", f"{activity.active_channels:,}", "Channels with messages"),
            self._metric(
                "Background tasks",
                f"{running_tasks}/{len(tasks)}",
                "Running without a failed state",
                "ok" if running_tasks == len(tasks) and tasks else "error",
            ),
            self._metric(
                "Live latency",
                f"{latency_ms:.0f} ms" if latency_ms is not None else "Unknown",
                "Event-loop response",
                latency_level,
            ),
            self._metric(
                "Database checks",
                f"{passing_checks}/{len(health_checks)}",
                f"{warning_checks} warning · {error_checks} error",
                "error" if error_checks else "warning" if warning_checks else "ok",
            ),
        ))

        runtime_rows = (
            self._bot_rows(guild_ids)
            + self._message_queue_rows()
            + [("Queue capacity", self._safe_text(queue_detail))]
            + self._guild_rows(guild_ids)
        )
        config_rows = self._config_health_rows(guild_ids)

        return (
            f'<section class="status-band status-{overall_level}">'
            '<div class="status-copy">'
            f'<span class="status-label"><span class="status-dot"></span>{html.escape(overall_title)}</span>'
            f'<h2>{html.escape(overall_detail)}</h2>'
            '</div>'
            '<dl class="status-meta">'
            '<div><dt>Server time</dt><dd>'
            f'<time datetime="{html.escape(server_now.isoformat())}">'
            f'{html.escape(server_now.strftime("%b %d, %I:%M:%S %p"))}</time></dd></div>'
            f'<div><dt>Timezone</dt><dd>{html.escape(timezone_label)}</dd></div>'
            '</dl>'
            '</section>'
            f'<section class="metric-grid" aria-label="Current operational metrics">{metrics}</section>'
            '<section class="chart-grid">'
            f'{self._render_activity_chart(activity)}'
            f'{self._render_channel_chart(activity)}'
            '</section>'
            '<section class="detail-grid">'
            f'{self._render_task_panel(tasks)}'
            f'{self._render_health_panel(health_checks)}'
            '</section>'
            f'{self._card("Runtime details", runtime_rows, "runtime-panel")}'
            '<details class="panel disclosure">'
            '<summary><span>Configuration inventory</span>'
            f'<span class="summary-count">{len(config_rows)} checks</span></summary>'
            f'{self._table(config_rows)}'
            '</details>'
        )

    def _render_guild_dashboard(self, guild_ids: set[int]) -> str:
        activity = self._activity_snapshot(guild_ids)
        visible_guilds = sum(self.bot.get_guild(guild_id) is not None for guild_id in guild_ids)
        status_level = "ok" if visible_guilds == len(guild_ids) else "error"
        status_title = "Guild diagnostics available" if status_level == "ok" else "Guild visibility issue"
        status_detail = (
            f"{visible_guilds}/{len(guild_ids)} authorized guilds visible"
            if guild_ids else "No authorized guilds"
        )
        metrics = "".join((
            self._metric("Queued messages · 60m", f"{activity.total_messages:,}", "Allowed guilds only"),
            self._metric("Active members · 60m", f"{activity.active_users:,}", "Unique message authors"),
            self._metric("Active channels · 60m", f"{activity.active_channels:,}", "Channels with messages"),
        ))
        config_rows = self._config_health_rows(guild_ids)
        return (
            f'<section class="status-band status-{status_level}">'
            '<div class="status-copy">'
            f'<span class="status-label"><span class="status-dot"></span>{html.escape(status_title)}</span>'
            f'<h2>{html.escape(status_detail)}</h2>'
            '</div></section>'
            f'<section class="metric-grid metric-grid-compact" aria-label="Current guild metrics">{metrics}</section>'
            '<section class="chart-grid">'
            f'{self._render_activity_chart(activity)}'
            f'{self._render_channel_chart(activity)}'
            '</section>'
            f'{self._card("Guilds", self._guild_rows(guild_ids), "runtime-panel")}'
            '<details class="panel disclosure">'
            '<summary><span>Configuration inventory</span>'
            f'<span class="summary-count">{len(config_rows)} checks</span></summary>'
            f'{self._table(config_rows)}'
            '</details>'
        )

    @staticmethod
    def _server_time(value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if CHICAGO_TIMEZONE is not None:
            return value.astimezone(CHICAGO_TIMEZONE)
        return value.astimezone()

    def _activity_snapshot(
        self,
        guild_ids: set[int],
        now_utc: Optional[datetime] = None,
    ) -> ActivitySnapshot:
        now_utc = now_utc or discord.utils.utcnow()
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        window_start = now_utc - timedelta(minutes=ACTIVITY_WINDOW_MINUTES)
        bucket_count = ACTIVITY_WINDOW_MINUTES // ACTIVITY_BUCKET_MINUTES
        bucket_counts = [0] * bucket_count
        channel_counts: Counter[tuple[int, int]] = Counter()
        active_users: set[int] = set()
        oldest_available: Optional[datetime] = None
        visible_guild_ids = {guild_id for guild_id in guild_ids if self.bot.get_guild(guild_id)}

        queue = getattr(self.bot, "message_queue", None)
        if queue is not None:
            try:
                oldest_available = queue[0].created_at if queue else None
            except (AttributeError, IndexError, TypeError):
                oldest_available = None
            try:
                messages = reversed(queue)
            except TypeError:
                messages = reversed(list(queue))

            for message in messages:
                try:
                    created_at = message.created_at
                    guild_id = int(message.guild_id)
                    channel_id = int(message.channel_id)
                    author_id = int(message.author_id)
                except (AttributeError, TypeError, ValueError):
                    continue
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at < window_start:
                    break
                if created_at > now_utc + timedelta(minutes=1) or guild_id not in visible_guild_ids:
                    continue

                elapsed = (created_at - window_start).total_seconds()
                bucket_index = min(bucket_count - 1, int(elapsed // (ACTIVITY_BUCKET_MINUTES * 60)))
                bucket_counts[bucket_index] += 1
                channel_counts[(guild_id, channel_id)] += 1
                active_users.add(author_id)

        if oldest_available is not None:
            if oldest_available.tzinfo is None:
                oldest_available = oldest_available.replace(tzinfo=timezone.utc)
            coverage_start = max(window_start, oldest_available)
            coverage_minutes = min(
                ACTIVITY_WINDOW_MINUTES,
                max(0, round((now_utc - coverage_start).total_seconds() / 60)),
            )
        else:
            coverage_minutes = 0

        bucket_labels = []
        for index in range(bucket_count):
            bucket_start = window_start + timedelta(minutes=index * ACTIVITY_BUCKET_MINUTES)
            local_start = self._server_time(bucket_start)
            bucket_labels.append(local_start.strftime("%I:%M").lstrip("0"))

        top_channels = []
        multiple_guilds = len(guild_ids) > 1
        for (guild_id, channel_id), count in channel_counts.most_common(6):
            guild = self.bot.get_guild(guild_id)
            channel = guild.get_channel_or_thread(channel_id) if guild else None
            channel_label = f"#{channel.name}" if channel else f"Channel {channel_id}"
            if multiple_guilds and guild:
                channel_label = f"{guild.name} · {channel_label}"
            top_channels.append((channel_label, count))

        return ActivitySnapshot(
            bucket_labels=tuple(bucket_labels),
            bucket_counts=tuple(bucket_counts),
            total_messages=sum(bucket_counts),
            active_users=len(active_users),
            active_channels=len(channel_counts),
            coverage_minutes=coverage_minutes,
            top_channels=tuple(top_channels),
        )

    def _task_snapshots(self) -> list[TaskSnapshot]:
        def task_name(task: Any) -> str:
            return getattr(getattr(task, "coro", None), "__name__", type(task).__name__)

        snapshots = []
        now_utc = discord.utils.utcnow()
        for task in sorted(getattr(self.bot, "bg_tasks", []), key=task_name):
            name = task_name(task)
            try:
                running = bool(task.is_running())
            except AttributeError:
                running = False
            try:
                failed = bool(task.failed())
            except AttributeError:
                failed = False

            if failed:
                state, level = "Failed", "error"
            elif running:
                state, level = "Running", "ok"
            else:
                state, level = "Stopped", "error"

            next_iteration = getattr(task, "next_iteration", None)
            if isinstance(next_iteration, datetime):
                if next_iteration.tzinfo is None:
                    next_iteration = next_iteration.replace(tzinfo=timezone.utc)
                next_run = _format_relative_seconds((next_iteration - now_utc).total_seconds(), future=True)
            else:
                next_run = "Not scheduled"

            current_loop = getattr(task, "current_loop", 0)
            iterations = int(current_loop) if isinstance(current_loop, int) else 0
            snapshots.append(TaskSnapshot(name, state, level, next_run, iterations))
        return snapshots

    def _database_health_checks(self, guild_ids: set[int]) -> list[HealthCheck]:
        checks = []
        db = getattr(self.bot, "db", None)
        stats = getattr(self.bot, "stats", None)
        queue = getattr(self.bot, "message_queue", None)

        db_loaded = isinstance(db, dict) and bool(db)
        checks.append(HealthCheck(
            "Main configuration database",
            f"{len(db):,} top-level sections loaded" if db_loaded else "Not loaded or empty",
            "ok" if db_loaded else "error",
        ))

        invalid_sections = [
            section for section in CORE_DB_SECTIONS
            if not isinstance(db, dict) or not isinstance(db.get(section), dict)
        ]
        checks.append(HealthCheck(
            "Core database sections",
            "All expected sections have mapping data" if not invalid_sections
            else f"Invalid or missing: {', '.join(invalid_sections)}",
            "ok" if not invalid_sections else "error",
        ))

        valid_stats = isinstance(stats, dict)
        checks.append(HealthCheck(
            "Statistics database",
            f"{len(stats):,} guild entries loaded" if valid_stats else "Not loaded",
            "ok" if valid_stats else "error",
        ))

        checks.append(HealthCheck(
            "In-memory message queue",
            f"{len(queue):,} messages available" if queue is not None else "Not loaded",
            "ok" if queue is not None else "error",
        ))

        sqlite_ready = bool(getattr(self.bot, "database_tables_ready", False))
        checks.append(HealthCheck(
            "SQLite schema",
            "Startup table checks completed" if sqlite_ready else "Startup table checks have not completed",
            "ok" if sqlite_ready else "error",
        ))

        for guild_id in sorted(guild_ids):
            guild = self.bot.get_guild(guild_id)
            guild_label = guild.name if guild else str(guild_id)
            checks.append(HealthCheck(
                f"{guild_label}: guild cache",
                "Guild, channels, and roles are visible" if guild else "Guild is unavailable to the bot",
                "ok" if guild else "error",
            ))

            guild_key = str(guild_id)
            mod_channel = self._guild_config_entry(db, "mod_channel", guild_key)
            mod_role = self._guild_config_entry(db, "mod_role", guild_key)
            submod_role = self._guild_config_entry(db, "submod_role", guild_key)
            mod_role_ids = mod_role.get("id") if isinstance(mod_role, dict) else (
                mod_role if mod_role is None or mod_role is INVALID_CONFIG else INVALID_CONFIG
            )
            submod_role_ids = submod_role.get("id") if isinstance(submod_role, dict) else (
                submod_role if submod_role is None or submod_role is INVALID_CONFIG else INVALID_CONFIG
            )
            reference_statuses = (
                self._channel_status(guild, mod_channel),
                self._role_status(guild, mod_role_ids),
                self._role_status(guild, submod_role_ids),
            )
            reference_levels = [self._reference_level(status) for status in reference_statuses]
            reference_level = self._worst_level(reference_levels)
            resolved_references = sum(level == "ok" for level in reference_levels)
            checks.append(HealthCheck(
                f"{guild_label}: staff references",
                f"{resolved_references}/3 channel and role references resolve",
                reference_level,
            ))

            module_statuses = [
                self._module_status(guild, self._guild_config_entry(db, module, guild_key))
                for module in LOG_MODULES
            ]
            module_levels = [self._reference_level(status) for status in module_statuses]
            checks.append(HealthCheck(
                f"{guild_label}: logging modules",
                f"{sum(level == 'ok' for level in module_levels)}/{len(LOG_MODULES)} valid configurations",
                self._worst_level(module_levels),
            ))

            guild_stats = self._mapping_entry(stats, guild_key)
            if guild_stats is INVALID_CONFIG or (guild_stats is not None and not isinstance(guild_stats, dict)):
                stats_detail, stats_level = "Invalid statistics configuration", "error"
            elif not guild_stats:
                stats_detail, stats_level = "Statistics are not configured", "warning"
            elif guild_stats.get("enable"):
                stats_detail, stats_level = "Collection enabled", "ok"
            else:
                stats_detail, stats_level = "Collection disabled", "ok"
            checks.append(HealthCheck(f"{guild_label}: statistics collection", stats_detail, stats_level))

        return checks

    @staticmethod
    def _reference_level(status: str) -> str:
        normalized = status.casefold()
        if "invalid" in normalized or "unavailable" in normalized:
            return "error"
        if "enabled;" in normalized and "(missing)" in normalized:
            return "error"
        if "(missing)" in normalized:
            return "warning"
        return "ok"

    @staticmethod
    def _worst_level(levels: list[str]) -> str:
        if "error" in levels:
            return "error"
        if "warning" in levels:
            return "warning"
        return "ok"

    def _latency_snapshot(self) -> tuple[Optional[float], str]:
        latency = getattr(self.bot, "live_latency", None)
        if not isinstance(latency, (int, float)):
            latency = getattr(self.bot, "latency", None)
        if not isinstance(latency, (int, float)):
            return None, "warning"
        latency_ms = max(0.0, float(latency) * 1000)
        if latency_ms >= 1500:
            return latency_ms, "error"
        if latency_ms >= 500:
            return latency_ms, "warning"
        return latency_ms, "ok"

    def _overall_health(
        self,
        tasks: list[TaskSnapshot],
        health_checks: list[HealthCheck],
        latency_level: str,
    ) -> tuple[str, str, str]:
        issues = []
        level = "ok"
        if not bool(getattr(self.bot, "is_ready", lambda: False)()):
            issues.append("Discord gateway is not ready")
            level = "error"

        failed_tasks = [task.name for task in tasks if task.level == "error"]
        if not tasks:
            issues.append("background tasks are not loaded")
            level = "error"
        elif failed_tasks:
            issues.append(f"{len(failed_tasks)} background task issue")
            level = "error"

        errored_checks = [check for check in health_checks if check.level == "error"]
        warned_checks = [check for check in health_checks if check.level == "warning"]
        if errored_checks:
            issues.append(f"{len(errored_checks)} database or configuration error")
            level = "error"
        elif warned_checks and level == "ok":
            issues.append(f"{len(warned_checks)} configuration warning")
            level = "warning"

        if latency_level == "error":
            issues.append("latency is critical")
            level = "error"
        elif latency_level == "warning" and level == "ok":
            issues.append("latency is elevated")
            level = "warning"

        if level == "error":
            return level, "Needs attention", " · ".join(issues)
        if level == "warning":
            return level, "Check recommended", " · ".join(issues)

        task_count = len(tasks)
        return (
            level,
            "All systems operational",
            f"{task_count} background tasks running · {len(health_checks)} database checks passing",
        )

    def _metric(self, label: str, value: str, detail: str, level: str = "neutral") -> str:
        return (
            f'<article class="metric metric-{level}">'
            f'<span class="metric-label">{html.escape(label)}</span>'
            f'<strong>{html.escape(value)}</strong>'
            f'<span class="metric-detail">{html.escape(detail)}</span>'
            '</article>'
        )

    def _render_activity_chart(self, activity: ActivitySnapshot) -> str:
        maximum = max(activity.bucket_counts, default=0)
        bars = []
        for label, count in zip(activity.bucket_labels, activity.bucket_counts):
            height = max(6, round(count / maximum * 100)) if count and maximum else 0
            bars.append(
                '<div class="activity-column">'
                f'<span class="bar-value">{count:,}</span>'
                '<div class="bar-track">'
                f'<span class="bar-fill" style="height:{height}%" title="{count:,} messages"></span>'
                '</div>'
                f'<span class="bar-label">{html.escape(label)}</span>'
                '</div>'
            )
        coverage_label = (
            "Last 60 minutes"
            if activity.coverage_minutes >= ACTIVITY_WINDOW_MINUTES
            else f"{activity.coverage_minutes} of 60 minutes available"
        )
        return (
            '<section class="panel activity-panel">'
            f'<div class="section-heading"><div><span class="eyebrow">{coverage_label}</span>'
            '<h2>Queued message activity</h2></div>'
            f'<strong class="section-value">{activity.total_messages / 60:.1f}/min</strong></div>'
            '<div class="chart-scroll"><div class="activity-chart" role="img" '
            'aria-label="Messages observed in each five-minute interval">'
            f'{"".join(bars)}</div></div>'
            '</section>'
        )

    def _render_channel_chart(self, activity: ActivitySnapshot) -> str:
        if not activity.top_channels:
            rows = '<p class="empty-state">No messages observed in the last 60 minutes.</p>'
        else:
            maximum = max(count for _, count in activity.top_channels)
            rendered_rows = []
            for label, count in activity.top_channels:
                width = max(2, round(count / maximum * 100))
                rendered_rows.append(
                    '<div class="channel-row">'
                    f'<span class="channel-label" title="{html.escape(label)}">{html.escape(label)}</span>'
                    '<span class="channel-track">'
                    f'<span class="channel-fill" style="width:{width}%"></span></span>'
                    f'<strong>{count:,}</strong>'
                    '</div>'
                )
            rows = "".join(rendered_rows)
        return (
            '<section class="panel channel-panel">'
            '<div class="section-heading"><div><span class="eyebrow">Last 60 minutes</span>'
            '<h2>Most active channels</h2></div></div>'
            f'<div class="channel-chart">{rows}</div>'
            '</section>'
        )

    def _render_task_panel(self, tasks: list[TaskSnapshot]) -> str:
        if tasks:
            task_rows = "".join(
                '<tr>'
                f'<th>{html.escape(task.name)}</th>'
                f'<td><span class="state-badge state-{task.level}">{html.escape(task.state)}</span></td>'
                f'<td>{html.escape(task.next_run)}</td>'
                f'<td>{task.iterations:,}</td>'
                '</tr>'
                for task in tasks
            )
        else:
            task_rows = '<tr><td colspan="4" class="empty-state">Background tasks are not loaded.</td></tr>'
        return (
            '<section class="panel task-panel">'
            '<div class="section-heading"><div><span class="eyebrow">Process health</span>'
            '<h2>Background tasks</h2></div>'
            f'<strong class="section-value">{sum(task.level == "ok" for task in tasks)}/{len(tasks)}</strong></div>'
            '<div class="table-scroll"><table><thead><tr><th>Task</th><th>State</th>'
            '<th>Next run</th><th>Runs</th></tr></thead>'
            f'<tbody>{task_rows}</tbody></table></div>'
            '</section>'
        )

    def _render_health_panel(self, checks: list[HealthCheck]) -> str:
        rendered_checks = "".join(
            '<li class="health-row">'
            f'<span class="health-indicator health-{check.level}"></span>'
            '<div>'
            f'<strong>{html.escape(check.label)}</strong>'
            f'<span>{html.escape(check.detail)}</span>'
            '</div>'
            f'<span class="state-badge state-{check.level}">{self._level_label(check.level)}</span>'
            '</li>'
            for check in checks
        )
        passing = sum(check.level == "ok" for check in checks)
        return (
            '<section class="panel health-panel">'
            '<div class="section-heading"><div><span class="eyebrow">Data health</span>'
            '<h2>Database &amp; configuration</h2></div>'
            f'<strong class="section-value">{passing}/{len(checks)}</strong></div>'
            f'<ul class="health-list">{rendered_checks}</ul>'
            '</section>'
        )

    @staticmethod
    def _level_label(level: str) -> str:
        return {"ok": "OK", "warning": "Check", "error": "Error"}.get(level, "Info")

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
            ("Maximum length", self._safe_text(getattr(queue, "maxlen", "unknown"))),
            ("Depth", self._safe_text(getattr(queue, "depth", "unknown"))),
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

        for module in LOG_MODULES:
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

    def _table(self, rows: list[tuple[str, str]]) -> str:
        rendered_rows = "".join(
            f'<tr><th scope="row">{html.escape(key)}</th><td>{value}</td></tr>'
            for key, value in rows
        )
        return f'<div class="table-scroll"><table><tbody>{rendered_rows}</tbody></table></div>'

    def _card(self, title: str, rows: list[tuple[str, str]], extra_class: str = "") -> str:
        class_name = f"panel {extra_class}".strip()
        return (
            f'<section class="{class_name}">'
            f'<div class="section-heading"><h2>{html.escape(title)}</h2></div>'
            f'{self._table(rows)}'
            '</section>'
        )

    def _page(
        self,
        title: str,
        body: str,
        user_label: Optional[str] = None,
        refresh_seconds: Optional[int] = None,
    ) -> str:
        if user_label:
            refresh_link = (
                '<a href="/?refresh=off">Pause refresh</a>'
                if refresh_seconds is not None
                else '<a href="/">Resume refresh</a>'
            )
            user_html = f"<span>{user_label}</span>{refresh_link}<a href=\"/logout\">Logout</a>"
        else:
            user_html = ""
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
      --bg: #f1f3f5;
      --panel: #ffffff;
      --text: #17212b;
      --muted: #5f6b76;
      --line: #d9dfe4;
      --accent: #1769aa;
      --accent-soft: #e8f1f8;
      --ok: #176b4d;
      --ok-soft: #e5f4ec;
      --warning: #8a5308;
      --warning-soft: #fff1cf;
      --error: #a12b2b;
      --error-soft: #fbe7e7;
      --neutral-soft: #edf1f4;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #101417;
        --panel: #1a2025;
        --text: #edf2f5;
        --muted: #a6b0b7;
        --line: #343d44;
        --accent: #70b7ea;
        --accent-soft: #17364b;
        --ok: #83d7b1;
        --ok-soft: #16382b;
        --warning: #f0c66f;
        --warning-soft: #453515;
        --error: #f0a0a0;
        --error-soft: #461f22;
        --neutral-soft: #283138;
      }}
    }}
    * {{ box-sizing: border-box; }}
    html {{ min-width: 320px; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-variant-numeric: tabular-nums;
    }}
    a {{ color: var(--accent); }}
    a:focus-visible, summary:focus-visible {{ outline: 3px solid var(--accent); outline-offset: 3px; }}
    .skip-link {{
      position: fixed;
      left: 12px;
      top: 8px;
      z-index: 10;
      transform: translateY(-150%);
      padding: 8px 10px;
      background: var(--panel);
      border: 1px solid var(--line);
    }}
    .skip-link:focus {{ transform: translateY(0); }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 56px;
      padding: 10px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    main {{
      width: min(1320px, calc(100vw - 32px));
      margin: 16px auto 32px;
      display: grid;
      gap: 12px;
    }}
    h1, h2 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 20px; line-height: 1.2; }}
    h2 {{ font-size: 15px; line-height: 1.3; }}
    code {{
      padding: 1px 5px;
      border: 1px solid var(--line);
      border-radius: 4px;
      overflow-wrap: anywhere;
    }}
    .top-actions {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px 14px;
      color: var(--muted);
    }}
    .top-actions a {{ text-underline-offset: 3px; }}
    .button {{
      display: inline-block;
      padding: 8px 12px;
      border: 1px solid var(--accent);
      border-radius: 5px;
      text-decoration: none;
      font-weight: 600;
    }}
    .status-band {{
      min-height: 74px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      padding: 14px 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-left-width: 5px;
      border-radius: 7px;
    }}
    .status-band.status-ok {{ border-left-color: var(--ok); }}
    .status-band.status-warning {{ border-left-color: var(--warning); }}
    .status-band.status-error {{ border-left-color: var(--error); }}
    .status-copy {{ display: grid; gap: 5px; min-width: 0; }}
    .status-copy h2 {{ font-size: 16px; font-weight: 550; overflow-wrap: anywhere; }}
    .status-label {{ display: inline-flex; align-items: center; gap: 7px; font-weight: 700; }}
    .status-dot {{ width: 9px; height: 9px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }}
    .status-ok .status-label {{ color: var(--ok); }}
    .status-warning .status-label {{ color: var(--warning); }}
    .status-error .status-label {{ color: var(--error); }}
    .status-meta {{ display: flex; gap: 24px; margin: 0; flex: 0 0 auto; }}
    .status-meta div {{ display: grid; gap: 2px; }}
    .status-meta dt, .metric-label, .eyebrow {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .status-meta dd {{ margin: 0; font-weight: 650; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }}
    .metric-grid-compact {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .metric {{
      min-height: 92px;
      display: grid;
      align-content: center;
      gap: 4px;
      padding: 12px 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-top: 3px solid var(--accent);
      border-radius: 7px;
      min-width: 0;
    }}
    .metric-ok {{ border-top-color: var(--ok); }}
    .metric-warning {{ border-top-color: var(--warning); }}
    .metric-error {{ border-top-color: var(--error); }}
    .metric strong {{ font-size: 22px; line-height: 1.1; overflow-wrap: anywhere; }}
    .metric-detail {{ color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }}
    .chart-grid {{ display: grid; grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr); gap: 12px; }}
    .detail-grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 14px;
      min-width: 0;
    }}
    .section-heading {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .section-heading > div {{ display: grid; gap: 3px; }}
    .section-value {{ font-size: 18px; line-height: 1.2; }}
    .chart-scroll, .table-scroll {{ overflow-x: auto; }}
    .activity-chart {{
      height: 190px;
      min-width: 620px;
      display: grid;
      grid-template-columns: repeat(12, minmax(34px, 1fr));
      align-items: end;
      gap: 7px;
      padding-top: 6px;
    }}
    .activity-column {{
      height: 100%;
      display: grid;
      grid-template-rows: 20px 1fr 20px;
      gap: 3px;
      text-align: center;
    }}
    .bar-value {{ color: var(--muted); font-size: 11px; align-self: end; }}
    .bar-track {{
      height: 100%;
      display: flex;
      align-items: end;
      background: var(--accent-soft);
      border-radius: 3px 3px 0 0;
    }}
    .bar-fill {{ width: 100%; display: block; background: var(--accent); border-radius: 3px 3px 0 0; }}
    .bar-label {{ color: var(--muted); font-size: 10px; white-space: nowrap; }}
    .channel-chart {{ display: grid; gap: 12px; padding-top: 5px; }}
    .channel-row {{
      display: grid;
      grid-template-columns: minmax(110px, 1fr) minmax(100px, 2fr) 48px;
      gap: 9px;
      align-items: center;
    }}
    .channel-label {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .channel-track {{ height: 10px; background: var(--accent-soft); border-radius: 3px; overflow: hidden; }}
    .channel-fill {{ height: 100%; display: block; background: var(--accent); }}
    .channel-row strong {{ text-align: right; }}
    .state-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 54px;
      padding: 2px 7px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 750;
    }}
    .state-ok {{ color: var(--ok); background: var(--ok-soft); }}
    .state-warning {{ color: var(--warning); background: var(--warning-soft); }}
    .state-error {{ color: var(--error); background: var(--error-soft); }}
    .health-list {{ list-style: none; margin: 0; padding: 0; display: grid; }}
    .health-row {{
      display: grid;
      grid-template-columns: 10px minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
      padding: 9px 0;
      border-top: 1px solid var(--line);
    }}
    .health-row:first-child {{ border-top: 0; }}
    .health-row > div {{ display: grid; gap: 2px; min-width: 0; }}
    .health-row > div > span {{ color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }}
    .health-indicator {{ width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }}
    .health-ok {{ background: var(--ok); }}
    .health-warning {{ background: var(--warning); }}
    .health-error {{ background: var(--error); }}
    .empty-state {{ color: var(--muted); margin: 18px 0; }}
    .disclosure {{ padding: 0; overflow: hidden; }}
    .disclosure summary {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px;
      cursor: pointer;
      font-weight: 700;
    }}
    .disclosure[open] summary {{ border-bottom: 1px solid var(--line); }}
    .disclosure .table-scroll {{ padding: 0 14px 14px; }}
    .summary-count {{ color: var(--muted); font-size: 12px; font-weight: 500; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 540px;
    }}
    th, td {{
      padding: 8px 7px;
      border-top: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }}
    tbody th {{
      width: 34%;
      color: var(--muted);
      font-weight: 600;
    }}
    thead th {{ border-top: 0; color: var(--muted); font-size: 11px; text-transform: uppercase; }}
    .task-panel tbody th {{ width: auto; color: var(--text); }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 1100px) {{
      .metric-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
      .chart-grid, .detail-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 700px) {{
      header {{ align-items: flex-start; padding: 12px 16px; }}
      main {{ width: min(100% - 20px, 1320px); margin-top: 10px; }}
      .status-band {{ align-items: flex-start; flex-direction: column; }}
      .status-meta {{ width: 100%; justify-content: space-between; gap: 12px; }}
      .metric-grid, .metric-grid-compact {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .top-actions span {{ width: 100%; text-align: right; }}
    }}
    @media (max-width: 430px) {{
      .metric-grid, .metric-grid-compact {{ grid-template-columns: 1fr; }}
      .status-meta {{ flex-direction: column; }}
      .channel-row {{ grid-template-columns: minmax(100px, 1fr) minmax(80px, 1.4fr) 42px; }}
    }}
  </style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to diagnostics</a>
  <header>
    <h1>{html.escape(title)}</h1>
    <nav class="top-actions">{user_html}</nav>
  </header>
  <main id="main-content">{body}</main>
</body>
</html>"""

    def _html_response(self, title: str, body: str, status: int = 200) -> web.Response:
        return web.Response(text=body, status=status, content_type="text/html")

    @staticmethod
    def _safe_text(value: Any) -> str:
        return html.escape(str(value))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebAdmin(bot))
