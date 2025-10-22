# pylint: disable=C0301,C0116,C0115,C0114
import copy
from typing import Optional, Union
from datetime import datetime, timezone
import discord
from discord import app_commands, Interaction
from discord.ext import commands

import cogs.channel_mods as cm
from cogs.utils import modlog_utils as mlu
from cogs.utils.BotUtils import bot_utils as utils


class ModView(discord.ui.View):
    def __init__(self, parent_cog: "cm.ChannelMods", manage_cog: "UserManage", ctx_or_interaction: Union[commands.Context, discord.Interaction], id_arg: str):
        super().__init__(timeout=30)
        self.cog: commands.Cog = parent_cog
        self.manage_cog = manage_cog
        self.ctx = ctx_or_interaction
        self.id_arg = id_arg
        # Initialize author_id and bot from the context or interaction
        self.author_id = mlu.get_author_id(ctx_or_interaction)
        self.bot = mlu.get_bot(ctx_or_interaction)
        self.message: Optional[discord.Message] = None
        self.user_profile: Optional[mlu.UserProfile] = None

    async def init(self):
        # Use UserProfile instead of direct resolution
        self.user_profile = await mlu.UserProfile.create(self.bot, self.ctx, self.id_arg)
        if not self.user_profile:
            raise ValueError("Could not resolve user")

    @property
    def member(self):
        return self.user_profile.member if self.user_profile else None
    
    @property
    def user(self):
        return self.user_profile.user if self.user_profile else None
    
    @property
    def user_id(self):
        return self.user_profile.user_id if self.user_profile else None

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass

    @discord.ui.button(label="Open log", style=discord.ButtonStyle.primary)
    async def modlog_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Use UserProfile to get modlog entries
        entries = await self.user_profile.get_modlog_entries()
        embed, total_pages = await self.user_profile.build_modlog_embed()

        # Pass entries and user to the view
        view = PaginatedModLogView(
            self, entries=entries, page=total_pages)
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Mute", style=discord.ButtonStyle.secondary)
    async def mute_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # # Build a fake message that simulates the command call
        # fake_message = copy.copy(interaction.message)
        # fake_message.author = interaction.user
        # fake_message.content = f"{self.ctx.prefix}mute {self.user_id}"

        # ctx = await self.bot.get_context(fake_message)
        # await self.bot.invoke(ctx)
        embed = utils.green_embed("")
        if not embed.description:
            embed.description = "This will mute the user"
        view = MuteConfirmationView(self)
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

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
    async def warn_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Build a fake message that simulates the command call
        fake_message = copy.copy(interaction.message)
        fake_message.author = interaction.user
        fake_message.content = f"{self.ctx.prefix}warn {self.user_id}"

        ctx = await self.cog.bot.get_context(fake_message)
        await self.bot.invoke(ctx)


