"""Reusable Discord-shaped objects for Rai's tests.

These are factories, not shared mock instances.  Every call returns fresh
namespaces, collections, and mocks so a test cannot inherit another test's
mutations or mock call history.

The factories intentionally model only common Discord structure.  Tests should
pass one-off attributes and behavior as keyword overrides instead of continually
growing every fake into a permissive copy of all of discord.py.

These objects are structurally Discord-shaped but remain ``SimpleNamespace``
instances.  Code paths that depend on ``isinstance(obj, discord.SomeType)``
should continue to use a local ``Mock(spec_set=discord.SomeType)``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Mapping
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import discord


# Realistic, distinct snowflake-shaped defaults let factories work with code
# that validates Discord IDs by their 18-21 digit length.
DEFAULT_GUILD_ID = 111111111111111111
DEFAULT_CHANNEL_ID = 222222222222222222
DEFAULT_THREAD_ID = 333333333333333333
DEFAULT_MESSAGE_ID = 444444444444444444
DEFAULT_MEMBER_ID = 555555555555555555
DEFAULT_ROLE_ID = 666666666666666666
DEFAULT_BOT_ID = 777777777777777777
DEFAULT_CATEGORY_ID = 888888888888888888
DEFAULT_ATTACHMENT_ID = 999999999999999999


_MISSING = object()


class _DiscordFake(SimpleNamespace):
    """Namespace with non-recursive, Discord-style snowflake equality.

    Discord entities compare by their type and snowflake rather than walking
    their attributes. That also keeps cyclic guild/channel/member graphs from
    triggering ``SimpleNamespace``'s recursive structural equality.
    """

    def __eq__(self, other: object) -> bool:
        if self is other:
            return True
        self_kind = getattr(self, "_fake_discord_kind", None)
        self_id = getattr(self, "id", None)
        if self_kind is None or self_id is None:
            return False
        return (
            getattr(other, "_fake_discord_kind", None) == self_kind
            and getattr(other, "id", None) == self_id
        )

    def __hash__(self) -> int:
        fake_kind = getattr(self, "_fake_discord_kind", None)
        object_id = getattr(self, "id", None)
        if fake_kind is None or object_id is None:
            return object.__hash__(self)
        return hash((fake_kind, object_id))


def _namespace(defaults: dict[str, Any], overrides: dict[str, Any]) -> SimpleNamespace:
    """Return a new namespace after applying explicit test-specific values."""
    reserved = sorted(key for key in overrides if key.startswith("_fake_"))
    if reserved:
        raise TypeError(
            "Factory-internal override name(s) are reserved: "
            + ", ".join(reserved)
        )
    defaults.update(overrides)
    return _DiscordFake(**defaults)


def _objects_by_id(objects: Iterable[Any] | Mapping[int, Any]) -> dict[int, Any]:
    """Normalize either Discord-like objects or an explicit ID mapping."""
    if isinstance(objects, Mapping):
        return dict(objects)

    objects_by_id = {}
    for item in objects:
        if item.id in objects_by_id:
            raise ValueError(f"Duplicate Discord fake ID {item.id}")
        objects_by_id[item.id] = item
    return objects_by_id


def _reject_id_override(factory_name: str, overrides: dict[str, Any]) -> None:
    """Keep IDs and fields derived from them from silently disagreeing."""
    if "id" in overrides:
        parameter_name = {
            "make_attachment": "attachment_id",
            "make_category": "category_id",
            "make_channel": "channel_id",
            "make_guild": "guild_id",
            "make_member": "member_id",
            "make_message": "message_id",
            "make_message_reference": "message_id",
            "make_role": "role_id",
            "make_thread": "thread_id",
        }[factory_name]
        raise TypeError(
            f"{factory_name}() uses {parameter_name}=, not the id= override"
        )


def _coalesce_same(label: str, *values: Any) -> Any:
    """Choose the one supplied relationship or reject contradictory objects."""
    resolved = None
    for value in values:
        if value is None:
            continue
        if resolved is None:
            resolved = value
        elif value is not resolved:
            raise ValueError(f"Conflicting {label} objects supplied to fake factory")
    return resolved


def _link_guild(
        obj: Any,
        guild: SimpleNamespace,
        *,
        allow_foreign: bool = False,
) -> None:
    """Fill an absent guild link and reject accidental inconsistent graphs."""
    _validate_helper_kind(guild, "guild")
    existing_guild = getattr(obj, "guild", None)
    if existing_guild is guild:
        return
    if existing_guild is not None:
        if allow_foreign:
            return
        raise ValueError("Discord fake is already linked to a different guild")
    try:
        obj.guild = guild
    except (AttributeError, TypeError):
        # Some spec-constrained mocks or immutable test records may not allow
        # the relationship to be assigned.  Their creator remains responsible
        # for supplying the link explicitly.
        pass


def _link_relation(obj: Any, attribute: str, value: Any) -> None:
    """Set a missing object relationship or reject a contradictory one."""
    existing = getattr(obj, attribute, None)
    if existing is value:
        return
    if existing is not None:
        raise ValueError(
            f"Discord fake's {attribute} is already linked to a different object"
        )
    try:
        setattr(obj, attribute, value)
    except (AttributeError, TypeError) as exc:
        raise TypeError(
            f"Cannot set {attribute} on supplied Discord test object"
        ) from exc


def _find_by_id(objects: Iterable[Any], object_id: int) -> Any:
    """Return the first object with a matching Discord ID."""
    return next((obj for obj in objects if obj.id == object_id), None)


def _register_guild_object(
        guild: Any,
        collection_name: str,
        obj: Any,
) -> None:
    """Register an object with a helper-built guild without duplicating IDs."""
    if getattr(guild, "_fake_discord_kind", None) != "guild":
        return

    collection = getattr(guild, collection_name)
    collections_to_check = [collection]
    if collection_name == "channels":
        collections_to_check.append(guild.threads)
    elif collection_name == "threads":
        collections_to_check.append(guild.channels)

    for objects in collections_to_check:
        for existing in objects:
            if existing is obj:
                if objects is collection:
                    return
                raise ValueError(
                    "The same Discord fake cannot be both a channel and a thread"
                )
            if existing.id == obj.id:
                raise ValueError(
                    "Guild fake already has a different cached object "
                    f"with ID {obj.id}"
                )
    collection.append(obj)

    # Guild.categories and Guild.text_channels are filtered views over the
    # broader Guild.channels cache. Keep those lists synchronized when an
    # object is created after its helper-built guild.
    if collection_name == "channels":
        object_kind = getattr(obj, "_fake_discord_kind", None)
        if object_kind == "category":
            guild.categories.append(obj)
        elif object_kind == "channel":
            guild.text_channels.append(obj)


def _link_channel_messages(channel: Any, guild: SimpleNamespace) -> None:
    """Propagate a channel's guild to messages configured for fetch_message."""
    for attribute in ("_fake_messages", "_fake_history_messages"):
        for message in getattr(channel, attribute, ()):
            _link_guild(message, guild)


