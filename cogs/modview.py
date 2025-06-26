import copy
from datetime import datetime
import discord
from discord.ext import commands

import cogs.channel_mods as cm
from cogs.utils import modlog_utils as mlu
from cogs.utils.BotUtils import bot_utils as utils


class ModView(discord.ui.View):
    def __init__(self, cog: "cm", manage_cog: "UserManage", ctx: commands.Context, id_arg: str):
        super().__init__()
        self.manage_cog = manage_cog
        self.cog = cog
        self.ctx = ctx
        self.author_id = ctx.author.id
        self.member, self.user, self.user_id = None, None, None
        self.id_arg = id_arg

    async def init(self):
        self.member, self.user, self.user_id = await mlu.resolve_user(
            self.ctx, self.id_arg, self.cog.bot)

    # @discord.ui.button(label="Open log", style=discord.ButtonStyle.primary)
    # async def modlog_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     if interaction.user.id != self.author_id:
    #         await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
    #         return
    #     await interaction.response.defer(ephemeral=True)
    #     _member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.cog.bot)
    #     embed = await mlu.build_modlog_embed(self.cog.bot, self.ctx, user)

    #     # Replace the current message
    #     view = ModLogView(self)
    #     await interaction.message.edit(embed=embed, view=view)
    @discord.ui.button(label="Open log", style=discord.ButtonStyle.primary)
    async def modlog_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Resolve the user and their log
        entries = await mlu.get_modlog_entries(self.ctx.guild.id, self.user_id, self.cog.bot)

        embed = await mlu.build_modlog_embed(self.cog.bot, self.ctx, self.user)

        # Pass entries and user to the view
        view = PaginatedModLogView(self, entries=entries)
        await interaction.message.edit(embed=embed, view=view)

    @discord.ui.button(label="Mute", style=discord.ButtonStyle.secondary)
    async def mute_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Build a fake message that simulates the command call
        fake_message = copy.copy(interaction.message)
        fake_message.author = interaction.user
        fake_message.content = f"{self.ctx.prefix}mute {self.user_id}"

        ctx = await self.cog.bot.get_context(fake_message)
        await self.cog.bot.invoke(ctx)

    # @discord.ui.button(label="Ban", style=discord.ButtonStyle.red)
    # async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     if interaction.user.id != self.author_id:
    #         await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
    #         return
    #     await interaction.response.defer(ephemeral=True)
    #     _member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.cog.bot)
    #     embed = await mlu.build_modlog_embed(self.cog.bot, self.ctx, user)

    #     # Replace the current message
    #     view = BanView(self)
    #     await interaction.message.edit(embed=embed, view=view)

    @discord.ui.button(label="Warn", style=discord.ButtonStyle.blurple)
    async def warn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Build a fake message that simulates the command call
        fake_message = copy.copy(interaction.message)
        fake_message.author = interaction.user
        fake_message.content = f"{self.ctx.prefix}warn {self.user_id}"

        ctx = await self.cog.bot.get_context(fake_message)
        await self.cog.bot.invoke(ctx)

    # async def on_timeout(self, interaction: discord.Interaction) -> None:
    #     if interaction.message:
    #         try:
    #             # Remove all buttons after timeout
    #             await interaction.message.edit(view=None)
    #         except discord.NotFound:
    #             pass
    #     self.stop()


# class ModLogView(discord.ui.View):
#     def __init__(self, parent_view: "ModView"):
#         super().__init__()
#         self.ctx = parent_view.ctx
#         self.user_id = parent_view.id_arg
#         self.author_id = parent_view.author_id
#         self.manage_cog = parent_view.manage_cog

#     @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary)
#     async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user.id != self.author_id:
#             await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
#             return

#         await interaction.response.defer()

#         # Resolve user again
#         member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.manage_cog.bot)
#         embed = await mlu.build_user_summary_embed(self.manage_cog.bot, self.ctx, user_id, member, user)

#         # Recreate the original ModView
#         mod_cog = self.ctx.bot.get_cog("ChannelMods")
#         view = ModView(self.manage_cog, mod_cog, self.ctx, user_id)
#         await interaction.message.edit(embed=embed, view=view)