class PaginatedModLogView(discord.ui.View):
    def __init__(self, parent_view: "ModView", entries: list[mlu.ModLogEntry], page: int = 0):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.entries = entries
        self.page = page
        # Initialize context and bot from the parent view
        self.ctx = parent_view.ctx
        self.bot = parent_view.bot
        self.user_profile = parent_view.user_profile
        self.author_id = parent_view.author_id
        self.manage_cog = parent_view.manage_cog

        self.max_per_page = 5
        self.selector = None
        self.message: Optional[discord.Message] = None

        self.total_pages = (len(entries) - 1) // self.max_per_page + 1
        self.update_children()

    def update_children(self):
        if self.selector:
            self.remove_item(self.selector)
            self.selector = None

        start = self.page * self.max_per_page
        end = start + self.max_per_page
        page_entries = self.entries[start:end]

        options = [
            discord.SelectOption(
                label=f"{i+1} [{entry.type}] {entry.reason[:80]}",
                value=str(i),
                description=f"<t:{entry.date}:f>"
            )
            for i, entry in enumerate(page_entries, start=start)
        ]
        if options:
            self.selector = LogEntrySelector(options, self)
            self.add_item(self.selector)
            self.previous_button.disabled = self.page == 0
            self.first_button.disabled = self.page == 0
            self.next_button.disabled = self.page == self.total_pages - 1
            self.last_button.disabled = self.page == self.total_pages - 1
        else:
            self.clear_items()
            self.add_item(self.back_button)
            self.add_item(self.add_entry_button)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.NotFound:
                pass

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer()
        embed = await self.user_profile.build_summary_embed()

        # Recreate the original ModView
        mod_cog = self.bot.get_cog("ChannelMods")
        view = ModView(mod_cog, self.manage_cog, self.ctx, self.user_profile.user_id)
        await view.init()
        view.message = interaction.message
        await interaction.edit_original_response(embed=embed, view=view)

    @discord.ui.button(label="➕ Add Entry", style=discord.ButtonStyle.success, row=1)
    async def add_entry_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.send_modal(AddModlogEntryModal(self, "Log"))

    @discord.ui.button(label="<< First", style=discord.ButtonStyle.secondary, custom_id="first", row=0)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 You can’t do that.", ephemeral=True)
            return
        self.page = 0
        self.update_children()
        embed, _ = await self.user_profile.build_modlog_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="< Previous", style=discord.ButtonStyle.secondary, custom_id="prev", row=0)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 You can’t do that.", ephemeral=True)
            return
        self.page -= 1
        self.update_children()
        embed, _ = await self.user_profile.build_modlog_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next >", style=discord.ButtonStyle.secondary, custom_id="next", row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        self.page += 1
        self.update_children()
        embed, _ = await self.user_profile.build_modlog_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Last >>", style=discord.ButtonStyle.secondary, custom_id="last", row=0)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        self.page = self.total_pages-1
        self.update_children()
        embed, _ = await self.user_profile.build_modlog_embed(self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:  # pylint: disable=W0221
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can interact.", ephemeral=True)
            return False
        return True


class LogEntrySelector(discord.ui.Select):
    def __init__(self, options: list[discord.SelectOption], view: PaginatedModLogView):
        super().__init__(placeholder="Select a log entry",
                         min_values=1, max_values=1, options=options)
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        entry = self.parent_view.entries[index]

        embed = entry.build_embed(self.parent_view.user_profile.user, index=index)
        await interaction.response.edit_message(embed=embed, view=DetailedEntryView(self.parent_view, entry, index))


class DetailedEntryView(discord.ui.View):
    def __init__(self, paginated_view: PaginatedModLogView, entry: mlu.ModLogEntry, index: int):
        super().__init__(timeout=180)
        self.parent_view = paginated_view
        self.entry = entry
        self.index = index

        self.ctx = paginated_view.ctx
        self.bot = paginated_view.bot
        self.user_profile = paginated_view.user_profile
        self.author_id = paginated_view.author_id
        self.manage_cog = paginated_view.manage_cog

    @discord.ui.button(label="✏ Edit", style=discord.ButtonStyle.blurple)
    async def edit_entry(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        await interaction.response.send_modal(EditModlogEntryModal(self, self.index, self.entry))

    @discord.ui.button(label="🗑 Delete", style=discord.ButtonStyle.red)
    async def delete_entry(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        success = await self.user_profile.delete_modlog_entry(self.index)
        if success:
            mlu.save_db(self.bot)
            await interaction.response.send_message("✅ Entry deleted.", ephemeral=True)
            
            # Refresh entries and rebuild view
            entries = await self.user_profile.get_modlog_entries(force_refresh=True)
            embed, total_pages = await self.user_profile.build_modlog_embed()
            new_view = PaginatedModLogView(self.parent_view.parent_view, entries, total_pages)
            new_view.message = self.parent_view.message
            
            # Edit the original message that the view is attached to
            if self.parent_view.message:
                await self.parent_view.message.edit(embed=embed, view=new_view)
        else:
            await interaction.response.send_message("⚠️ Could not delete entry.", ephemeral=True)


    @discord.ui.button(label="← Back to Log", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_log(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        embed, _ = await self.user_profile.build_modlog_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class EditModlogEntryModal(discord.ui.Modal, title="Edit Modlog Entry"):
    def __init__(self, view: PaginatedModLogView, entry_index: int, entry: mlu.ModLogEntry):
        super().__init__()
        self.view = view
        self.entry_index = entry_index
        self.entry = entry

        # Pre-fill fields with current data
        self.reason = discord.ui.TextInput(
            label="Reason",
            default=entry.reason,
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1024
        )

        self.duration = discord.ui.TextInput(
            label="Duration (optional, e.g. 1d2h)",
            default=entry.length or "",
            required=False,
            max_length=32
        )

        self.add_item(self.reason)
        self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction):  # pylint: disable=W0221
        success = await self.view.user_profile.update_modlog_entry(
            self.entry_index,
            reason=self.reason.value,
            length=self.duration.value if self.duration.value else None
        )
        
        if success:
            mlu.save_db(self.view.bot)
            await interaction.response.defer()
            
            # Refresh entries and rebuild view
            entries = await self.view.user_profile.get_modlog_entries(force_refresh=True)
            embed, total_pages = await self.view.user_profile.build_modlog_embed()
            new_view = PaginatedModLogView(self.view.parent_view.parent_view, entries, total_pages)
            new_view.message = self.view.parent_view.message
            
            # Edit the original message that the view is attached to
            if self.view.parent_view.message:
                await self.view.parent_view.message.edit(embed=embed, view=new_view)
            await interaction.followup.send("✅ Entry edited!", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Could not update log entry.", ephemeral=True)



class MuteConfirmationView(discord.ui.View):
    def __init__(self, parent_view: "ModView"):
        super().__init__(timeout=60)
        self.ctx = parent_view.ctx
        self.user_id = parent_view.id_arg
        self.author_id = parent_view.author_id
        self.manage_cog = parent_view.manage_cog
        self.bot = parent_view.bot

    @discord.ui.button(label="Add Reason/Duration", style=discord.ButtonStyle.primary)
    async def add_reason(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return
        await interaction.response.send_modal(AddModlogEntryModal(self, "Mute"))

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm_mute(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        # Build a fake message that simulates the command call
        fake_message = copy.copy(interaction.message)
        fake_message.author = interaction.user
        fake_message.content = f"{self.ctx.prefix}mute {self.user_id}"

        ctx = await self.bot.get_context(fake_message)
        await self.bot.invoke(ctx)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel_mute(self, interaction: discord.Interaction, button: discord.ui.Button):  # pylint: disable=W0613
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

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
        self.add_item(self.reason)
        if entry_type.lower() in ["mute", "ban"]:
            self.duration = discord.ui.TextInput(
                label="Duration (optional, e.g. 1d2h)",
                placeholder="Leave blank for permanent",
                required=False,
                max_length=32
            )
            self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction):  # pylint: disable=W0221
        await interaction.response.defer(ephemeral=True)

        # Create new ModLogEntry
        entry = mlu.ModLogEntry(
            entry_type=self.entry_type,
            reason=self.reason.value,
            author=interaction.user.display_name,
            author_id=str(interaction.user.id),
            length=self.duration.value if self.duration.value else ""
        )

        # Use UserProfile to add entry
        await self.view.user_profile.add_modlog_entry(entry)
        mlu.save_db(self.view.bot)

        # Send to log channel (optional)
        log_channel_id = 1364314775789502666  # Replace with your real channel
        log_channel = self.view.ctx.guild.get_channel(log_channel_id)
        if log_channel:
            embed = entry.build_message_embed()
            await log_channel.send(embed=embed)


        # Refresh entries and rebuild view
        entries = await self.view.user_profile.get_modlog_entries(force_refresh=True)
        embed, total_pages = await self.view.user_profile.build_modlog_embed()
        new_view = PaginatedModLogView(self.view.parent_view, entries, total_pages)
        new_view.message = self.view.message
        
        # Edit the original message that the view is attached to
        if self.view.message:
            await self.view.message.edit(embed=embed, view=new_view)
        await interaction.followup.send("✅ Entry added!", ephemeral=True)


class UserManage(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    # @commands.group(aliases=['manage', 'um'], invoke_without_command=True)
    # async def user_manage(self, ctx: commands.Context, *, id_arg: str):
    #     member, user, user_id = await mlu.resolve_user(ctx, id_arg, self.bot)

    #     if not user:
    #         emb = utils.red_embed("")
    #         emb.set_author(name="COULD NOT FIND USER")
    #         await utils.safe_send(ctx, embed=emb)
    #         return

    #     # Build detailed user summary embed
    #     embed = await mlu.build_user_summary_embed(self.bot, ctx, member, user)
    #     mod_cog = ctx.bot.get_cog("ChannelMods")
    #     # Create interactive button view
    #     view = ModView(mod_cog, self, ctx, user_id)
    #     await view.init()

    #     message = await utils.safe_send(ctx, embed=embed, view=view)
    #     view.message = message

    async def launch_user_manage_view(
        self,
        interaction: Union[commands.Context, Interaction],
        member,
        user,
        ephemeral=False
    ):
        user_profile = await mlu.UserProfile.create(self.bot, interaction, str(user.id))
        if not user_profile:
            emb = utils.red_embed("")
            emb.set_author(name="COULD NOT FIND USER")
            if isinstance(interaction, Interaction):
                await interaction.response.send_message(embed=emb, ephemeral=True)
            else:
                await utils.safe_send(interaction, embed=emb)
            return

        embed = await user_profile.build_summary_embed()
        mod_cog = self.bot.get_cog("ChannelMods")
        view = ModView(mod_cog, self, interaction, str(user.id))
        await view.init()

        if isinstance(interaction, Interaction):
            await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
            view.message = await interaction.original_response()
        else:
            # it's a text command (Context)
            view.message = await utils.safe_send(interaction, embed=embed, view=view)

    @commands.group(aliases=['manage', 'um'], invoke_without_command=True)
    async def user_manage(self, ctx: commands.Context, *, id_arg: str):
        user_profile = await mlu.UserProfile.create(self.bot, ctx, id_arg)
        if not user_profile:
            emb = utils.red_embed("")
            emb.set_author(name="COULD NOT FIND USER")
            await utils.safe_send(ctx, embed=emb)
            return

        await self.launch_user_manage_view(ctx, user_profile.member, user_profile.user)


@app_commands.context_menu(name="Manage User")
@app_commands.guilds(243838819743432704)
@app_commands.default_permissions()
async def context_user_manage(interaction: discord.Interaction, target_user: discord.User):
    cog: UserManage = interaction.client.get_cog("UserManage")
    if cog is None:
        await interaction.response.send_message("UserManage cog is not loaded.", ephemeral=True)
        return

    member = interaction.guild.get_member(target_user.id)

    # Call a method on the cog instance; e.g., launch a shared method you create
    await cog.launch_user_manage_view(interaction, member, target_user, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserManage(bot))
    # context_command = app_commands.ContextMenu(
    #     name="Manage User",
    #     callback=context_user_manage,
    #     guild_ids=[243838819743432704]
    # )
    # bot.tree.add_command(context_command)

    # await bot.tree.sync(guild=discord.Object(id=243838819743432704))