def _link_member_roles(member: Any, guild: SimpleNamespace) -> None:
    """Keep a helper member's configured roles in the same guild graph."""
    for role in getattr(member, "roles", ()):
        _link_guild(role, guild)
        if getattr(role, "_fake_discord_kind", None) == "role":
            _register_guild_object(guild, "roles", role)


def _validate_helper_kind(
        obj: Any,
        expected_kind: str | set[str],
) -> None:
    """Reject putting one helper-built Discord kind in another kind's slot."""
    expected_kinds = {expected_kind} if isinstance(expected_kind, str) else expected_kind
    actual_kind = getattr(obj, "_fake_discord_kind", None)
    if actual_kind is not None and actual_kind not in expected_kinds:
        expected_label = " or ".join(sorted(expected_kinds))
        raise ValueError(
            f"Expected a {expected_label} fake, got helper-built {actual_kind}"
        )


def _attach_channel(
        guild: SimpleNamespace,
        channel: Any,
        *,
        register: bool = True,
        allow_foreign: bool = False,
) -> None:
    """Attach a channel graph to a guild and optionally expose it in cache."""
    _link_guild(channel, guild, allow_foreign=allow_foreign)
    if getattr(channel, "guild", None) is not guild:
        return

    channel_kind = getattr(channel, "_fake_discord_kind", None)
    parent = getattr(channel, "parent", None)
    if channel_kind == "thread" and parent is not None:
        _validate_helper_kind(parent, "channel")
        thread_is_cached = any(existing is channel for existing in guild.threads)
        _attach_channel(
            guild,
            parent,
            register=register or thread_is_cached,
        )

    _link_channel_messages(channel, guild)
    if register and channel_kind in {"category", "channel", "thread"}:
        collection_name = "threads" if channel_kind == "thread" else "channels"
        _register_guild_object(guild, collection_name, channel)


