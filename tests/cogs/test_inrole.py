from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from cogs import general
from cogs.utils.role_members import RoleMembersView
from tests.discord_fakes import make_bot, make_context, make_guild, make_member, make_role


@pytest.mark.asyncio
async def test_inrole_groups_members_using_the_last_30_utc_dates(monkeypatch):
    members = [
        make_member(member_id=101, name='zulu', nick='Z, the Third'),
        make_member(member_id=102, name='alpha', nick=None),
        make_member(member_id=103, name='delta', nick=None),
        make_member(member_id=104, name='echo', nick=None),
        make_member(member_id=105, name='unused', nick=None),
    ]
    role = make_role(name='Welcoming Party', members=members)
    guild = make_guild(roles=[role])
    stats = {
        '20261024': {'105': {'channels': {'1': 100}}},
        '20261025': {'103': {'channels': {'1': 3, '2': 7}}},
        '20261123': {
            '101': {'channels': {'1': 20}},
            '102': {'channels': {'1': 11}},
            '104': {'channels': {'1': 1}},
        },
    }
    bot = make_bot(stats={str(guild.id): {'enable': True, 'messages': stats}})
    ctx = make_context(guild=guild, bot=bot)
    cog = general.General(bot)
    sent = AsyncMock()
    monkeypatch.setattr(discord.utils, 'utcnow', lambda: datetime(2026, 11, 23, tzinfo=timezone.utc))
    monkeypatch.setattr(general.utils, 'safe_send', sent)

    await cog.inrole.callback(cog, ctx, role_name='welcoming party')
    embed = sent.call_args.kwargs['embed']
    assert [(field.name, field.value) for field in embed.fields] == [
        ('11+ messages', 'alpha\nzulu (Z, the Third)'),
        ('1–10 messages', 'delta\necho'),
        ('0 messages', 'unused'),
    ]
    assert [option.label for option in sent.call_args.kwargs['view'].actions.options] == [
        'Hide nicknames', 'Sort by message count',
    ]

    await cog.inrole.callback(cog, ctx, role_name=f'<@&{role.id}> --count')
    sent.assert_awaited_with(ctx, '**Welcoming Party** has **5** members.')


@pytest.mark.asyncio
async def test_inrole_menu_updates_pages_and_keeps_long_nicknames_compact():
    members = [
        make_member(member_id=i, name=f'member{i:03}', nick='🌸' * 30)
        for i in range(45)
    ]
    counts = {member.id: member.id + 11 for member in members}
    author = make_member()
    view = RoleMembersView('Welcoming Party', members, counts, author)
    interaction = SimpleNamespace(
        user=author, response=SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock()),
    )

    async def select(value):
        view.actions._refresh_state(interaction, {'values': [value]})
        await view.actions.callback(interaction)
        interaction.response.edit_message.assert_awaited_with(embed=view.embeds[view.current_page], view=view)

    assert await view.interaction_check(interaction)
    await select('next')
    assert view.current_page == 1
    await select('previous')
    assert view.current_page == 0
    await select('next')
    await select('nicknames')
    assert view.current_page == 0
    assert len(view.embeds[0].fields[0].value.splitlines()) == 20
    assert view.embeds[0].fields[0].value.startswith('member000\nmember001\n')
    await select('nicknames')
    assert view.embeds[0].fields[0].value.startswith(f"member000 ({'🌸' * 30})\n")
    await select('sort')
    assert view.embeds[0].fields[0].value.startswith(f"member044 ({'🌸' * 30}) [55]\n")

    all_entries = []
    for embed in view.embeds:
        parts = []
        page_entries = []
        for field in embed.fields:
            parts.extend([field.name, field.value])
            page_entries.extend(entry.split()[0] for entry in field.value.splitlines())
        assert 0 < len(page_entries) < 20
        assert sum(len(part.encode('utf-16-le')) // 2 for part in parts) <= 700
        all_entries.extend(page_entries)
    assert all_entries == [member.name for member in reversed(members)]

    await select('nicknames')
    await select('sort')
    assert view.embeds[0].fields[0].value.startswith('member000\nmember001\n')
    interaction.user = make_member(member_id=999)
    assert not await view.interaction_check(interaction)
    interaction.response.send_message.assert_awaited_once_with('You cannot control this menu.', ephemeral=True)


def test_inrole_handles_disabled_tracking_and_an_empty_role():
    author = make_member()
    member = make_member(name='alpha', nick=None)
    untracked = RoleMembersView('Welcoming Party', [member], None, author)
    assert untracked.embeds[0].fields[0].name == 'Members'
    assert 'Message tracking unavailable' in untracked.embeds[0].footer.text
    assert not untracked.children

    empty = RoleMembersView('Welcoming Party', [], {}, author)
    assert empty.embeds[0].description == 'No members.'
    assert not empty.children
