"""Contract tests for the reusable Discord fake-object factories."""

from types import SimpleNamespace

import discord
import pytest

from tests.discord_fakes import (
    discord_not_found,
    empty_async_history,
    make_attachment,
    make_bot,
    make_category,
    make_channel,
    make_context,
    make_guild,
    make_interaction,
    make_member,
    make_message,
    make_message_reference,
    make_role,
    make_thread,
)


@pytest.mark.asyncio
async def test_factories_return_fresh_mutable_values_and_mocks():
    first = make_message()
    second = make_message()

    first.attachments.append(object())
    await first.delete("unused")

    assert second.attachments == []
    assert first.attachments is not second.attachments
    assert first.delete is not second.delete
    assert second.delete.call_count == 0


def test_bot_factories_have_fresh_state_and_cache_lookups():
    guild = make_guild(guild_id=1)
    channel = make_channel(channel_id=10, guild=guild)
    first = make_bot(guilds=[guild], channels=[channel])
    second = make_bot()

    first.db["changed"] = True
    first.profiling_decorators.add("cogs.message")

    assert first.get_guild(guild.id) is guild
    assert first.get_channel(channel.id) is channel
    assert second.db == {}
    assert second.profiling_decorators == set()


def test_bot_cache_lookups_follow_later_guild_and_channel_registration():
    bot = make_bot()
    guild = make_guild(guild_id=1)
    bot.guilds.append(guild)
    channel = make_channel(channel_id=10, guild=guild)

    assert bot.get_guild(guild.id) is guild
    assert bot.get_channel(channel.id) is channel


def test_guild_wires_cache_objects_and_preserves_explicit_foreign_guild():
    channel = make_channel(channel_id=10)
    thread = make_thread(thread_id=20)
    role = make_role(role_id=30)
    member = make_member(member_id=40)
    foreign_guild = make_guild(guild_id=99)
    foreign_thread = make_thread(thread_id=50, guild=foreign_guild)

    guild = make_guild(
        guild_id=1,
        channels=[channel],
        threads=[thread],
        roles=[role],
        members=[member],
        fetched_channels=[foreign_thread],
    )

    assert guild.get_channel(10) is channel
    assert guild.get_channel(20) is None
    assert guild.get_channel_or_thread(20) is thread
    assert guild.get_role(30) is role
    assert guild.get_member(40) is member
    assert channel.guild is guild
    assert thread.guild is guild
    assert role.guild is guild
    assert member.guild is guild
    assert foreign_thread.guild is foreign_guild


def test_objects_created_with_a_helper_guild_join_its_live_lookups():
    # Even an explicitly empty immutable input is normalized to the mutable
    # list needed when later helper-built channels register themselves.
    guild = make_guild(guild_id=1, text_channels=())
    channel = make_channel(channel_id=10, guild=guild)
    thread = make_thread(thread_id=20, guild=guild)
    role = make_role(role_id=30, guild=guild)
    member = make_member(member_id=40, guild=guild)
    category = make_category(category_id=50, guild=guild)

    assert guild.get_channel(10) is channel
    assert guild.get_channel_or_thread(20) is thread
    assert guild.get_role(30) is role
    assert guild.get_member(40) is member
    assert guild.text_channels == [channel]
    assert guild.get_channel(50) is category
    assert guild.categories == [category]


@pytest.mark.asyncio
async def test_guild_fetch_channel_uses_separate_uncached_records():
    uncached_thread = make_thread(thread_id=20)
    guild = make_guild(guild_id=1, fetched_channels=[uncached_thread])

    assert guild.get_channel_or_thread(20) is None
    assert await guild.fetch_channel(20) is uncached_thread
    assert uncached_thread.guild is guild

    with pytest.raises(discord.NotFound):
        await guild.fetch_channel(21)