def _attach_member(guild: SimpleNamespace, member: Any) -> None:
    """Attach a member and its configured roles to a guild."""
    _link_guild(member, guild)
    if getattr(member, "_fake_discord_kind", None) == "member":
        _register_guild_object(guild, "members", member)
    _link_member_roles(member, guild)


def _strict_async_mock(name: str) -> AsyncMock:
    """Fail clearly if code reaches an API operation the test did not configure."""
    return AsyncMock(
        side_effect=AssertionError(
            f"Unexpected {name} call; configure this behavior in the test."
        )
    )


def discord_not_found(
        *,
        message: str = "Unknown Message",
        code: int = 10008,
) -> discord.NotFound:
    """Create the same exception shape as a Discord HTTP 404 response.

    Discord error 10008 means "Unknown Message".  Callers can override the
    message and code for other missing resources, such as error 10003 for an
    unknown channel.
    """
    response = SimpleNamespace(status=404, reason="Not Found")
    return discord.NotFound(response, {"code": code, "message": message})


async def empty_async_history(*_args: Any, **_kwargs: Any) -> AsyncIterator[Any]:
    """Return an empty async iterator with the shape of channel.history()."""
    # The unreachable yield is what makes this function an async generator,
    # allowing production code to use ``async for`` over its result.
    if False:
        yield None


async def _async_items(items: Iterable[Any]) -> AsyncIterator[Any]:
    """Yield configured history records through an async iterator."""
    for item in items:
        yield item


def make_category(
        *,
        category_id: int = DEFAULT_CATEGORY_ID,
        name: str = "test-category",
        guild: Any = None,
        **overrides: Any,
) -> SimpleNamespace:
    """Create a category-shaped guild channel and register it when possible."""
    _reject_id_override("make_category", overrides)
    category = _namespace(
        {
            "id": category_id,
            "name": name,
            "mention": f"<#{category_id}>",
            "guild": guild,
            "_fake_discord_kind": "category",
        },
        overrides,
    )
    if guild is not None:
        _attach_channel(guild, category)
    return category


def make_role(
        *,
        role_id: int = DEFAULT_ROLE_ID,
        name: str = "Test Role",
        guild: Any = None,
        **overrides: Any,
) -> SimpleNamespace:
    """Create a fresh, inert Discord-role-shaped namespace."""
    _reject_id_override("make_role", overrides)
    role = _namespace(
        {
            "id": role_id,
            "name": name,
            "mention": f"<@&{role_id}>",
            "guild": guild,
            "_fake_discord_kind": "role",
        },
        overrides,
    )
    if guild is not None:
        _link_guild(role, guild)
        _register_guild_object(guild, "roles", role)
    return role


def make_member(
        *,
        member_id: int = DEFAULT_MEMBER_ID,
        name: str = "test-user",
        display_name: str | None = None,
        global_name: str | None = None,
        guild: Any = None,
        roles: Iterable[Any] = (),
        bot: bool = False,
        **overrides: Any,
) -> SimpleNamespace:
    """Create a fresh Discord-member-shaped namespace.

    Methods such as ``send`` or ``add_roles`` are deliberately not universal
    defaults.  Tests exercising them should pass an ``AsyncMock`` override so
    the capability and its assertion remain visible in that test.
    """
    _reject_id_override("make_member", overrides)
    role_list = list(roles)
    for role in role_list:
        _validate_helper_kind(role, "role")
    guild = _coalesce_same(
        "guild",
        guild,
        *(getattr(role, "guild", None) for role in role_list),
    )
    member = _namespace(
        {
            "id": member_id,
            "name": name,
            "display_name": display_name if display_name is not None else name,
            "global_name": global_name,
            "mention": f"<@{member_id}>",
            "guild": guild,
            "roles": role_list,
            "bot": bot,
            "_fake_discord_kind": "member",
        },
        overrides,
    )
    if guild is not None:
        _attach_member(guild, member)
    return member


