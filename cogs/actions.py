import os
from datetime import timedelta
from typing import Union

import discord
from discord import Interaction

from discord.ext import commands

from cogs.utils.BotUtils import bot_utils as utils
from .utils import helper_functions as hf

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SP_SERV_ID = 243838819743432704
JP_SERVER_ID = 189571157446492161
CH_SERV_ID = 266695661670367232

class Actions(commands.Cog):
    """A cog for base moderation actions like ban, kick, mute, and unmute."""

    def __init__(self, bot):
        self.bot = bot
    
    class BanConfirmationView(utils.RaiView):
        def __init__(self,
                     targets: list[Union[discord.User, discord.Member]],
                     reason: str,
                     length: list[int],
                     time_string: str,
                     delete_message_seconds: int = 0,
                     appeal: bool = True,
                     ctx: Union[discord.Interaction, commands.Context] = None):
            super().__init__(timeout=60)
            self.targets = targets
            self.reason = reason
            self.delete_message_seconds = delete_message_seconds
            self.length = length
            self.time_string = time_string
            self.appeal = appeal
            self.ctx = ctx
            self.silent = None
            self.confirmed = None
            self.command_caller = ctx.author if isinstance(ctx, commands.Context) \
                else ctx.user  # Store the command caller
        
        async def interaction_check(self, interaction: Interaction) -> bool:
            if interaction.user == self.command_caller:
                return True
            else:
                await interaction.response.send_message(
                    "Only the person who initiated the ban can interact with this.",
                    ephemeral=True)
                return False
        
        def get_embed(self) -> discord.Embed:
            """The embed that will be sent to the user"""
            emb = discord.Embed(
                title=f"You've been banned from {self.ctx.guild.name}")
            if self.length:
                emb.description = f"You will be unbanned automatically at {self.time_string} " \
                                  f"(in {self.length[0]} days and {self.length[1]} hours)"
            else:
                emb.description = "This ban is indefinite."
            
            emb.add_field(name="Reason:", value=self.reason)
            
            if self.appeal:
                ban_appeal_server: discord.Guild = self.ctx.bot.get_guild(
                    985963522796183622)
                ban_appeal_server_invite_link = "https://discord.gg/pnHEGPah8X"
                if ban_appeal_server:
                    if discord.utils.get(ban_appeal_server.text_channels,
                                         topic=str(self.ctx.guild.id)):
                        emb.add_field(name="Server for appealing your ban",
                                      value=ban_appeal_server_invite_link,
                                      inline=False)
            else:
                # say an appeal will not be possible
                emb.add_field(
                    name="Appeal", value="This ban can not be appealed.", inline=False)
            
            return emb
        
        def get_message_content(self) -> str:
            """The content for moderators to see describing the ban above the embed"""
            content = f"You are about to ban: **{'**, **'.join([t.mention for t in self.targets])}**\n"
            if self.delete_message_seconds:
                content += (f"- __Messages will be deleted__ from the last "
                            f"{self.delete_message_seconds // 60 // 60} hours .\n")
            
            return content
        
        async def handle_response(self, interaction: discord.Interaction, confirmed: bool):
            # noinspection PyUnresolvedReferences
            await interaction.response.defer(thinking=False)
            self.confirmed = confirmed
            self.stop()
        
        @discord.ui.button(label="Ban (Send DM)", style=discord.ButtonStyle.green, row=1)
        async def dm_confirm_button(self, interaction: discord.Interaction, _: discord.ui.Button):
            self.silent = False
            await self.handle_response(interaction, True)
        
        @discord.ui.button(label="Ban (Silent)", style=discord.ButtonStyle.green, row=1)
        async def silent_confirm_button(self, interaction: discord.Interaction,
                                        _: discord.ui.Button):
            self.silent = True
            await self.handle_response(interaction, True)
        
        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=1)
        async def cancel_button(self, interaction: discord.Interaction, _: discord.ui.Button):
            await self.handle_response(interaction, False)
        
        @discord.ui.button(label="Toggle Delete Messages", style=discord.ButtonStyle.blurple, row=2)
        async def toggle_delete_button(self, interaction: discord.Interaction,
                                       button: discord.ui.Button):
            self.delete_message_seconds = 24 * 60 * \
                                          60 if self.delete_message_seconds == 0 else 0
            button.style = discord.ButtonStyle.blurple if not self.delete_message_seconds else discord.ButtonStyle.red
            # noinspection PyUnresolvedReferences
            await interaction.response.edit_message(content=self.get_message_content(),
                                                    embed=self.get_embed(),
                                                    view=self)
        
        @discord.ui.button(label="Toggle Appeal", style=discord.ButtonStyle.blurple, row=2)
        async def toggle_appeal_button(self, interaction: discord.Interaction,
                                       button: discord.ui.Button):
            self.appeal = not self.appeal
            button.style = discord.ButtonStyle.blurple if self.appeal else discord.ButtonStyle.red
            # noinspection PyUnresolvedReferences
            await interaction.response.edit_message(content=self.get_message_content(),
                                                    embed=self.get_embed(),
                                                    view=self)
    
    async def ban(self, ctx, targets, reason, length, time_string):
        # check permissions for target, and also the person calling the command
        for target in targets.copy():
            if hasattr(target, "joined_at"):  # will be false if the user is not in the server
                joined_at = discord.utils.utcnow() - target.joined_at
            else:
                # arbitrarily bigger than 24 to fail the conditional
                joined_at = timedelta(hours=25)
            
            # check if top role of target user is higher than Rai
            if hasattr(target, "top_role"):
                if target.top_role > ctx.guild.me.top_role:
                    await utils.safe_send(ctx,
                                          f"I won't be able to ban {str(target)} "
                                          f"as their top role is higher than mine.")
                    targets.remove(target)
                    continue
            
            # Allow server helpers on Spanish/JP server to
            # ban users who joined within last 60 minutes
            perms = False
            if hf.admin_check(ctx):
                perms = True
            else:
                if joined_at < timedelta(hours=24):
                    if ctx.guild.id == JP_SERVER_ID:
                        jp_staff_role = 543721608506900480
                        if ctx.guild.get_role(jp_staff_role) in ctx.author.roles:
                            perms = True
                    elif ctx.guild.id == SP_SERV_ID:
                        sp_server_helper_role = 258819531193974784
                        if ctx.guild.get_role(sp_server_helper_role) in ctx.author.roles:
                            perms = True
            
            if not perms:
                raise commands.MissingPermissions(['ban_members'])
        
        if not targets:
            return
        
        author_tag = f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** "
        # this will only be used in the internal discord ban reason
        ban_reason = f"{author_tag}{reason}"
        if len(ban_reason) > 512:
            msg = (f"Discord only allows bans with a length of __512 characters__. "
                   f"With my included author tag, you are allowed __{512 - len(author_tag)} "
                   f"characters__. Please reduce the "
                   f"length of your ban message by __{len(ban_reason) - 512} characters__. "
                   f"\n\nAlternatively, "
                   f"consider sending the full length of the ban text as a separate warning "
                   f"immediately before the ban itself if reducing characters would be difficult.")
            await utils.safe_send(ctx, msg)
            return
        
        view = self.BanConfirmationView(
            targets, reason, length=length, time_string=time_string, ctx=ctx)
        confirmation_msg = await ctx.send(content=view.get_message_content(),
                                          embed=view.get_embed(), view=view)
        await view.wait()  # wait for response to view to complete
        
        flags = {}
        any_flags = False
        if view.confirmed:
            successes = []
            failures = []
            for target in targets:
                if not view.silent:
                    try:
                        await utils.safe_send(target, embed=view.get_embed())
                    except discord.Forbidden:
                        await utils.safe_send(ctx, f"The user {target.mention} has "
                                                   f"DMs blocked. Defaulting to silent ban.")
                try:
                    await ctx.guild.ban(target, reason=ban_reason,
                                        delete_message_seconds=view.delete_message_seconds)
                    successes.append(target)
                except Exception as e:
                    await utils.safe_send(ctx, f"I couldn't ban {target.mention}: `{e}`")
                    failures.append(target)
                else:
                    # calculate length of temporary ban
                    if length:
                        default_config = {'enable': False, 'channel': None, 'timed_bans': {}}
                        config = self.bot.db['bans'].setdefault(str(ctx.guild.id), default_config)
                        timed_bans = config.setdefault('timed_bans', {})
                        timed_bans[str(target.id)] = time_string
                    else:
                        # if the user was already scheduled to be unbanned at some point,
                        # delete the entry, changing it to a permanent ban
                        try:
                            g_id = str(ctx.guild.id)
                            if str(target.id) in self.bot.db['bans'][g_id]['timed_bans']:
                                del self.bot.db['bans'][g_id]['timed_bans'][str(target.id)]
                        except KeyError:
                            pass
                    
                    # format length string and add to modlog
                    if length:
                        length_str = f"{length[0]}d{length[1]}h"
                    else:
                        length_str = None
                    if reason.startswith("*by*"):
                        reason = reason.replace(
                            f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** ", '')
                    modlog_entry = hf.ModlogEntry(event="Ban", user=target,
                                                  guild=ctx.guild, ctx=ctx,
                                                  length=length_str, reason=reason,
                                                  silent=view.silent)
                    modlog_entry.add_to_modlog()
                    
                    # check for user account flags
                    flag_one = bool(await hf.suspected_spam_activity_flag(ctx.guild.id, target.id))
                    flag_two = bool(await hf.excessive_dm_activity(ctx.guild.id, target.id))
                    if flag_one or flag_two:
                        any_flags = True
                    flags[target.id] = (flag_one, flag_two)
            
            # check for if any of the users have flags for spamming or excessive DM activity
            if successes:
                if any_flags:
                    flag_msg = "The following users were flagged for potential spamming or excessive DM activity:\n"
                    for member in successes:
                        if flags[member.id][0] and not flags[member.id][1]:
                            flag_msg += f"- {member.mention} ***(Was flagged for suspected spam activity)***\n"
                        elif not flags[member.id][0] and flags[member.id][1]:
                            flag_msg += f"- {member.mention} ***(Was flagged for excessive DMs at one point)***\n"
                        elif flags[member.id][0] and flags[member.id][1]:
                            flag_msg += (
                                f"- {member.mention} ***(Was flagged for both excessive DM activity "
                                f"and potential spamming activities)***\n")
                    flag_msg += f"-# ||<@{self.bot.owner_id}>||\n"
                    await confirmation_msg.reply(flag_msg)
                
                embed = discord.Embed(
                    title="Ban Successful",
                    description=f"Successfully banned {', '.join(user.mention for user in successes)}",
                    color=0x00FF00
                )
                if failures:
                    embed.add_field(
                        name="Failed to Ban",
                        value=", ".join(user.mention for user in failures),
                        inline=False)
                await confirmation_msg.edit(embed=embed, view=None)
                
                return
        
        embed = discord.Embed(
            title="Ban Cancelled",
            description="The ban operation was cancelled.",
            color=0xFFA500
        )
        await confirmation_msg.edit(content=None, embed=embed, view=None)