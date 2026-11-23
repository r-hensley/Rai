import asyncio
from datetime import timedelta

import discord

from .BotUtils import bot_utils as utils


def recent_role_counts(members, stats) -> dict[int, int] | None:
    """Return counts from the last 30 UTC dates, including today."""
    if not stats.get('enable'):
        return None

    today = discord.utils.utcnow()
    since = (today - timedelta(days=29)).strftime('%Y%m%d')
    until = today.strftime('%Y%m%d')
    member_ids = {str(member.id): member.id for member in members}
    counts = dict.fromkeys(member_ids.values(), 0)
    for day, activity in stats.get('messages', {}).items():
        if since <= day <= until:
            for user_id in member_ids.keys() & activity.keys():
                counts[member_ids[user_id]] += sum(activity[user_id].get('channels', {}).values())
    return counts


class RoleMembersView(utils.RaiView):
    MAX_MEMBERS_PER_PAGE = 20
    MAX_PAGE_TEXT = 700

    def __init__(self, role_name, members, counts, author):
        super().__init__(timeout=60)
        self.title = f"{discord.utils.escape_markdown(role_name)} — {len(members):,} members"
        self.members = sorted(members, key=lambda member: member.name.casefold())
        self.counts = counts
        self.author = author
        self.current_page = 0
        self.message = None
        self.show_nicknames = True
        self.sort_by_count = False
        self.has_nicknames = any(member.nick and member.nick != member.name for member in members)
        self.lock = asyncio.Lock()
        self.embeds = self.build_embeds()
        self.update_menu()

    def build_embeds(self) -> list[discord.Embed]:
        members = self.members
        if self.sort_by_count:
            members = sorted(members, key=lambda member: self.counts[member.id], reverse=True)

        if self.counts is None:
            groups = {'Members': []}
            activity_note = 'Message tracking unavailable'
        else:
            groups = {'11+ messages': [], '1–10 messages': [], '0 messages': []}
            activity_note = 'Tracked messages in the last 30 days'

        for member in members:
            label = discord.utils.escape_markdown(member.name)
            if self.show_nicknames and member.nick and member.nick != member.name:
                nick = discord.utils.escape_markdown(' '.join(member.nick.split()), ignore_links=False)
                label += f" ({discord.utils.escape_mentions(nick)})"

            if self.counts is None:
                group = 'Members'
            else:
                count = self.counts[member.id]
                if count > 10:
                    group = '11+ messages'
                elif count:
                    group = '1–10 messages'
                else:
                    group = '0 messages'
                if self.sort_by_count:
                    label += f" [{count:,}]"
            groups[group].append(label)

        order = 'Most messages first' if self.sort_by_count else 'A–Z'
        footer = f"{activity_note} · {order}"
        page = {}
        pages = [page]
        page_members = 0
        page_text = 0
        separator = ', '
        for heading, labels in groups.items():
            for label in labels:
                label_size = len(label.encode('utf-16-le')) // 2
                cost = label_size + (len(separator) if heading in page else len(heading))
                # Break earlier when long nicknames would wrap onto extra lines.
                if page_members >= self.MAX_MEMBERS_PER_PAGE or page_text + cost > self.MAX_PAGE_TEXT:
                    page = {}
                    pages.append(page)
                    page_members = 0
                    page_text = 0
                    cost = label_size + len(heading)
                page.setdefault(heading, []).append(label)
                page_members += 1
                page_text += cost

        embeds = []
        for index, fields in enumerate(pages, start=1):
            embed = discord.Embed(title=self.title, color=0x00FF00)
            for heading, entries in fields.items():
                embed.add_field(name=heading, value=separator.join(entries), inline=False)
            if not fields:
                embed.description = 'No members.'
            embed.set_footer(text=f"{footer} · Page {index}/{len(pages)}")
            embeds.append(embed)
        return embeds

    def update_menu(self):
        options = []
        if self.current_page > 0:
            options.append(discord.SelectOption(label='Previous page', value='previous'))
        if self.current_page < len(self.embeds) - 1:
            options.append(discord.SelectOption(label='Next page', value='next'))
        if self.has_nicknames:
            label = 'Hide nicknames' if self.show_nicknames else 'Show nicknames'
            options.append(discord.SelectOption(label=label, value='nicknames'))
        if self.counts is not None and self.members:
            label = 'Sort alphabetically' if self.sort_by_count else 'Sort by message count'
            options.append(discord.SelectOption(label=label, value='sort'))
        if options:
            self.actions.options = options
        else:
            self.remove_item(self.actions)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author.id:
            return True
        await interaction.response.send_message('You cannot control this menu.', ephemeral=True)
        return False

    @discord.ui.select(placeholder='Member list options')
    async def actions(self, interaction: discord.Interaction, select: discord.ui.Select):
        action = select.values[0]
        async with self.lock:
            if action == 'previous':
                self.current_page = max(0, self.current_page - 1)
            elif action == 'next':
                self.current_page = min(len(self.embeds) - 1, self.current_page + 1)
            else:
                if action == 'nicknames':
                    self.show_nicknames = not self.show_nicknames
                elif action == 'sort':
                    self.sort_by_count = not self.sort_by_count
                self.current_page = 0
                self.embeds = self.build_embeds()
            self.update_menu()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def on_timeout(self):
        async with self.lock:
            if self.message:
                try:
                    await self.message.edit(view=None)
                except discord.NotFound:
                    pass