def make_bot(
        *,
        user: Any = _MISSING,
        db: Mapping[Any, Any] | None = None,
        stats: Mapping[Any, Any] | None = None,
        message_queue: Any = None,
        guilds: Iterable[Any] = (),
        channels: Iterable[Any] = (),
        **overrides: Any,
) -> SimpleNamespace:
    """Create a fresh Rai/discord.py bot-shaped namespace.

    Guild and channel cache lookups are synchronous, matching discord.py.
    Network-style ``fetch_channel`` is strict until a test configures it.
    """
    guild_list = list(guilds)
    channel_list = list(channels)
    for guild in guild_list:
        _validate_helper_kind(guild, "guild")
    for channel in channel_list:
        _validate_helper_kind(channel, {"category", "channel", "thread"})

    _objects_by_id(guild_list)
    _objects_by_id(channel_list)
    if user is _MISSING:
        user = make_member(member_id=DEFAULT_BOT_ID, name="Rai", bot=True)
    else:
        _validate_helper_kind(user, "member")

    bot: SimpleNamespace

    def get_guild(guild_id: int) -> Any:
        return _find_by_id(bot.guilds, guild_id)

    def get_channel(channel_id: int) -> Any:
        channel = _find_by_id(bot.channels, channel_id)
        if channel is not None:
            return channel
        for guild in bot.guilds:
            channel = _find_by_id(guild.channels, channel_id)
            if channel is not None:
                return channel
            thread = _find_by_id(guild.threads, channel_id)
            if thread is not None:
                return thread
        return None

    bot = _namespace(
        {
            "user": user,
            "db": dict(db) if db is not None else {},
            "stats": dict(stats) if stats is not None else {},
            "message_queue": message_queue,
            "guilds": guild_list,
            "channels": channel_list,
            "get_guild": Mock(side_effect=get_guild),
            "get_channel": Mock(side_effect=get_channel),
            "fetch_channel": _strict_async_mock("bot.fetch_channel"),
            "profiling_decorators": set(),
            "latency": 0.0,
            "_fake_discord_kind": "bot",
        },
        overrides,
    )
    return bot


def make_attachment(
        *,
        attachment_id: int = DEFAULT_ATTACHMENT_ID,
        channel_id: int = DEFAULT_CHANNEL_ID,
        filename: str = "attachment.txt",
        data: bytes = b"",
        content_type: str | None = None,
        size: int | None = None,
        url: str | None = None,
        proxy_url: str | None = None,
        description: str | None = None,
        ephemeral: bool = False,
        **overrides: Any,
) -> SimpleNamespace:
    """Create an attachment with fresh awaitable read/save operations."""
    _reject_id_override("make_attachment", overrides)
    attachment_url = url or (
        "https://cdn.discordapp.com/attachments/"
        f"{channel_id}/{attachment_id}/{filename}"
    )
    return _namespace(
        {
            "id": attachment_id,
            "filename": filename,
            "content_type": content_type,
            "size": len(data) if size is None else size,
            "url": attachment_url,
            "proxy_url": proxy_url or attachment_url,
            "description": description,
            "ephemeral": ephemeral,
            "read": AsyncMock(return_value=data),
            "save": AsyncMock(),
            "to_file": AsyncMock(),
            "_fake_discord_kind": "attachment",
        },
        overrides,
    )


