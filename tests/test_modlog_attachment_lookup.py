from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import cogs.channel_mods as channel_mods
from tests.discord_fakes import (
    discord_not_found,
    make_attachment,
    make_bot,
    make_channel,
    make_context,
    make_guild,
    make_member,
    make_message,
)


@pytest.mark.asyncio
async def test_modlog_refreshes_attachment_from_another_guild(monkeypatch):
    avatar = SimpleNamespace(
        replace=Mock(return_value=SimpleNamespace(url="https://example.com/avatar.png")),
    )
    guild = make_guild(
        guild_id=1,
        fetch_ban=AsyncMock(side_effect=discord_not_found()),
    )
    member = make_member(
        member_id=42,
        guild=guild,
        display_avatar=avatar,
        is_timed_out=Mock(return_value=False),
        timed_out_until=None,
        joined_at=None,
    )
    attachment_url = (
        "https://cdn.discordapp.com/attachments/637275284424359937/"
        "1541090000000000000/evidence.png"
    )
    refreshed_url = f"{attachment_url}?ex=68ae1200&is=68acc080&hm=abc123"
    foreign_guild = make_guild(guild_id=2)
    evidence_channel = make_channel(
        channel_id=637275284424359937,
        guild=foreign_guild,
    )
    evidence_attachment = make_attachment(
        attachment_id=1541090000000000000,
        channel_id=evidence_channel.id,
        filename="evidence.png",
        url=refreshed_url,
    )
    evidence_message = make_message(
        message_id=1541090000000000001,
        channel=evidence_channel,
        guild=foreign_guild,
        attachments=[evidence_attachment],
    )
    evidence_channel._fake_history_messages.append(evidence_message)
    entry = {
        "silent": False,
        "type": "Warning",
        "date": "2026/08/23 07:17 UTC",
        "length": None,
        "reason": f"Test entry\n{attachment_url}",
        "jump_url": None,
    }
    bot = make_bot(
        db={
            "modlog": {str(guild.id): {str(member.id): [entry]}},
            "mutes": {},
            "voice_mutes": {},
            "bans": {},
        },
        stats={},
        fetch_channel=AsyncMock(return_value=evidence_channel),
    )
    ctx = make_context(guild=guild, bot=bot)

    async def convert_member(_ctx, _id_in):
        return member

    async def no_activity(*_args):
        return False

    monkeypatch.setattr(channel_mods.utils, "member_converter", convert_member)
    monkeypatch.setattr(channel_mods.hf, "excessive_dm_activity", no_activity)
    monkeypatch.setattr(channel_mods.hf, "suspected_spam_activity_flag", no_activity)

    cog = channel_mods.ChannelMods(bot)
    embed = await cog.modlog.callback(cog, ctx, str(member.id), post_embed=False)

    bot.fetch_channel.assert_awaited_once_with(637275284424359937)
    guild.fetch_channel.assert_not_awaited()
    assert refreshed_url in embed.fields[0].value
