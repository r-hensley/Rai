from typing import Any, Optional

import discord

from .diagnostics import ACTIVITY_WINDOW_MINUTES
from .models import ActivitySnapshot, HealthCheck, Metric


class DashboardViewMixin:
    bot: Any
    renderer: Any

    def _render_dashboard(
        self,
        session: dict[str, Any],
        guild_ids: set[int],
        refresh_seconds: Optional[int] = None,
    ) -> str:
        try:
            user_id = int(session["user_id"])
        except (KeyError, TypeError, ValueError):
            user_id = 0
        user_label = str(session.get("username", session.get("user_id", "unknown")))
        if not self._is_owner_user(user_id):
            return self._render_guild_dashboard(guild_ids, user_label, refresh_seconds)

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
        metrics = (
            Metric("Queued messages · 60m", f"{activity.total_messages:,}", "Allowed guilds only"),
            Metric("Active members · 60m", f"{activity.active_users:,}", "Unique message authors"),
            Metric("Active channels · 60m", f"{activity.active_channels:,}", "Channels with messages"),
            Metric(
                "Background tasks",
                f"{running_tasks}/{len(tasks)}",
                "Running without a failed state",
                "ok" if running_tasks == len(tasks) and tasks else "error",
            ),
            Metric(
                "Live latency",
                f"{latency_ms:.0f} ms" if latency_ms is not None else "Unknown",
                "Event-loop response",
                latency_level,
            ),
            Metric(
                "Database checks",
                f"{passing_checks}/{len(health_checks)}",
                f"{warning_checks} warning · {error_checks} error",
                "error" if error_checks else "warning" if warning_checks else "ok",
            ),
        )

        runtime_rows = (
            self._bot_rows(guild_ids)
            + self._message_queue_rows()
            + [("Queue capacity", queue_detail)]
            + self._guild_rows(guild_ids)
        )
        config_rows = self._config_health_rows(guild_ids)

        return self.renderer.render(
            "dashboard.html",
            title="Rai Operations",
            user_label=user_label,
            refresh_seconds=refresh_seconds,
            show_refresh_controls=True,
            owner_view=True,
            status_level=overall_level,
            status_title=overall_title,
            status_detail=overall_detail,
            server_now_iso=server_now.isoformat(),
            server_now_display=server_now.strftime("%b %d, %I:%M:%S %p"),
            timezone_label=timezone_label,
            metrics=metrics,
            tasks=tasks,
            running_tasks=running_tasks,
            health_rows=self._health_view_rows(health_checks),
            passing_checks=passing_checks,
            runtime_rows=runtime_rows,
            guild_rows=(),
            config_rows=config_rows,
            **self._activity_view_context(activity),
        )

    def _render_guild_dashboard(
        self,
        guild_ids: set[int],
        user_label: str,
        refresh_seconds: Optional[int],
    ) -> str:
        activity = self._activity_snapshot(guild_ids)
        visible_guilds = sum(self.bot.get_guild(guild_id) is not None for guild_id in guild_ids)
        status_level = "ok" if visible_guilds == len(guild_ids) else "error"
        status_title = "Guild diagnostics available" if status_level == "ok" else "Guild visibility issue"
        status_detail = (
            f"{visible_guilds}/{len(guild_ids)} authorized guilds visible"
            if guild_ids else "No authorized guilds"
        )
        metrics = (
            Metric("Queued messages · 60m", f"{activity.total_messages:,}", "Allowed guilds only"),
            Metric("Active members · 60m", f"{activity.active_users:,}", "Unique message authors"),
            Metric("Active channels · 60m", f"{activity.active_channels:,}", "Channels with messages"),
        )
        config_rows = self._config_health_rows(guild_ids)
        return self.renderer.render(
            "dashboard.html",
            title="Rai Operations",
            user_label=user_label,
            refresh_seconds=refresh_seconds,
            show_refresh_controls=True,
            owner_view=False,
            status_level=status_level,
            status_title=status_title,
            status_detail=status_detail,
            metrics=metrics,
            tasks=(),
            running_tasks=0,
            health_rows=(),
            passing_checks=0,
            runtime_rows=(),
            guild_rows=self._guild_rows(guild_ids),
            config_rows=config_rows,
            **self._activity_view_context(activity),
        )

    @staticmethod
    def _activity_view_context(activity: ActivitySnapshot) -> dict[str, Any]:
        maximum = max(activity.bucket_counts, default=0)
        activity_bars = tuple(
            {
                "label": label,
                "count": count,
                "height": max(6, round(count / maximum * 100)) if count and maximum else 0,
            }
            for label, count in zip(activity.bucket_labels, activity.bucket_counts)
        )
        channel_maximum = max((count for _, count in activity.top_channels), default=0)
        channel_bars = tuple(
            {
                "label": label,
                "count": count,
                "width": max(2, round(count / channel_maximum * 100)),
            }
            for label, count in activity.top_channels
        ) if channel_maximum else ()
        coverage_label = (
            "Last 60 minutes"
            if activity.coverage_minutes >= ACTIVITY_WINDOW_MINUTES
            else f"{activity.coverage_minutes} of 60 minutes available"
        )
        return {
            "activity_bars": activity_bars,
            "channel_bars": channel_bars,
            "coverage_label": coverage_label,
            "activity_rate": f"{activity.total_messages / 60:.1f}/min",
        }

    @classmethod
    def _health_view_rows(cls, checks: list[HealthCheck]) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "label": check.label,
                "detail": check.detail,
                "level": check.level,
                "state": cls._level_label(check.level),
            }
            for check in checks
        )