def make_message_reference(
        *,
        message_id: int | None = None,
        channel_id: int | None = None,
        guild_id: int | None = None,
        resolved: Any = None,
        cached_message: Any = None,
        fail_if_not_exists: bool = True,
        **overrides: Any,
) -> SimpleNamespace:
    """Create a message reference, deriving IDs from supplied message records."""
    _reject_id_override("make_message_reference", overrides)
    related_messages = [
        message
        for message in (resolved, cached_message)
        if message is not None
    ]
    for message in related_messages:
        _validate_helper_kind(message, "message")

    def resolve_id(
            label: str,
            explicit_value: int | None,
            derived_values: Iterable[int | None],
            default: int | None,
    ) -> int | None:
        values = {value for value in derived_values if value is not None}
        if len(values) > 1:
            raise ValueError(f"Referenced messages disagree on {label}")
        derived_value = next(iter(values), None)
        if (
                explicit_value is not None
                and derived_value is not None
                and explicit_value != derived_value
        ):
            raise ValueError(f"Message reference's {label} disagrees with its message")
        if explicit_value is not None:
            return explicit_value
        if derived_value is not None:
            return derived_value
        return default

    resolved_message_id = resolve_id(
        "message_id",
        message_id,
        (getattr(message, "id", None) for message in related_messages),
        DEFAULT_MESSAGE_ID,
    )
    resolved_channel_id = resolve_id(
        "channel_id",
        channel_id,
        (
            getattr(getattr(message, "channel", None), "id", None)
            for message in related_messages
        ),
        DEFAULT_CHANNEL_ID,
    )
    resolved_guild_id = resolve_id(
        "guild_id",
        guild_id,
        (
            getattr(getattr(message, "guild", None), "id", None)
            for message in related_messages
        ),
        None,
    )
    return _namespace(
        {
            "message_id": resolved_message_id,
            "channel_id": resolved_channel_id,
            "guild_id": resolved_guild_id,
            "resolved": resolved,
            "cached_message": cached_message,
            "fail_if_not_exists": fail_if_not_exists,
            "_fake_discord_kind": "message_reference",
        },
        overrides,
    )


def _message_fetch_mock(
        messages: Iterable[Any] | Mapping[int, Any] | object,
) -> tuple[AsyncMock, dict[int, Any]]:
    """Build a strict or record-backed channel.fetch_message mock."""
    if messages is _MISSING:
        return _strict_async_mock("channel.fetch_message"), {}

    message_map = _objects_by_id(messages)

    def fetch_message(message_id: int) -> Any:
        try:
            return message_map[message_id]
        except KeyError:
            raise discord_not_found() from None

    return AsyncMock(side_effect=fetch_message), message_map


def _make_channel(
        *,
        fake_kind: str,
        channel_id: int = DEFAULT_CHANNEL_ID,
        guild: Any = None,
        name: str = "test-channel",
        messages: Iterable[Any] | Mapping[int, Any] | object = _MISSING,
        history_messages: Iterable[Any] = (),
        **overrides: Any,
) -> SimpleNamespace:
    """Create a text-channel-shaped object with configurable message lookup.

    Passing ``messages`` configures ``fetch_message`` from those records and
    returns ``discord.NotFound`` for an unknown ID.  Omitting ``messages`` makes
    ``fetch_message`` fail immediately if unexpectedly awaited.  An explicit
    ``fetch_message=AsyncMock(...)`` override remains available for unusual
    behavior such as permission errors.
    """
    _reject_id_override("make_channel", overrides)
    fetch_message, message_map = _message_fetch_mock(messages)
    for message in message_map.values():
        _validate_helper_kind(message, "message")
    history_records = list(history_messages)
    for message in history_records:
        _validate_helper_kind(message, "message")

    channel = _namespace(
        {
            "id": channel_id,
            "guild": guild,
            "name": name,
            "mention": f"<#{channel_id}>",
            "fetch_message": fetch_message,
            "history": Mock(
                side_effect=lambda *_args, **_kwargs: _async_items(history_records)
            ),
            "_fake_discord_kind": fake_kind,
            "_fake_messages": list(message_map.values()),
            "_fake_history_messages": history_records,
        },
        overrides,
    )

    # Keep explicitly supplied messages internally consistent with their
    # channel when the test did not already set a different relationship.
    for message in message_map.values():
        _link_relation(message, "channel", channel)
        if guild is not None:
            _link_guild(message, guild)
    for message in history_records:
        _link_relation(message, "channel", channel)
        if guild is not None:
            _link_guild(message, guild)

    if guild is not None:
        _attach_channel(guild, channel)
    return channel


