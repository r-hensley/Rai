import copy
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
        self.id_arg = id_arg
        self.author_id = ctx.author.id

    @discord.ui.button(label="Open log", style=discord.ButtonStyle.primary)
    async def modlog_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        _member, user, user_id = await mlu.resolve_user(self.ctx, self.id_arg, self.cog.bot)
        embed = await mlu.build_modlog_embed(self.cog.bot, self.ctx, user_id, user)

        # Replace the current message
        view = ModLogView(self)
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
        fake_message.content = f"{self.ctx.prefix}mute {self.id_arg}"

        ctx = await self.cog.bot.get_context(fake_message)
        await self.cog.bot.invoke(ctx)

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.red)
    async def ban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        _member, user, user_id = await mlu.resolve_user(self.ctx, self.id_arg, self.cog.bot)
        embed = await mlu.build_modlog_embed(self.cog.bot, self.ctx, user_id, user)

        # Replace the current message
        view = BanView(self)
        await interaction.message.edit(embed=embed, view=view)

    @discord.ui.button(label="Warn", style=discord.ButtonStyle.blurple)
    async def warn_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Build a fake message that simulates the command call
        fake_message = copy.copy(interaction.message)
        fake_message.author = interaction.user
        fake_message.content = f"{self.ctx.prefix}warn {self.id_arg}"

        ctx = await self.cog.bot.get_context(fake_message)
        await self.cog.bot.invoke(ctx)


class ModLogView(discord.ui.View):
    def __init__(self, parent_view: "ModView"):
        super().__init__()
        self.ctx = parent_view.ctx
        self.user_id = parent_view.id_arg
        self.author_id = parent_view.author_id
        self.manage_cog = parent_view.manage_cog

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer()

        # Resolve user again
        member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.manage_cog.bot)
        embed = await mlu.build_user_summary_embed(self.manage_cog.bot, self.ctx, user_id, member, user)

        # Recreate the original ModView
        mod_cog = self.ctx.bot.get_cog("ChannelMods")
        view = ModView(self.manage_cog, mod_cog, self.ctx, user_id)
        await interaction.message.edit(embed=embed, view=view)

    @discord.ui.button(label="➕ Add Entry", style=discord.ButtonStyle.success)
    async def add_entry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.send_modal(AddModlogEntryModal(self, "Silent Log"))


class BanView(discord.ui.View):
    def __init__(self, parent_view: "ModView"):
        super().__init__()
        self.ctx = parent_view.ctx
        self.user_id = parent_view.id_arg
        self.author_id = parent_view.author_id
        self.manage_cog = parent_view.manage_cog

    @discord.ui.button(label="Ban (hacked)", style=discord.ButtonStyle.success)
    async def ban_hacked(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer()

        # Resolve user again
        member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.manage_cog.bot)
        embed = await mlu.build_user_summary_embed(self.manage_cog.bot, self.ctx, user_id, member, user)

        # Recreate the original ModView
        mod_cog = self.ctx.bot.get_cog("ChannelMods")
        view = BanConfirmationView(self)
        await interaction.message.edit(embed=embed, view=view)

    @discord.ui.button(label="Ban (minor)", style=discord.ButtonStyle.success)
    async def ban_minor(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer()

        # Resolve user again
        member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.manage_cog.bot)
        embed = await mlu.build_user_summary_embed(self.manage_cog.bot, self.ctx, user_id, member, user)

        # Recreate the original ModView
        mod_cog = self.ctx.bot.get_cog("ChannelMods")
        view = BanConfirmationView(self)
        await interaction.message.edit(embed=embed, view=view)

    @discord.ui.button(label="Ban (hate)", style=discord.ButtonStyle.success)
    async def ban_hate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.defer()

        # Resolve user again
        member, user, user_id = await mlu.resolve_user(self.ctx, self.user_id, self.manage_cog.bot)
        embed = await mlu.build_user_summary_embed(self.manage_cog.bot, self.ctx, user_id, member, user)

        # Recreate the original ModView
        mod_cog = self.ctx.bot.get_cog("ChannelMods")
        view = BanConfirmationView(self)
        await interaction.message.edit(embed=embed, view=view)

    @discord.ui.button(label="Ban (add reason)", style=discord.ButtonStyle.success)
    async def ban_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🚫 Only the original author can use this.", ephemeral=True)
            return

        await interaction.response.send_modal(AddModlogEntryModal(self, "Ban"))


class BanConfirmationView(discord.ui.View):
    def __init__(self, parent_view: "ModView"):
        super().__init__()
        self.ctx = parent_view.ctx
        self.user_id = parent_view.id_arg
        self.author_id = parent_view.author_id
        self.manage_cog = parent_view.manage_cog


class AddModlogEntryModal(discord.ui.Modal, title="Add Modlog Entry"):
    def __init__(self, view: ModLogView, entry_type):
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
        user_id = str(self.view.user_id)
        guild_id = str(ctx.guild.id)
        bot = self.view.manage_cog.bot

        # Ensure modlog DB is set up
        if guild_id not in bot.db["modlog"]:
            bot.db["modlog"][guild_id] = {}

        if user_id not in bot.db["modlog"][guild_id]:
            bot.db["modlog"][guild_id][user_id] = []

        from datetime import datetime
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
        user = await bot.fetch_user(int(user_id))
        embed = await mlu.build_modlog_embed(bot, ctx, user_id, user)

        new_view = ModLogView(self.view)
        await interaction.message.edit(embed=embed, view=new_view)


class UserManage(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    @commands.group(aliases=['manage', 'um'], invoke_without_command=True)
    async def user_manage(self, ctx: commands.Context, *, id_arg: str):
        member, user, user_id = await mlu.resolve_user(ctx, id_arg, self.bot)

        if not member and not user:
            emb = utils.red_embed("")
            emb.set_author(name="COULD NOT FIND USER")
            await utils.safe_send(ctx, embed=emb)
            return

        # Build detailed user summary embed
        embed = await mlu.build_user_summary_embed(self.bot, ctx, user_id, member, user)
        mod_cog = ctx.bot.get_cog("ChannelMods")
        # Create interactive button view
        view = ModView(mod_cog, self, ctx, user_id)

        await utils.safe_send(ctx, embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(UserManage(bot))
