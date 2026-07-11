import logging
from copy import deepcopy
from typing import Any, Callable, Mapping, Optional

from aiohttp import web

from cogs.utils.BotUtils import bot_utils as utils

from .config import LOGGING_MODULES
from .security import SESSION_COOKIE


log = logging.getLogger("rai.web_admin.audit")

ANTISPAM_ACTIONS = ("mute", "kick", "ban")
ANTISPAM_DEFAULTS = {
    "enable": False,
    "action": "mute",
    "message_threshold": 5,
    "time_threshold": 10,
    "ignored": [],
    "exempt_roles": [],
    "ban_override": 0,
}
SAVED_MESSAGES = {
    "staff": "Staff settings saved.",
    "logging": "Logging settings saved.",
    "antispam": "Antispam settings saved.",
}


class SettingsValidationError(ValueError):
    pass


class SettingsPersistenceError(RuntimeError):
    pass


class SettingsMixin:
    bot: Any
    renderer: Any
    config_write_lock: Any

    async def settings_index(self, request: web.Request) -> web.Response:
        session, guild_ids = self._authorized_session(request)
        if not session:
            return self._settings_login_redirect(request)

        visible_guilds = tuple(
            guild
            for guild_id in sorted(guild_ids)
            if (guild := self.bot.get_guild(guild_id)) is not None
        )
        if len(visible_guilds) == 1:
            return web.HTTPFound(f"/settings/{visible_guilds[0].id}")

        user_id = int(session["user_id"])
        guilds = tuple(
            {
                "id": guild.id,
                "name": guild.name,
                "can_edit": self._can_manage_guild(guild.id, user_id),
            }
            for guild in visible_guilds
        )
        body = self.renderer.render(
            "settings_index.html",
            title="Rai Settings",
            user_label=self._session_user_label(session),
            refresh_seconds=None,
            show_refresh_controls=False,
            guilds=guilds,
        )
        return self._html_response("Rai Settings", body)

    async def settings_detail(self, request: web.Request) -> web.Response:
        scope = self._settings_scope(request)
        if isinstance(scope, web.StreamResponse):
            return scope
        session, guild = scope
        return self._settings_response(
            session,
            guild,
            success_message=SAVED_MESSAGES.get(request.query.get("saved", "")),
        )

    async def update_staff_settings(self, request: web.Request) -> web.Response:
        return await self._handle_settings_update(
            request,
            area="staff",
            section_names=("mod_channel", "mod_role", "submod_role"),
            parse=self._parse_staff_settings,
            apply=self._apply_staff_settings,
        )

    async def update_logging_settings(self, request: web.Request) -> web.Response:
        return await self._handle_settings_update(
            request,
            area="logging",
            section_names=tuple(module for module, _ in LOGGING_MODULES),
            parse=self._parse_logging_settings,
            apply=self._apply_logging_settings,
        )

    async def update_antispam_settings(self, request: web.Request) -> web.Response:
        return await self._handle_settings_update(
            request,
            area="antispam",
            section_names=("antispam",),
            parse=self._parse_antispam_settings,
            apply=self._apply_antispam_settings,
        )

    async def _handle_settings_update(
        self,
        request: web.Request,
        *,
        area: str,
        section_names: tuple[str, ...],
        parse: Callable[[Mapping[str, Any], Any], dict[str, Any]],
        apply: Callable[[int, dict[str, Any]], None],
    ) -> web.Response:
        scope = self._settings_scope(request)
        if isinstance(scope, web.StreamResponse):
            return scope
        session, guild = scope
        user_id = int(session["user_id"])
        if not self._can_manage_guild(guild.id, user_id):
            return self._settings_error_response(
                "Access Denied",
                "Only the bot owner or the server Administrator role can change settings.",
                403,
                session,
            )

        form = await request.post()
        if not self._valid_csrf_token(session, guild.id, form.get("csrf_token")):
            return self._settings_error_response(
                "Request Rejected",
                "The settings form expired or failed its security check. Reload it and try again.",
                403,
                session,
            )

        try:
            self._require_configuration_sections(section_names)
            payload = parse(form, guild)
            await self._persist_guild_update(
                guild.id,
                section_names,
                lambda: apply(guild.id, payload),
            )
        except SettingsValidationError as exc:
            return self._settings_response(session, guild, error_message=str(exc), status=400)
        except SettingsPersistenceError:
            return self._settings_response(
                session,
                guild,
                error_message="Rai could not save the configuration. No web changes were kept.",
                status=503,
            )

        log.warning(
            "configuration_updated actor_user_id=%s guild_id=%s area=%s",
            user_id,
            guild.id,
            area,
        )
        return web.HTTPSeeOther(location=f"/settings/{guild.id}?saved={area}")

    def _settings_scope(
        self,
        request: web.Request,
    ) -> tuple[dict[str, Any], Any] | web.StreamResponse:
        session, guild_ids = self._authorized_session(request)
        if not session:
            return self._settings_login_redirect(request)

        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, TypeError, ValueError):
            return self._settings_error_response(
                "Not Found",
                "The requested settings page does not exist.",
                404,
                session,
            )
        if guild_id not in guild_ids:
            return self._settings_error_response(
                "Access Denied",
                "Your Discord account cannot access that server.",
                403,
                session,
            )

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return self._settings_error_response(
                "Server Unavailable",
                "Rai cannot currently see that server.",
                503,
                session,
            )
        return session, guild

    def _settings_login_redirect(self, request: web.Request) -> web.Response:
        response = web.HTTPFound("/")
        if request.cookies.get(SESSION_COOKIE):
            self._delete_cookie(response, SESSION_COOKIE)
        return response

    def _settings_error_response(
        self,
        title: str,
        message: str,
        status: int,
        session: Optional[dict[str, Any]] = None,
    ) -> web.Response:
        body = self.renderer.render(
            "error.html",
            title=title,
            message=message,
            user_label=self._session_user_label(session) if session else None,
            refresh_seconds=None,
            show_refresh_controls=False,
        )
        return self._html_response(title, body, status)

    def _settings_response(
        self,
        session: dict[str, Any],
        guild: Any,
        *,
        success_message: Optional[str] = None,
        error_message: Optional[str] = None,
        status: int = 200,
    ) -> web.Response:
        user_id = int(session["user_id"])
        body = self.renderer.render(
            "settings.html",
            title=f"{guild.name} Settings",
            user_label=self._session_user_label(session),
            refresh_seconds=None,
            show_refresh_controls=False,
            guild=guild,
            can_edit=self._can_manage_guild(guild.id, user_id),
            csrf_token=self._csrf_token(session, guild.id),
            success_message=success_message,
            error_message=error_message,
            **self._settings_view_context(guild),
        )
        return self._html_response("Rai Settings", body, status)

    @staticmethod
    def _session_user_label(session: dict[str, Any]) -> str:
        return str(session.get("username", session.get("user_id", "unknown")))

    def _settings_view_context(self, guild: Any) -> dict[str, Any]:
        guild_key = str(guild.id)
        db = self.bot.db if isinstance(self.bot.db, dict) else {}
        base_channels = self._base_channel_options(guild)
        base_roles = self._base_role_options(guild)

        mod_channel = self._positive_int(self._mapping_value(db, "mod_channel", guild_key))
        mod_roles = self._role_config_ids(self._mapping_value(db, "mod_role", guild_key))
        submod_roles = self._role_config_ids(self._mapping_value(db, "submod_role", guild_key))

        logging_modules = []
        for module, label in LOGGING_MODULES:
            config = self._mapping_value(db, module, guild_key)
            config = config if isinstance(config, dict) else {}
            channel_id = self._positive_int(config.get("channel"))
            logging_modules.append({
                "key": module,
                "label": label,
                "enabled": bool(config.get("enable")),
                "channel_id": channel_id,
                "channel_options": self._marked_options(
                    base_channels,
                    {channel_id} if channel_id else set(),
                    "Missing channel",
                ),
            })

        antispam_config = self._mapping_value(db, "antispam", guild_key)
        antispam_config = antispam_config if isinstance(antispam_config, dict) else {}
        ignored_channels = set(self._id_list(antispam_config.get("ignored")))
        exempt_roles = set(self._id_list(antispam_config.get("exempt_roles")))
        action = antispam_config.get("action")
        if action not in ANTISPAM_ACTIONS:
            action = ANTISPAM_DEFAULTS["action"]

        antispam = {
            "enabled": bool(antispam_config.get("enable")),
            "action": action,
            "message_threshold": self._display_int(
                antispam_config.get("message_threshold"),
                ANTISPAM_DEFAULTS["message_threshold"],
            ),
            "time_threshold": self._display_int(
                antispam_config.get("time_threshold"),
                ANTISPAM_DEFAULTS["time_threshold"],
            ),
            "ban_override": self._display_int(
                antispam_config.get("ban_override"),
                ANTISPAM_DEFAULTS["ban_override"],
            ),
            "ignored_channel_options": self._marked_options(
                base_channels,
                ignored_channels,
                "Missing channel",
            ),
            "exempt_role_options": self._marked_options(
                base_roles,
                exempt_roles,
                "Missing role",
            ),
        }
        return {
            "mod_channel_id": mod_channel or 0,
            "mod_channel_options": self._marked_options(
                base_channels,
                {mod_channel} if mod_channel else set(),
                "Missing channel",
            ),
            "mod_role_options": self._marked_options(base_roles, set(mod_roles), "Missing role"),
            "submod_role_options": self._marked_options(base_roles, set(submod_roles), "Missing role"),
            "logging_modules": tuple(logging_modules),
            "antispam": antispam,
            "antispam_actions": ANTISPAM_ACTIONS,
        }

    @staticmethod
    def _base_channel_options(guild: Any) -> tuple[dict[str, Any], ...]:
        return tuple(
            {"id": int(channel.id), "label": f"#{channel.name}"}
            for channel in getattr(guild, "text_channels", ())
            if isinstance(getattr(channel, "id", None), int)
        )

    @staticmethod
    def _base_role_options(guild: Any) -> tuple[dict[str, Any], ...]:
        return tuple(
            {"id": int(role.id), "label": f"@{role.name}"}
            for role in reversed(tuple(getattr(guild, "roles", ())))
            if isinstance(getattr(role, "id", None), int) and role.id != guild.id
        )

    @staticmethod
    def _marked_options(
        options: tuple[dict[str, Any], ...],
        selected_ids: set[int],
        missing_label: str,
    ) -> tuple[dict[str, Any], ...]:
        rendered = [
            {**option, "selected": option["id"] in selected_ids, "missing": False}
            for option in options
        ]
        available_ids = {option["id"] for option in options}
        rendered.extend(
            {
                "id": item_id,
                "label": f"{missing_label} ({item_id})",
                "selected": True,
                "missing": True,
            }
            for item_id in sorted(selected_ids - available_ids)
        )
        return tuple(rendered)

    @staticmethod
    def _mapping_value(db: dict[str, Any], section: str, guild_key: str) -> Any:
        mapping = db.get(section)
        return mapping.get(guild_key) if isinstance(mapping, dict) else None

    @classmethod
    def _role_config_ids(cls, config: Any) -> tuple[int, ...]:
        if not isinstance(config, dict):
            return ()
        return cls._id_list(config.get("id"))

    @staticmethod
    def _positive_int(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 and not isinstance(value, bool) else None

    @classmethod
    def _id_list(cls, value: Any) -> tuple[int, ...]:
        values = value if isinstance(value, (list, tuple, set)) else (value,)
        return tuple(dict.fromkeys(
            parsed
            for item in values
            if (parsed := cls._positive_int(item)) is not None
        ))

    @staticmethod
    def _display_int(value: Any, default: int) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    def _parse_staff_settings(self, form: Mapping[str, Any], guild: Any) -> dict[str, Any]:
        valid_channels = {option["id"] for option in self._base_channel_options(guild)}
        valid_roles = {option["id"] for option in self._base_role_options(guild)}
        return {
            "mod_channel": self._form_single_id(
                form,
                "mod_channel",
                valid_channels,
                "Moderation channel",
            ),
            "mod_roles": self._form_id_list(
                form,
                "mod_roles",
                valid_roles,
                "Moderator roles",
                maximum=10,
            ),
            "submod_roles": self._form_id_list(
                form,
                "submod_roles",
                valid_roles,
                "Submoderator roles",
                maximum=20,
            ),
        }

    def _parse_logging_settings(self, form: Mapping[str, Any], guild: Any) -> dict[str, Any]:
        valid_channels = {option["id"] for option in self._base_channel_options(guild)}
        modules = {}
        for module, label in LOGGING_MODULES:
            channel_id = self._form_single_id(
                form,
                f"{module}_channel",
                valid_channels,
                f"{label} channel",
            )
            enabled = f"{module}_enabled" in form
            if enabled and channel_id is None:
                raise SettingsValidationError(f"{label} requires a destination channel when enabled.")
            modules[module] = {"enable": enabled, "channel": channel_id}
        return modules

    def _parse_antispam_settings(self, form: Mapping[str, Any], guild: Any) -> dict[str, Any]:
        action = str(form.get("action", "")).casefold()
        if action not in ANTISPAM_ACTIONS:
            raise SettingsValidationError("Antispam action must be mute, kick, or ban.")

        valid_channels = {option["id"] for option in self._base_channel_options(guild)}
        valid_roles = {option["id"] for option in self._base_role_options(guild)}
        return {
            "enable": "enabled" in form,
            "action": action,
            "message_threshold": self._form_integer(
                form,
                "message_threshold",
                "Message threshold",
                minimum=2,
                maximum=50,
            ),
            "time_threshold": self._form_integer(
                form,
                "time_threshold",
                "Time threshold",
                minimum=1,
                maximum=300,
            ),
            "ban_override": self._form_integer(
                form,
                "ban_override",
                "New-member ban override",
                minimum=0,
                maximum=10_080,
            ),
            "ignored": self._form_id_list(
                form,
                "ignored_channels",
                valid_channels,
                "Ignored channels",
                maximum=100,
            ),
            "exempt_roles": self._form_id_list(
                form,
                "exempt_roles",
                valid_roles,
                "Exempt roles",
                maximum=50,
            ),
        }

    @classmethod
    def _form_single_id(
        cls,
        form: Mapping[str, Any],
        field: str,
        valid_ids: set[int],
        label: str,
    ) -> Optional[int]:
        raw = form.get(field, "0")
        if raw is None or raw == "" or raw == "0" or raw == 0:
            return None
        parsed = cls._positive_int(raw)
        if parsed is None or parsed not in valid_ids:
            raise SettingsValidationError(f"{label} is not a valid server channel or role.")
        return parsed

    @classmethod
    def _form_id_list(
        cls,
        form: Mapping[str, Any],
        field: str,
        valid_ids: set[int],
        label: str,
        *,
        maximum: int,
    ) -> list[int]:
        values = cls._form_values(form, field)
        if len(values) > maximum:
            raise SettingsValidationError(f"{label} accepts at most {maximum} selections.")
        parsed_values = []
        for value in values:
            parsed = cls._positive_int(value)
            if parsed is None or parsed not in valid_ids:
                raise SettingsValidationError(f"{label} contains an invalid server selection.")
            parsed_values.append(parsed)
        return list(dict.fromkeys(parsed_values))

    @staticmethod
    def _form_values(form: Mapping[str, Any], field: str) -> list[Any]:
        getall = getattr(form, "getall", None)
        if callable(getall):
            return list(getall(field, []))
        value = form.get(field, [])
        return list(value) if isinstance(value, (list, tuple)) else ([value] if value else [])

    @staticmethod
    def _form_integer(
        form: Mapping[str, Any],
        field: str,
        label: str,
        *,
        minimum: int,
        maximum: int,
    ) -> int:
        try:
            value = int(form.get(field, ""))
        except (TypeError, ValueError) as exc:
            raise SettingsValidationError(f"{label} must be a whole number.") from exc
        if value < minimum or value > maximum:
            raise SettingsValidationError(f"{label} must be between {minimum} and {maximum}.")
        return value

    def _require_configuration_sections(self, section_names: tuple[str, ...]) -> None:
        if not isinstance(self.bot.db, dict):
            raise SettingsValidationError("Rai's configuration database is unavailable.")
        invalid = [name for name in section_names if not isinstance(self.bot.db.get(name), dict)]
        if invalid:
            noun = "section is" if len(invalid) == 1 else "sections are"
            raise SettingsValidationError(
                f"Rai's {', '.join(invalid)} configuration {noun} unavailable or malformed."
            )

    async def _persist_guild_update(
        self,
        guild_id: int,
        section_names: tuple[str, ...],
        update: Callable[[], None],
    ) -> None:
        guild_key = str(guild_id)
        async with self.config_write_lock:
            snapshots = {
                section: (
                    guild_key in self.bot.db[section],
                    deepcopy(self.bot.db[section].get(guild_key)),
                )
                for section in section_names
            }
            try:
                update()
                await utils.dump_json("db")
            except SettingsValidationError:
                for section, (existed, value) in snapshots.items():
                    mapping = self.bot.db[section]
                    if existed:
                        mapping[guild_key] = value
                    else:
                        mapping.pop(guild_key, None)
                raise
            except Exception as exc:
                for section, (existed, value) in snapshots.items():
                    mapping = self.bot.db[section]
                    if existed:
                        mapping[guild_key] = value
                    else:
                        mapping.pop(guild_key, None)
                log.exception(
                    "configuration_update_failed guild_id=%s sections=%s",
                    guild_id,
                    ",".join(section_names),
                )
                raise SettingsPersistenceError from exc

    def _apply_staff_settings(self, guild_id: int, payload: dict[str, Any]) -> None:
        guild_key = str(guild_id)
        mod_channel = self.bot.db["mod_channel"]
        if payload["mod_channel"] is None:
            mod_channel.pop(guild_key, None)
        else:
            mod_channel[guild_key] = payload["mod_channel"]

        self._set_role_config("mod_role", guild_key, payload["mod_roles"], single_when_possible=True)
        self._set_role_config("submod_role", guild_key, payload["submod_roles"], single_when_possible=False)

    def _set_role_config(
        self,
        section: str,
        guild_key: str,
        role_ids: list[int],
        *,
        single_when_possible: bool,
    ) -> None:
        mapping = self.bot.db[section]
        if not role_ids:
            mapping.pop(guild_key, None)
            return
        existing = mapping.get(guild_key)
        if existing is not None and not isinstance(existing, dict):
            raise SettingsValidationError(f"The existing {section} configuration is malformed.")
        config = dict(existing or {})
        config["id"] = role_ids[0] if single_when_possible and len(role_ids) == 1 else role_ids
        mapping[guild_key] = config

    def _apply_logging_settings(self, guild_id: int, payload: dict[str, Any]) -> None:
        guild_key = str(guild_id)
        for module, _label in LOGGING_MODULES:
            mapping = self.bot.db[module]
            existing = mapping.get(guild_key)
            if existing is not None and not isinstance(existing, dict):
                raise SettingsValidationError(f"The existing {module} configuration is malformed.")
            config = dict(existing or {})
            config.update(payload[module])
            mapping[guild_key] = config

    def _apply_antispam_settings(self, guild_id: int, payload: dict[str, Any]) -> None:
        guild_key = str(guild_id)
        mapping = self.bot.db["antispam"]
        existing = mapping.get(guild_key)
        if existing is not None and not isinstance(existing, dict):
            raise SettingsValidationError("The existing antispam configuration is malformed.")
        config = dict(existing or {})
        config.update(payload)
        mapping[guild_key] = config