def make_channel(
        *,
        channel_id: int = DEFAULT_CHANNEL_ID,
        guild: Any = None,
        name: str = "test-channel",
        messages: Iterable[Any] | Mapping[int, Any] | object = _MISSING,
        history_messages: Iterable[Any] = (),
        **overrides: Any,
) -> SimpleNamespace:
    """Create a text-channel-shaped object with configurable message lookup."""
    return _make_channel(
        fake_kind="channel",
        channel_id=channel_id,
        guild=guild,
        name=name,
        messages=messages,
        history_messages=history_messages,
        **overrides,
    )


def make_thread(
        *,
        thread_id: int = DEFAULT_THREAD_ID,
        guild: Any = None,
        name: str = "test-thread",
        parent: Any = None,
        archived: bool = False,
        messages: Iterable[Any] | Mapping[int, Any] | object = _MISSING,
        history_messages: Iterable[Any] = (),
        **overrides: Any,
) -> SimpleNamespace:
    """Create a thread-shaped channel using the same lookup behavior."""
    _reject_id_override("make_thread", overrides)
    if parent is not None:
        _validate_helper_kind(parent, "channel")
    parent_guild = getattr(parent, "guild", None)
    guild = _coalesce_same("guild", guild, parent_guild)
    explicit_parent_id = overrides.pop("parent_id", _MISSING)
    if (
            parent is not None
            and explicit_parent_id is not _MISSING
            and explicit_parent_id != parent.id
    ):
        raise ValueError("Thread fake's parent and parent_id override disagree")
    if parent is not None and guild is not None:
        _attach_channel(guild, parent)

    return _make_channel(
        fake_kind="thread",
        channel_id=thread_id,
        guild=guild,
        name=name,
        messages=messages,
        history_messages=history_messages,
        parent=parent,
        parent_id=(
            getattr(parent, "id", None)
            if explicit_parent_id is _MISSING
            else explicit_parent_id
        ),
        archived=archived,
        **overrides,
    )


def _guild_fetch_mock(
        fetched_channels: Iterable[Any] | Mapping[int, Any] | object,
) -> AsyncMock:
    """Build a strict or record-backed guild.fetch_channel mock."""
    if fetched_channels is _MISSING:
        return _strict_async_mock("guild.fetch_channel")

    fetched_channel_map = _objects_by_id(fetched_channels)

    def fetch_channel(channel_id: int) -> Any:
        try:
            return fetched_channel_map[channel_id]
        except KeyError:
            raise discord_not_found(
                message="Unknown Channel",
                code=10003,
            ) from None

    return AsyncMock(side_effect=fetch_channel)