def test_fetched_channel_propagates_guild_to_its_messages():
    message = SimpleNamespace(id=40, channel=None, guild=None)
    uncached_channel = make_channel(channel_id=20, messages=[message])

    guild = make_guild(guild_id=1, fetched_channels=[uncached_channel])

    assert message.guild is guild


@pytest.mark.asyncio
async def test_channel_fetch_message_uses_configured_records():
    message = SimpleNamespace(id=40, channel=None, guild=None)
    channel = make_channel(channel_id=20, messages=[message])

    assert await channel.fetch_message(40) is message
    assert message.channel is channel

    with pytest.raises(discord.NotFound):
        await channel.fetch_message(41)


def test_later_guild_link_propagates_to_configured_channel_messages():
    message = SimpleNamespace(id=40, channel=None, guild=None)
    channel = make_channel(channel_id=20, messages=[message])

    guild = make_guild(guild_id=1, channels=[channel])

    assert message.channel is channel
    assert message.guild is guild


@pytest.mark.asyncio
async def test_history_records_are_linked_to_their_channel_and_later_guild():
    message = SimpleNamespace(id=40, channel=None, guild=None)
    channel = make_channel(channel_id=20, history_messages=[message])
    guild = make_guild(guild_id=1, channels=[channel])

    history = [record async for record in channel.history(limit=1)]

    assert history == [message]
    assert message.channel is channel
    assert message.guild is guild


def test_composite_attachment_propagates_to_nested_messages_and_roles():
    guild = make_guild(guild_id=1)
    fetched_message = SimpleNamespace(id=40, channel=None, guild=None)
    channel = make_channel(channel_id=20, messages=[fetched_message])
    role = make_role(role_id=30)
    member = make_member(member_id=50, roles=[role])

    make_message(guild=guild, channel=channel, author=member)

    assert fetched_message.guild is guild
    assert role.guild is guild


def test_channel_rejects_a_message_linked_to_a_different_channel():
    first_channel = make_channel(channel_id=10)
    message = SimpleNamespace(id=40, channel=first_channel, guild=None)

    with pytest.raises(ValueError, match="channel"):
        make_channel(channel_id=20, messages=[message])


@pytest.mark.asyncio
async def test_unconfigured_api_fetches_fail_loudly():
    guild = make_guild()
    channel = make_channel()

    with pytest.raises(AssertionError, match="guild.fetch_channel"):
        await guild.fetch_channel(123)
    with pytest.raises(AssertionError, match="channel.fetch_message"):
        await channel.fetch_message(456)


def test_context_builds_a_consistent_fresh_object_graph():
    ctx = make_context()

    assert ctx.channel.guild is ctx.guild
    assert ctx.author.guild is ctx.guild
    assert ctx.message.guild is ctx.guild
    assert ctx.message.channel is ctx.channel
    assert ctx.message.author is ctx.author


def test_context_derives_existing_message_relationships():
    message = make_message()

    ctx = make_context(message=message)

    assert ctx.guild is message.guild
    assert ctx.channel is message.channel
    assert ctx.author is message.author


def test_factories_reject_contradictory_relationships_and_id_aliases():
    first_guild = make_guild(guild_id=1)
    second_guild = make_guild(guild_id=2)
    channel = make_channel(guild=first_guild)

    with pytest.raises(ValueError, match="Conflicting guild"):
        make_message(guild=second_guild, channel=channel)
    with pytest.raises(TypeError, match="channel_id"):
        make_channel(id=123)
    with pytest.raises(TypeError, match="reserved"):
        make_channel(_fake_discord_kind="thread")


def test_record_backed_fetches_reject_duplicate_ids():
    first = SimpleNamespace(id=40, channel=None, guild=None)
    second = SimpleNamespace(id=40, channel=None, guild=None)

    with pytest.raises(ValueError, match="Duplicate Discord fake ID"):
        make_channel(messages=[first, second])