#     @discord.ui.button(label="➕ Add Entry", style=discord.ButtonStyle.success)
#     async def add_entry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user.id != self.author_id:
#             await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
#             return

#         await interaction.response.send_modal(AddModlogEntryModal(self, "Silent Log"))

class PaginatedModLogView(discord.ui.View):
    def __init__(self, parent_view: "ModView", entries: list[dict], page: int = 0):
        super().__init__(timeout=180)
        self.ctx = parent_view.ctx
        self.user = parent_view.user
        self.member = parent_view.member
        self.user_id = parent_view.user_id
        self.author_id = parent_view.author_id
        self.manage_cog = parent_view.manage_cog
        self.entries = entries
        self.page = page
        self.max_per_page = 5
        self.selector = None

        self.total_pages = (len(entries) - 1) // self.max_per_page + 1
        self.update_children()

    def update_children(self):
        # self.clear_items()
        # If selector already exists, remove it
        if self.selector:
            self.remove_item(self.selector)
            self.selector = None

        start = self.page * self.max_per_page
        end = start + self.max_per_page
        page_entries = self.entries[start:end]

        # options = []
        # for i, entry in enumerate(page_entries, start=start):
        #     label = f"[{entry.get('type', 'Unknown')}] {entry.get('reason', '')[:80]}"
        #     options.append(discord.SelectOption(
        #         label=label, value=str(i), description=entry.get('date', '')))

        # self.add_item(LogEntrySelector(options, self))

        options = [
            discord.SelectOption(
                label=f"{i+1} [{entry.get('type', 'Unknown')}] {entry.get('reason', '')[:80]}",
                value=str(i),
                description=entry.get('date', '')
            )
            for i, entry in enumerate(page_entries, start=start)
        ]
        self.selector = LogEntrySelector(options, self)
        self.add_item(self.selector)

        # Conditionally add buttons
        # if self.page > 0:
        #     self.add_item(self.previous_button)
        # if self.page < self.total_pages - 1:
        #     self.add_item(self.next_button)

        # self.add_item(self.back_button)
        # self.add_item(self.add_entry_button)
        self.previous_button.disabled = (self.page == 0)
        self.next_button.disabled = (self.page == self.total_pages - 1)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer()
        embed = await mlu.build_user_summary_embed(self.manage_cog.bot, self.ctx, self.member, self.user)

        # Recreate the original ModView
        mod_cog = self.ctx.bot.get_cog("ChannelMods")
        view = ModView(mod_cog, self.manage_cog, self.ctx, self.user_id)
        await view.init()
        await interaction.message.edit(embed=embed, view=view)

    @discord.ui.button(label="➕ Add Entry", style=discord.ButtonStyle.success, row=1)
    async def add_entry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.send_modal(AddModlogEntryModal(self, "Silent Log"))

    @discord.ui.button(label="< Previous", style=discord.ButtonStyle.secondary, custom_id="prev", row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 You can’t do that.", ephemeral=True)
            return
        self.page -= 1
        self.update_children()
        embed = await mlu.build_modlog_embed(self.ctx.bot, self.ctx, self.user, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next >", style=discord.ButtonStyle.secondary, custom_id="next", row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        self.page += 1
        self.update_children()
        embed = await mlu.build_modlog_embed(self.ctx.bot, self.ctx, self.user, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can interact.", ephemeral=True)
            return False
        return True

    async def interaction_dispatch(self, interaction: discord.Interaction):
        cid = interaction.data.get("custom_id")
        if cid == "prev":
            self.page -= 1
        elif cid == "next":
            self.page += 1

        self.update_children()
        embed = await mlu.build_modlog_embed(self.ctx.bot, self.ctx, self.user, self.page)
        await interaction.response.edit_message(embed=embed, view=self)


class LogEntrySelector(discord.ui.Select):
    def __init__(self, options: list[discord.SelectOption], view: PaginatedModLogView):
        super().__init__(placeholder="Select a log entry",
                         min_values=1, max_values=1, options=options)
        self.parent_view = view
        self.user = view.user

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        entry = self.parent_view.entries[index]

        embed = mlu.build_log_entry_embed(entry, self.user, index)
        await interaction.response.edit_message(embed=embed, view=DetailedEntryView(self.parent_view, entry, index))


class DetailedEntryView(discord.ui.View):
    def __init__(self, paginated_view: PaginatedModLogView, entry: dict, index: int):
        super().__init__(timeout=180)
        self.parent_view = paginated_view
        self.ctx = paginated_view.ctx
        self.entry = entry
        self.index = index
        self.user = paginated_view.user
        self.user_id = paginated_view.user_id
        self.author_id = paginated_view.author_id
        self.manage_cog = paginated_view.manage_cog

    @discord.ui.button(label="✏ Edit", style=discord.ButtonStyle.blurple)
    async def edit_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditModlogEntryModal(self, self.index, self.entry))

    @discord.ui.button(label="🗑 Delete", style=discord.ButtonStyle.red)
    async def delete_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(self.ctx.guild.id)
        del self.ctx.bot.db["modlog"][guild_id][self.user_id][self.index]
        await interaction.response.send_message("✅ Entry deleted.", ephemeral=True)
        embed = await mlu.build_modlog_embed(self.ctx.bot, self.ctx, self.user)
        await interaction.message.edit(embed=embed, view=PaginatedModLogView(self.parent_view, self.parent_view.entries, self.user))

    @discord.ui.button(label="← Back to Log", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await mlu.build_modlog_embed(self.ctx.bot, self.ctx, self.user)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class EditModlogEntryModal(discord.ui.Modal, title="Edit Modlog Entry"):
    def __init__(self, view: discord.ui.View, entry_index: int, entry_data: dict):
        super().__init__()
        self.view = view
        self.entry_index = entry_index
        self.entry_data = entry_data

        # Pre-fill fields with current data
        self.reason = discord.ui.TextInput(
            label="Reason",
            default=entry_data.get("reason", ""),
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1024
        )

        self.duration = discord.ui.TextInput(
            label="Duration (optional, e.g. 1d2h)",
            default=entry_data.get("length") or "",
            required=False,
            max_length=32
        )

        self.add_item(self.reason)
        self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = self.view.ctx
        user_id = str(self.view.user_id)
        guild_id = str(ctx.guild.id)
        bot = self.view.manage_cog.bot

        # Update the entry in the bot's DB
        try:
            db_entries = bot.db["modlog"][guild_id][user_id]
            entry = db_entries[self.entry_index]

            entry["reason"] = self.reason.value
            entry["length"] = self.duration.value if self.duration.value else None
            entry["date_edited"] = datetime.utcnow().strftime(
                "%Y/%m/%d %H:%M UTC")
            await interaction.response.defer()
            user = await bot.fetch_user(int(user_id))
            entries = bot.db["modlog"][guild_id][user_id]

            embed = await mlu.build_modlog_embed(bot, ctx, user)
            new_view = PaginatedModLogView(
                self.view.parent_view, entries, user)

            await interaction.message.edit(embed=embed, view=new_view)
            await interaction.response.send_message("✅ Entry edited!", ephemeral=True)
        except (IndexError, KeyError):
            await interaction.response.send_message("⚠️ Could not update log entry — it may have been deleted.", ephemeral=True)
            return

        # Confirm


# class BanView(discord.ui.View):
#     def __init__(self, parent_view: "ModView"):
#         super().__init__()
#         self.ctx = parent_view.ctx
#         self.user_id = parent_view.id_arg
#         self.author_id = parent_view.author_id
#         self.manage_cog = parent_view.manage_cog

#     @discord.ui.button(label="Ban (hacked)", style=discord.ButtonStyle.success)
#     async def ban_hacked(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user.id != self.author_id:
#             await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
#             return

#         await interaction.response.defer()

#         # Resolve user again
#         member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.manage_cog.bot)
#         embed = await mlu.build_user_summary_embed(self.manage_cog.bot, self.ctx, user_id, member, user)

#         # Recreate the original ModView
#         _mod_cog = self.ctx.bot.get_cog("ChannelMods")
#         view = BanConfirmationView(self)
#         await interaction.message.edit(embed=embed, view=view)

#     @discord.ui.button(label="Ban (minor)", style=discord.ButtonStyle.success)
#     async def ban_minor(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user.id != self.author_id:
#             await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
#             return

#         await interaction.response.defer()

#         # Resolve user again
#         member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.manage_cog.bot)
#         embed = await mlu.build_user_summary_embed(self.manage_cog.bot, self.ctx, user_id, member, user)

#         # Recreate the original ModView
#         _mod_cog = self.ctx.bot.get_cog("ChannelMods")
#         view = BanConfirmationView(self)
#         await interaction.message.edit(embed=embed, view=view)

#     @discord.ui.button(label="Ban (hate)", style=discord.ButtonStyle.success)
#     async def ban_hate(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user.id != self.author_id:
#             await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
#             return

#         await interaction.response.defer()

#         # Resolve user again
#         member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.manage_cog.bot)
#         embed = await mlu.build_user_summary_embed(self.manage_cog.bot, self.ctx, user_id, member, user)

#         # Recreate the original ModView
#         _mod_cog = self.ctx.bot.get_cog("ChannelMods")
#         view = BanConfirmationView(self)
#         await interaction.message.edit(embed=embed, view=view)

#     @discord.ui.button(label="Ban (add reason)", style=discord.ButtonStyle.success)
#     async def ban_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
#         if interaction.user.id != self.author_id:
#             await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
#             return

#         await interaction.response.send_modal(AddModlogEntryModal(self, "Ban"))


class BanConfirmationView(discord.ui.View):
    def __init__(self, parent_view: "ModView"):
        super().__init__()
        self.ctx = parent_view.ctx
        self.user_id = parent_view.id_arg
        self.author_id = parent_view.author_id
        self.manage_cog = parent_view.manage_cog


class AddModlogEntryModal(discord.ui.Modal, title="Add Modlog Entry"):
    def __init__(self, view: PaginatedModLogView, entry_type):
        super().__init__()
        self.view = view

        self.entry_type = entry_type
        self.reason = discord.ui.TextInput(
            label="Reason",
            placeholder="Reason for the entry...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1024
        )
        self.duration = discord.ui.TextInput(
            label="Duration (optional, e.g. 1d2h)",
            required=False,
            max_length=32
        )

        self.add_item(self.reason)
        self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction):
        # Insert into modlog DB
        ctx = self.view.ctx
        user_id = self.view.user_id
        guild_id = str(ctx.guild.id)
        bot = self.view.manage_cog.bot

        # Ensure modlog DB is set up
        if guild_id not in bot.db["modlog"]:
            bot.db["modlog"][guild_id] = {}

        if user_id not in bot.db["modlog"][guild_id]:
            bot.db["modlog"][guild_id][user_id] = []

        new_entry = {
            "type": self.entry_type,
            "reason": self.reason.value,
            "length": self.duration.value if self.duration.value else None,
            "jump_url": None,
            "silent": False,
            "date": datetime.utcnow().strftime("%Y/%m/%d %H:%M UTC")
        }

        bot.db["modlog"][guild_id][user_id].append(new_entry)

        # Confirm to user
        await interaction.response.send_message("✅ Entry added!", ephemeral=True)

        # Refresh the modlog embed
        entries = bot.db["modlog"][guild_id][user_id]
        embed = await mlu.build_modlog_embed(bot, ctx, self.view.user)
        new_view = PaginatedModLogView(self.view, entries, self.view.user)
        await interaction.message.edit(embed=embed, view=new_view)


class UserManage(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    @commands.group(aliases=['manage', 'um'], invoke_without_command=True)
    async def user_manage(self, ctx: commands.Context, *, id_arg: str):
        member, user, user_id = await mlu.resolve_user(ctx, id_arg, self.bot)

        if not user:
            emb = utils.red_embed("")
            emb.set_author(name="COULD NOT FIND USER")
            await utils.safe_send(ctx, embed=emb)
            return

        # Build detailed user summary embed
        embed = await mlu.build_user_summary_embed(self.bot, ctx, member, user)
        mod_cog = ctx.bot.get_cog("ChannelMods")
        # Create interactive button view
        view = ModView(mod_cog, self, ctx, user_id)
        await view.init()

        await utils.safe_send(ctx, embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(UserManage(bot))