def make_guild(
        *,
        guild_id: int = DEFAULT_GUILD_ID,
        name: str = "Test Guild",
        channels: Iterable[Any] = (),
        categories: Iterable[Any] = (),
        threads: Iterable[Any] = (),
        roles: Iterable[Any] = (),
        members: Iterable[Any] = (),
        text_channels: Iterable[Any] | None = None,
        fetched_channels: Iterable[Any] | Mapping[int, Any] | object = _MISSING,
        **overrides: Any,
) -> SimpleNamespace:
    """Create a guild with live cache lookups and optional API results."""
    _reject_id_override("make_guild", overrides)
    channel_list = list(channels)
    category_list = list(categories)
    all_channel_list = [*channel_list, *category_list]
    thread_list = list(threads)
    role_list = list(roles)
    member_list = list(members)
    text_channel_list = (
        list(channel_list) if text_channels is None else list(text_channels)
    )
    if fetched_channels is _MISSING:
        fetched_channel_map: Mapping[int, Any] | object = _MISSING
    else:
        # Normalize once so generator inputs are not consumed separately while
        # configuring fetch behavior and then linking objects back to the guild.
        fetched_channel_map = _objects_by_id(fetched_channels)

    # Validate every top-level collection before linking any supplied object to
    # the new guild, so a failure cannot leave a partially mutated object graph.
    for obj in channel_list:
        _validate_helper_kind(obj, "channel")
    for obj in category_list:
        _validate_helper_kind(obj, "category")
    for obj in thread_list:
        _validate_helper_kind(obj, "thread")
    for obj in role_list:
        _validate_helper_kind(obj, "role")
    for obj in member_list:
        _validate_helper_kind(obj, "member")
    for obj in text_channel_list:
        _validate_helper_kind(obj, "channel")
        if not any(obj is channel for channel in channel_list):
            raise ValueError(
                "Guild fake text_channels must be an identity subset of channels"
            )
    if fetched_channel_map is not _MISSING:
        for obj in fetched_channel_map.values():
            _validate_helper_kind(obj, {"category", "channel", "thread"})

    # Reject duplicate IDs before the fake's cache methods become ambiguous.
    for objects in (
            all_channel_list,
            thread_list,
            role_list,
            member_list,
            text_channel_list,
    ):
        _objects_by_id(objects)
    if set(_objects_by_id(all_channel_list)) & set(_objects_by_id(thread_list)):
        raise ValueError("A guild channel and thread cannot share the same ID")

    guild: SimpleNamespace

    def get_channel(channel_id: int) -> Any:
        return _find_by_id(guild.channels, channel_id)

    def get_channel_or_thread(channel_id: int) -> Any:
        channel = get_channel(channel_id)
        if channel is not None:
            return channel
        return _find_by_id(guild.threads, channel_id)

    def get_role(role_id: int) -> Any:
        return _find_by_id(guild.roles, role_id)

    def get_member(member_id: int) -> Any:
        return _find_by_id(guild.members, member_id)

    guild = _namespace(
        {
            "id": guild_id,
            "name": name,
            "channels": all_channel_list,
            "categories": category_list,
            "threads": thread_list,
            "text_channels": text_channel_list,
            "roles": role_list,
            "members": member_list,
            "get_channel": Mock(side_effect=get_channel),
            "get_channel_or_thread": Mock(side_effect=get_channel_or_thread),
            "get_role": Mock(side_effect=get_role),
            "get_member": Mock(side_effect=get_member),
            "fetch_channel": _guild_fetch_mock(fetched_channel_map),
            "_fake_discord_kind": "guild",
        },
        overrides,
    )

    # Cached helper-built objects must be placed in the correct collection and
    # all cached objects must form one coherent guild graph.
    for channel in channel_list:
        _attach_channel(guild, channel, register=False)
    for category in category_list:
        _attach_channel(guild, category, register=False)
    for thread in thread_list:
        _attach_channel(guild, thread, register=False)
    for role in role_list:
        _link_guild(role, guild)
    for member in member_list:
        _attach_member(guild, member)

    # API results are kept separate from the cache.  A deliberately foreign
    # fetched channel is allowed so tests can exercise production isolation
    # checks without the factory rewriting that setup.
    if fetched_channel_map is not _MISSING:
        for obj in fetched_channel_map.values():
            _attach_channel(
                guild,
                obj,
                register=False,
                allow_foreign=True,
            )
    return guild


def make_message(
        *,
        message_id: int = DEFAULT_MESSAGE_ID,
        content: str = "",
        author: Any = None,
        channel: Any = None,
        guild: Any = None,
        attachments: Iterable[Any] = (),
        embeds: Iterable[Any] = (),
        created_at: datetime | None = None,
        reference: Any = None,
        **overrides: Any,
) -> SimpleNamespace:
    """Create a message with fresh collections and awaitable common actions."""
    _reject_id_override("make_message", overrides)
    attachment_list = list(attachments)
    for attachment in attachment_list:
        _validate_helper_kind(attachment, "attachment")
    if reference is not None:
        _validate_helper_kind(reference, "message_reference")
    if channel is not None:
        _validate_helper_kind(channel, {"channel", "thread"})
    if author is not None:
        _validate_helper_kind(author, "member")
    guild = _coalesce_same(
        "guild",
        guild,
        getattr(channel, "guild", None),
        getattr(author, "guild", None),
    )
    if guild is None:
        guild = make_guild()

    if channel is None:
        channel = make_channel(guild=guild)
    else:
        _attach_channel(guild, channel)

    if author is None:
        author = make_member(guild=guild)
    else:
        _attach_member(guild, author)

    jump_url = None
    if guild is not None:
        jump_url = (
            f"https://discord.com/channels/{guild.id}/{channel.id}/{message_id}"
        )

    return _namespace(
        {
            "id": message_id,
            "content": content,
            "author": author,
            "channel": channel,
            "guild": guild,
            "attachments": attachment_list,
            "embeds": list(embeds),
            "created_at": created_at or datetime.now(timezone.utc),
            "reference": reference,
            "jump_url": jump_url,
            "delete": AsyncMock(),
            "add_reaction": AsyncMock(),
            "_fake_discord_kind": "message",
        },
        overrides,
    )