def test_guild_rejects_helper_objects_in_the_wrong_cache_collection():
    channel = make_channel(channel_id=10)
    thread = make_thread(thread_id=20)

    with pytest.raises(ValueError, match="Expected a channel fake"):
        make_guild(channels=[channel, thread])
    assert channel.guild is None


def test_guild_rejects_text_channels_outside_its_channel_cache():
    channel = make_channel(channel_id=10)

    with pytest.raises(ValueError, match="identity subset"):
        make_guild(text_channels=[channel])

    assert channel.guild is None


def test_typed_factory_arguments_reject_the_wrong_helper_kind():
    channel = make_channel(channel_id=10)
    member = make_member(member_id=20)

    with pytest.raises(ValueError, match="Expected a role fake"):
        make_member(roles=[channel])
    with pytest.raises(
            ValueError,
            match="Expected a category or channel or thread fake",
    ):
        make_guild(fetched_channels=[member])


def test_thread_derives_its_guild_from_parent():
    guild = make_guild(guild_id=1)
    parent = make_channel(channel_id=10)

    thread = make_thread(thread_id=20, guild=guild, parent=parent)

    assert thread.guild is guild
    assert parent.guild is guild
    assert thread.parent is parent
    assert guild.get_channel(parent.id) is parent
    assert guild.get_channel_or_thread(thread.id) is thread


def test_later_guild_attachment_also_registers_a_thread_parent():
    parent = make_channel(channel_id=10)
    thread = make_thread(thread_id=20, parent=parent)

    guild = make_guild(guild_id=1, threads=[thread])

    assert parent.guild is guild
    assert thread.guild is guild
    assert guild.get_channel(parent.id) is parent


def test_thread_accepts_an_explicit_parent_id_that_matches_parent():
    parent = make_channel(channel_id=10)

    thread = make_thread(thread_id=20, parent=parent, parent_id=10)

    assert thread.parent is parent
    assert thread.parent_id == 10


def test_member_roles_share_and_register_with_the_member_guild():
    guild = make_guild(guild_id=1)
    role = make_role(role_id=30)

    member = make_member(member_id=40, guild=guild, roles=[role])

    assert role.guild is guild
    assert guild.get_role(role.id) is role
    assert guild.get_member(member.id) is member


@pytest.mark.asyncio
async def test_interactions_do_not_share_response_or_followup_mocks():
    first = make_interaction()
    second = make_interaction()

    await first.response.send_message("unused")
    await first.followup.send("unused")

    assert first.response is not second.response
    assert first.followup is not second.followup
    assert second.response.send_message.call_count == 0
    assert second.followup.send.call_count == 0
    assert hasattr(first.response, "send_modal")
    assert hasattr(first, "edit_original_response")


@pytest.mark.asyncio
async def test_attachment_and_reference_factories_model_nested_message_records():
    attachment = make_attachment(filename="traceback.txt", data=b"details")
    referenced_message = make_message(message_id=40, attachments=[attachment])
    reference = make_message_reference(resolved=referenced_message)
    message = make_message(reference=reference)

    assert await attachment.read() == b"details"
    assert attachment.size == len(b"details")
    assert message.reference.resolved is referenced_message
    assert reference.message_id == referenced_message.id
    assert reference.channel_id == referenced_message.channel.id
    assert reference.guild_id == referenced_message.guild.id


def test_entity_equality_uses_kind_and_id_without_walking_cyclic_graphs():
    first = make_message(message_id=40)
    same_snowflake = make_message(message_id=40)
    different = make_message(message_id=41)

    assert first == same_snowflake
    assert first != different
    assert hash(first) == hash(same_snowflake)


@pytest.mark.asyncio
async def test_not_found_and_empty_history_match_discord_shapes():
    error = discord_not_found()
    history_items = [item async for item in empty_async_history(limit=1)]

    assert isinstance(error, discord.NotFound)
    assert error.status == 404
    assert error.code == 10008
    assert history_items == []
