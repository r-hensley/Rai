import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import time
from datetime import timedelta
from typing import Any, Optional
from urllib.parse import urlencode

import aiohttp
import discord
from aiohttp import web
from discord.ext import commands


DEFAULT_ALLOWED_GUILDS = (243838819743432704, 189571157446492161)
SESSION_COOKIE = "rai_web_admin_session"
STATE_COOKIE = "rai_web_admin_oauth_state"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
STATE_MAX_AGE_SECONDS = 10 * 60


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
            continue
        try:
            values.add(int(item))
        except ValueError:
            print(f"WEB_ADMIN config ignored invalid integer value: {item!r}")
    return values


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        print(f"WEB_ADMIN config ignored invalid integer for {name}; using {default}")
        return default


def _format_duration(value: Any) -> str:
    if not value:
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
        self.port = _env_int("WEB_ADMIN_PORT", 8765)
        self.public_base_url = os.getenv("WEB_ADMIN_PUBLIC_BASE_URL", "").rstrip("/")
        self.client_id = os.getenv("DISCORD_CLIENT_ID", "")
        self.client_secret = os.getenv("DISCORD_CLIENT_SECRET", "")
        self.session_secret = os.getenv("WEB_ADMIN_SESSION_SECRET", "")
        self.allowed_users = _parse_int_set(os.getenv("WEB_ADMIN_ALLOWED_USERS"))
        self.allowed_guilds = _parse_int_set(os.getenv("WEB_ADMIN_ALLOWED_GUILDS")) or set(DEFAULT_ALLOWED_GUILDS)
        self.cookie_secure = _env_bool("WEB_ADMIN_COOKIE_SECURE", True)
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

    async def cog_load(self) -> None:
        if not self.enabled:
            print("Web admin dashboard disabled. Set WEB_ADMIN_ENABLED=true to enable it.")
            return

        missing = self._missing_required_config()
        if missing:
            print(f"Web admin dashboard not started; missing required env vars: {', '.join(missing)}")
            return

        app = web.Application()
        app.add_routes([
            web.get("/", self.dashboard),
            web.get("/login", self.login),
            web.get("/oauth/callback", self.oauth_callback),
            web.get("/logout", self.logout),
            web.get("/healthz", self.healthz),
        ])

        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        print(f"Web admin dashboard listening on http://{self.host}:{self.port}")

    async def cog_unload(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    def _missing_required_config(self) -> list[str]:
        required = {
            "WEB_ADMIN_PUBLIC_BASE_URL": self.public_base_url,
            "WEB_ADMIN_SESSION_SECRET": self.session_secret,
            "WEB_ADMIN_ALLOWED_USERS": self.allowed_users,
            "DISCORD_CLIENT_ID": self.client_id,
            "DISCORD_CLIENT_SECRET": self.client_secret,
        }
        return [name for name, value in required.items() if not value]

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_base_url}/oauth/callback"

    async def healthz(self, _: web.Request) -> web.Response:
        body = {
            "ok": True,
            "bot_ready": bool(getattr(self.bot, "is_ready", lambda: False)()),
            "guilds": len(getattr(self.bot, "guilds", [])),
        }
        return web.json_response(body)

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
            return self._html_response("Login Failed", self._page("Login Failed", f"<p>{html.escape(error)}</p>"), 400)

        code = request.query.get("code")
        state = request.query.get("state")
        state_payload = self._read_signed_cookie(request, STATE_COOKIE, max_age=STATE_MAX_AGE_SECONDS)
        if not code or not state or not state_payload or state_payload.get("state") != state:
            return self._html_response("Login Failed", self._page("Login Failed", "<p>OAuth state check failed.</p>"), 400)

        try:
            user = await self._fetch_discord_user(code)
        except (aiohttp.ClientError, KeyError, TypeError, ValueError) as exc:
            print(f"Web admin OAuth request failed: {type(exc).__name__}")
            return self._html_response("Login Failed", self._page("Login Failed", "<p>Discord OAuth request failed.</p>"), 502)

        try:
            user_id = int(user["id"])
        except (KeyError, TypeError, ValueError):
            return self._html_response("Login Failed", self._page("Login Failed", "<p>Discord did not return a valid user.</p>"), 502)

        if user_id not in self.allowed_users:
            return self._html_response("Access Denied", self._page("Access Denied", "<p>Your Discord account is not allowlisted.</p>"), 403)

        session = {
            "user_id": user_id,
            "username": user.get("global_name") or user.get("username") or str(user_id),
            "iat": int(time.time()),
        }
        response = web.HTTPFound("/")
        response.del_cookie(STATE_COOKIE, path="/")
        self._set_signed_cookie(response, SESSION_COOKIE, session, max_age=SESSION_MAX_AGE_SECONDS)
        return response

    async def logout(self, _: web.Request) -> web.Response:
        response = web.HTTPFound("/")
        response.del_cookie(SESSION_COOKIE, path="/")
        response.del_cookie(STATE_COOKIE, path="/")
        return response

    async def dashboard(self, request: web.Request) -> web.Response:
        session = self._read_signed_cookie(request, SESSION_COOKIE, max_age=SESSION_MAX_AGE_SECONDS)
        if not session:
            body = self._page(
                "Rai Admin",
                "<p>This dashboard is read-only and requires Discord login.</p>"
                '<p><a class="button" href="/login">Log in with Discord</a></p>',
            )
            return self._html_response("Rai Admin", body)

        body = self._page(
            "Rai Admin",
            self._render_dashboard(session),
            user_label=html.escape(str(session.get("username", session.get("user_id", "unknown")))),
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

        async with aiohttp.ClientSession() as session:
            async with session.post("https://discord.com/api/oauth2/token", data=token_data, headers=headers) as response:
                response.raise_for_status()
                token_payload = await response.json()

            access_token = token_payload["access_token"]
            user_headers = {"Authorization": f"Bearer {access_token}"}
            async with session.get("https://discord.com/api/users/@me", headers=user_headers) as response:
                response.raise_for_status()
                return await response.json()

    def _set_signed_cookie(self, response: web.StreamResponse, name: str, payload: dict[str, Any], max_age: int) -> None:
        response.set_cookie(
            name,
            self._sign_payload(payload),
            max_age=max_age,
            path="/",
            httponly=True,
            secure=self.cookie_secure,
            samesite="Lax",
        )

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
        except (json.JSONDecodeError, ValueError):
            return None

        issued_at = payload.get("iat")
        if not isinstance(issued_at, int) or time.time() - issued_at > max_age:
            return None

        return payload

    def _render_dashboard(self, session: dict[str, Any]) -> str:
        cards = [
            self._card("Bot", self._bot_rows()),
            self._card("Background Tasks", self._background_task_rows()),
            self._card("Message Queue", self._message_queue_rows()),
            self._card("Guilds", self._guild_rows()),
            self._card("Config Health", self._config_health_rows()),
        ]
        user_id = html.escape(str(session.get("user_id", "unknown")))
        return (
            f"<p class=\"muted\">Logged in as Discord user <code>{user_id}</code>. "
            "This page is read-only and refreshes every 30 seconds.</p>"
            + "".join(cards)
        )

    def _bot_rows(self) -> list[tuple[str, str]]:
        user = getattr(self.bot, "user", None)
        started = getattr(self.bot, "t_start", None)
        now = discord.utils.utcnow().replace(tzinfo=None)
        uptime = now - started if started else None
        live_latency = getattr(self.bot, "live_latency", None)
        return [
            ("Bot user", self._safe_text(f"{user} ({user.id})") if user else "not ready"),
            ("Ready", self._safe_text(str(getattr(self.bot, "is_ready", lambda: False)()))),
            ("Uptime", self._safe_text(_format_duration(uptime))),
            ("Guild count", self._safe_text(str(len(getattr(self.bot, "guilds", []))))),
            ("Loaded cogs", self._safe_text(str(len(getattr(self.bot, "cogs", {}))))),
            ("Gateway latency", self._safe_text(f"{getattr(self.bot, 'latency', 0) * 1000:.0f} ms")),
            ("Live latency", self._safe_text(f"{live_latency * 1000:.0f} ms") if live_latency is not None else "unknown"),
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

    def _guild_rows(self) -> list[tuple[str, str]]:
        rows = []
        for guild_id in sorted(self.allowed_guilds):
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

    def _config_health_rows(self) -> list[tuple[str, str]]:
        rows = []
        for guild_id in sorted(self.allowed_guilds):
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

        rows.append((f"{label}: mod channel", self._safe_text(self._channel_status(guild, db.get("mod_channel", {}).get(guild_id)))))
        rows.append((f"{label}: mod role", self._safe_text(self._role_status(guild, db.get("mod_role", {}).get(guild_id, {}).get("id")))))
        rows.append((f"{label}: submod role", self._safe_text(self._role_status(guild, db.get("submod_role", {}).get(guild_id, {}).get("id")))))

        for module in ("deletes", "edits", "joins", "leaves", "kicks", "bans", "nicknames", "reactions", "voice", "channels"):
            config = db.get(module, {}).get(guild_id)
            rows.append((f"{label}: {module}", self._module_status(guild, config)))

        captcha = db.get("captcha", {}).get(guild_id)
        if captcha:
            channel_status = self._channel_status(guild, captcha.get("channel"))
            role_status = self._role_status(guild, captcha.get("role"))
            rows.append((f"{label}: captcha", self._safe_text(f"{_format_bool(captcha.get('enable'))}; channel {channel_status}; role {role_status}")))
        else:
            rows.append((f"{label}: captcha", "not configured"))

        antispam = db.get("antispam", {}).get(guild_id)
        if antispam:
            rows.append((
                f"{label}: antispam",
                self._safe_text(
                    f"{_format_bool(antispam.get('enable'))}; "
                    f"action {antispam.get('action') or 'unset'}; "
                    f"ignored channels {len(antispam.get('ignored', []))}"
                ),
            ))
        else:
            rows.append((f"{label}: antispam", "not configured"))

        wordfilter = db.get("wordfilter", {}).get(guild_id, {})
        rows.append((f"{label}: wordfilter", self._safe_text(f"{len(wordfilter)} entries")))

        guild_stats = stats.get(guild_id)
        if guild_stats:
            rows.append((
                f"{label}: stats",
                self._safe_text(f"{_format_bool(guild_stats.get('enable'))}; hidden channels {len(guild_stats.get('hidden', []))}"),
            ))
        else:
            rows.append((f"{label}: stats", "not configured"))

        if guild_id == "243838819743432704":
            hardcore = db.get("hardcore", {}).get(guild_id, {})
            rows.append((
                f"{label}: hardcore",
                self._safe_text(
                    f"users {len(hardcore.get('users', {}))}; ignored channels {len(hardcore.get('ignore', []))}"
                ),
            ))

        if guild_id == "189571157446492161":
            uhc = db.get("ultraHardcore", {})
            users = uhc.get("users", {})
            active = sum(1 for entry in users.values() if isinstance(entry, list) and entry and entry[0])
            rows.append((
                f"{label}: ultra hardcore",
                self._safe_text(f"active users {active}; ignored channels {len(uhc.get('ignore', []))}"),
            ))

        return rows

    def _module_status(self, guild: Optional[discord.Guild], config: Optional[dict[str, Any]]) -> str:
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

    def _page(self, title: str, body: str, user_label: Optional[str] = None) -> str:
        user_html = f"<span>{user_label}</span><a href=\"/logout\">Logout</a>" if user_label else ""
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
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
