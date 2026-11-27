from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs.interactions import Interactions, commands
from tests.discord_fakes import make_interaction, make_member


@pytest.mark.asyncio
@pytest.mark.parametrize("has_embed", [True, False])
async def test_context_view_modlog_defers_privately_before_loading_modlog(monkeypatch, has_embed):
    interaction = make_interaction()
    member = make_member(member_id=42, guild=interaction.guild)
    command = object()
    embed = discord.Embed(title="Modlog") if has_embed else None
    ctx = Mock(invoke=AsyncMock(return_value=embed))

    async def from_interaction(value):
        assert value is interaction
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        return ctx

    monkeypatch.setattr(commands.Context, "from_interaction", from_interaction)
    cog = Interactions.__new__(Interactions)
    cog.bot = Mock()
    cog.bot.get_command.return_value = command

    await cog.context_view_modlog(interaction, member)

    ctx.invoke.assert_awaited_once_with(command, "42", post_embed=False)
    if has_embed:
        interaction.edit_original_response.assert_awaited_once_with(embed=embed)
    else:
        interaction.edit_original_response.assert_awaited_once_with(content="No modlog available for this member.")
    interaction.response.send_message.assert_not_awaited()
