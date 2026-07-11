import json
import os
from typing import Optional


MIN_SESSION_SECRET_BYTES = 32
DISCORD_API_BASE_URL = "https://discord.com/api/v10"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
WEAK_SESSION_SECRETS = {
    "changeme",
    "change-me",
    "password",
    "secret",
    "test",
}

SPANISH_GUILD_ID = 243838819743432704
# Ordered from the lowest staff tier to the highest; any listed role grants access.
SPANISH_STAFF_ROLES_LOW_TO_HIGH = (
    (591745589054668817, "Trial Staff Helper"),
    (258819531193974784, "Server Staff"),
    (1483184760804347966, "Moderator"),
    (243854949522472971, "Administrator"),
)
SPANISH_ADMINISTRATOR_ROLE_ID = 243854949522472971
GUILD_ACCESS_ROLE_IDS = {
    SPANISH_GUILD_ID: frozenset(role_id for role_id, _ in SPANISH_STAFF_ROLES_LOW_TO_HIGH),
}
GUILD_CONFIG_EDITOR_ROLE_IDS = {
    SPANISH_GUILD_ID: frozenset({SPANISH_ADMINISTRATOR_ROLE_ID}),
}
LOGGING_MODULES = (
    ("deletes", "Deleted messages"),
    ("edits", "Edited messages"),
    ("joins", "Member joins"),
    ("leaves", "Member leaves"),
    ("kicks", "Member kicks"),
    ("bans", "Member bans"),
    ("nicknames", "Nickname changes"),
    ("reactions", "Reaction changes"),
    ("voice", "Voice activity"),
    ("channels", "Channel changes"),
)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on"}


def parse_int_set(value: Optional[str]) -> set[int]:
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


def parse_guild_admins(value: Optional[str]) -> dict[int, set[int]]:
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
