import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any, Optional
from urllib.parse import urlencode

import aiohttp
from aiohttp import web

from .config import (
    DISCORD_API_BASE_URL,
    GUILD_ACCESS_ROLE_IDS,
    GUILD_CONFIG_EDITOR_ROLE_IDS,
)
from .security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    STATE_COOKIE,
    STATE_MAX_AGE_SECONDS,
)


log = logging.getLogger(__name__)


class AuthMixin:
    bot: Any
    public_base_url: str
    client_id: str
    client_secret: str
    session_secret: str
    cookie_secure: bool
    allowed_guilds: set[int]
    guild_admins: dict[int, set[int]]
    owner_users: set[int]
    renderer: Any

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_base_url}/oauth/callback"

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
        body = self.renderer.render(
            "error.html",
            title=title,
            message=message,
            user_label=None,
            refresh_seconds=None,
        )
        response = self._html_response(title, body, status)
        self._delete_cookie(response, STATE_COOKIE)
        return response

    def _authorized_guild_ids(self, user_id: int) -> set[int]:
        return {
            guild_id
            for guild_id in self.allowed_guilds
            if (
                user_id in self.guild_admins.get(guild_id, set())
                or self._has_guild_access_role(guild_id, user_id)
            )
        }

    def _has_guild_access_role(self, guild_id: int, user_id: int) -> bool:
        access_role_ids = GUILD_ACCESS_ROLE_IDS.get(guild_id)
        return self._member_has_any_role(guild_id, user_id, access_role_ids)

    def _can_manage_guild(self, guild_id: int, user_id: int) -> bool:
        if self._is_owner_user(user_id):
            return True
        editor_role_ids = GUILD_CONFIG_EDITOR_ROLE_IDS.get(guild_id)
        return self._member_has_any_role(guild_id, user_id, editor_role_ids)

    def _member_has_any_role(
        self,
        guild_id: int,
        user_id: int,
        role_ids: Optional[set[int] | frozenset[int]],
    ) -> bool:
        if not role_ids:
            return False

        guild = self.bot.get_guild(guild_id)
        get_member = getattr(guild, "get_member", None)
        if not callable(get_member):
            return False

        member = get_member(user_id)
        if member is None:
            return False
        return any(
            getattr(role, "id", None) in role_ids
            for role in getattr(member, "roles", ())
        )

    def _authorized_session(
        self,
        request: web.Request,
    ) -> tuple[Optional[dict[str, Any]], set[int]]:
        session = self._read_signed_cookie(
            request,
            SESSION_COOKIE,
            max_age=SESSION_MAX_AGE_SECONDS,
        )
        if not session:
            return None, set()

        try:
            user_id = int(session["user_id"])
        except (KeyError, TypeError, ValueError):
            return None, set()

        authorized_guild_ids = self._authorized_guild_ids(user_id)
        if not authorized_guild_ids:
            return None, set()
        return session, authorized_guild_ids

    def _csrf_token(self, session: dict[str, Any], guild_id: int) -> str:
        try:
            user_id = int(session["user_id"])
            issued_at = int(session["iat"])
        except (KeyError, TypeError, ValueError):
            return ""
        payload = f"rai-web-admin-csrf:{user_id}:{issued_at}:{guild_id}".encode("ascii")
        digest = hmac.new(self.session_secret.encode("utf-8"), payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _valid_csrf_token(
        self,
        session: dict[str, Any],
        guild_id: int,
        candidate: Any,
    ) -> bool:
        expected = self._csrf_token(session, guild_id)
        return bool(
            expected
            and isinstance(candidate, str)
            and hmac.compare_digest(candidate, expected)
        )

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
