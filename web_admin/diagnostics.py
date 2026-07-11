import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from .models import ActivitySnapshot, HealthCheck, TaskSnapshot


INVALID_CONFIG = object()
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


class DiagnosticsMixin:
    bot: Any

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

    @staticmethod
    def _safe_text(value: Any) -> str:
        return str(value)