def make_context(
        *,
        guild: Any = None,
        channel: Any = None,
        author: Any = None,
        message: Any = None,
        bot: Any = None,
        **overrides: Any,
) -> SimpleNamespace:
    """Create a coherently linked command-context-shaped object."""
    if channel is not None:
        _validate_helper_kind(channel, {"channel", "thread"})
    if author is not None:
        _validate_helper_kind(author, "member")
    if message is not None:
        _validate_helper_kind(message, "message")
    message_channel = getattr(message, "channel", None)
    message_author = getattr(message, "author", None)
    channel = _coalesce_same("channel", channel, message_channel)
    author = _coalesce_same("author", author, message_author)
    guild = _coalesce_same(
        "guild",
        guild,
        getattr(message, "guild", None),
        getattr(channel, "guild", None),
        getattr(author, "guild", None),
    )
    if guild is None:
        guild = make_guild()
    if channel is None:
        channel = make_channel(guild=guild)
    else:
        _attach_channel(guild, channel)
    if author is None:
        author = make_member(guild=guild)
    else:
        _attach_member(guild, author)
    if message is None:
        message = make_message(
            author=author,
            channel=channel,
            guild=guild,
        )
    else:
        _link_relation(message, "guild", guild)
        _link_relation(message, "channel", channel)
        _link_relation(message, "author", author)
    if bot is None:
        bot = make_bot()

    return _namespace(
        {
            "guild": guild,
            "channel": channel,
            "author": author,
            "message": message,
            "bot": bot,
            "send": AsyncMock(),
        },
        overrides,
    )


def make_interaction(
        *,
        guild: Any = None,
        channel: Any = None,
        user: Any = None,
        message: Any = None,
        response: Any = None,
        followup: Any = None,
        **overrides: Any,
) -> SimpleNamespace:
    """Create a fresh interaction with response and follow-up send mocks."""
    if channel is not None:
        _validate_helper_kind(channel, {"channel", "thread"})
    if user is not None:
        _validate_helper_kind(user, "member")
    if message is not None:
        _validate_helper_kind(message, "message")
    message_channel = getattr(message, "channel", None)
    channel = _coalesce_same("channel", channel, message_channel)
    guild = _coalesce_same(
        "guild",
        guild,
        getattr(message, "guild", None),
        getattr(channel, "guild", None),
        getattr(user, "guild", None),
    )
    if guild is None:
        guild = make_guild()
    if channel is None:
        channel = make_channel(guild=guild)
    else:
        _attach_channel(guild, channel)
    if user is None:
        user = make_member(guild=guild)
    else:
        _attach_member(guild, user)
    if message is not None:
        _link_relation(message, "guild", guild)
        _link_relation(message, "channel", channel)
    if response is None:
        response = SimpleNamespace(
            send_message=AsyncMock(),
            defer=AsyncMock(),
            send_modal=AsyncMock(),
        )
    if followup is None:
        followup = SimpleNamespace(send=AsyncMock())

    return _namespace(
        {
            "guild": guild,
            "channel": channel,
            "user": user,
            "message": message,
            "response": response,
            "followup": followup,
            "edit_original_response": AsyncMock(),
            "delete_original_response": AsyncMock(),
        },
        overrides,
    )


__all__ = [
    "DEFAULT_ATTACHMENT_ID",
    "DEFAULT_BOT_ID",
    "DEFAULT_CATEGORY_ID",
    "DEFAULT_CHANNEL_ID",
    "DEFAULT_GUILD_ID",
    "DEFAULT_MEMBER_ID",
    "DEFAULT_MESSAGE_ID",
    "DEFAULT_ROLE_ID",
    "DEFAULT_THREAD_ID",
    "discord_not_found",
    "empty_async_history",
    "make_attachment",
    "make_category",
    "make_channel",
    "make_bot",
    "make_context",
    "make_guild",
    "make_interaction",
    "make_member",
    "make_message",
    "make_message_reference",
    "make_role",
    "make_thread",
]
