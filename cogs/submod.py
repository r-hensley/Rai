import asyncio
import re
import os
from collections import Counter
from typing import Optional, List, Union
from datetime import timedelta, datetime, timezone

import discord
from discord import app_commands, Interaction
from discord.ext import commands
from .utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

SP_SERV_ID = 243838819743432704
JP_SERVER_ID = 189571157446492161
CH_SERV_ID = 266695661670367232


class Submod(commands.Cog):
    """Help"""

    def __init__(self, bot):
        self.bot: commands.Bot = bot

    async def cog_check(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel':
            if not ctx.message.content.endswith("help"):  # ignore if it's the help command
                await utils.safe_send(ctx, "Please set a mod channel using `;set_mod_channel`.")
            return
        return True
    #
    # @commands.command(hidden=True)
    # @commands.bot_has_permissions(embed_links=True, ban_members=True)
    # @hf.is_submod()
    # async def old_ban(self, ctx, *, args: str):
    #     """Bans a user.  Usage: `;ban <list of users> [time #y#d#h] [reason]`
    #     Examples:
    #     - `;ban @Ryry013 being mean`
    #     - `;ban @Abelian 2d3h specify a time for a temporary ban`
    #     - `;ban 2d3h @Abelian swapping time and user mention`
    #     - `;ban 202995638860906496 414873201349361664 specify multiple IDs`
    #
    #     Helpers on Sp-En server can ban users within an hour after they join the server.
    #     """
    #     if not args:
    #         await utils.safe_send(ctx, ctx.command.help)
    #         return
    #
    #     # Here is the shortcut setter for the context menu ban command.
    #     # If this is triggered, the ban command should skip all printed confirmations and questions and just
    #     # skip straight to the banning
    #     # The arg will either be ⁣⁣delete or ⁣⁣keep__ with underscores to keep them the same length
    #     if '⁣⁣delete' in args:
    #         slash = True
    #         delete = 1
    #         args = re.sub(r'⁣⁣delete ?', '', args)
    #     elif '⁣⁣keep__' in args:
    #         slash = True
    #         delete = 0
    #         args = re.sub(r'⁣⁣keep__ ?', '', args)
    #     else:
    #         slash = False
    #         delete = 0
    #
    #     args = hf.args_discriminator(args)
    #
    #     user_ids = args.user_ids
    #     reason = args.reason
    #     length = args.length
    #     time_string = args.time_string
    #
    #     targets: List[discord.Member] = []
    #     for user_id in user_ids:
    #         target: Union[discord.User, discord.Member, None] = await utils.member_converter(ctx, user_id)
    #         if target:
    #             targets.append(target)
    #         else:
    #             # Check users who have recently left the server
    #             try:
    #                 recently_removed = self.bot.recently_removed_members[str(ctx.guild.id)]
    #                 id_to_member_dict: dict[int: discord.Member] = {m.id: m for m in recently_removed}
    #                 if user_id in id_to_member_dict:  # target is an ID
    #                     targets.append(id_to_member_dict[user_id])
    #                     continue
    #             except KeyError:
    #                 pass
    #
    #             # Try manually fetching an ID through an API call
    #             try:
    #                 target = await self.bot.fetch_user(user_id)
    #                 if target:
    #                     targets.append(target)
    #                     continue
    #                 else:
    #                     await utils.safe_send(ctx, f"I could not find the user {user_id}.")
    #             except discord.NotFound:
    #                 await utils.safe_send(ctx, f"I could not find the user {user_id}.")
    #             except ValueError:
    #                 await utils.safe_send(ctx, f"I could not find the user {user_id}.")
    #
    #     if not targets:
    #         await utils.safe_send(ctx, "I couldn't resolve any users to ban. Please check the IDs you gave again.")
    #         return
    #
    #     if not reason:
    #         reason = '(no reason given)'
    #
    #     # this memorial exists to forever remember the robot head, may you rest in peace ['_']
    #     # this comment exists to wonder what the hell the robot head was...
    #     for target in targets.copy():
    #         if hasattr(target, "joined_at"):  # will be false if the user is not in the server
    #             joined_at = discord.utils.utcnow() - target.joined_at
    #         else:
    #             joined_at = timedelta(hours=25)  # arbitrarily bigger than 24 to fail the conditional
    #
    #         # check if top role of target user is higher than Rai
    #         if hasattr(target, "top_role"):
    #             if target.top_role > ctx.guild.me.top_role:
    #                 await utils.safe_send(ctx,
    #                                    f"I won't be able to ban {str(target)} as their top role is higher than mine.")
    #                 targets.remove(target)
    #                 continue
    #
    #         # Allow server helpers on Spanish/JP server to ban users who joined within last 60 minutes
    #         perms = False
    #         if hf.admin_check(ctx):
    #             perms = True
    #         else:
    #             if joined_at < timedelta(hours=24):
    #                 if ctx.guild.id == JP_SERVER_ID:
    #                     jp_staff_role = 543721608506900480
    #                     if ctx.guild.get_role(jp_staff_role) in ctx.author.roles:
    #                         perms = True
    #                 elif ctx.guild.id == SP_SERV_ID:
    #                     sp_server_helper_role = 258819531193974784
    #                     if ctx.guild.get_role(sp_server_helper_role) in ctx.author.roles:
    #                         perms = True
    #
    #         if not perms:
    #             raise commands.MissingPermissions(['ban_members'])
    #
    #     if not targets:
    #         return
    #
    #     # Start constructing embed to send to user
    #     em = discord.Embed(title=f"You've been banned from {ctx.guild.name}")
    #     if length:
    #         em.description = f"You will be unbanned automatically at {time_string} " \
    #                          f"(in {length[0]} days and {length[1]} hours)"
    #     else:
    #         em.description = "This ban is indefinite."
    #     silent = False
    #     if reason != '(no reason given)':
    #         if '-silent' in reason or '-s' in reason:
    #             silent = True
    #             reason = reason.replace('-silent ⁣', '').replace('-s ', '')
    #             reason = '⁣' + reason  # a reason starting with a no width space signifies a silent ban
    #         if '-c' in reason:
    #             reason = '⠀' + reason  # invisible space = crosspost
    #         if noappeal := '-noappeal' in reason:
    #             reason = reason.replace('-noappeal', '')
    #         em.add_field(name="Reason:", value=reason)
    #
    #         # If the current guild is in Modbot's appeals server, add a field for the link to that server
    #         # so users can appeal their bans
    #         ban_appeal_server: discord.Guild = self.bot.get_guild(985963522796183622)
    #         ban_appeal_server_invite_link = "https://discord.gg/pnHEGPah8X"
    #         if ban_appeal_server:
    #             if discord.utils.get(ban_appeal_server.text_channels, topic=str(ctx.guild.id)):
    #                 if not noappeal:
    #                     em.add_field(name="Server for appealing your ban", value=ban_appeal_server_invite_link,
    #                                  inline=False)
    #                 else:
    #                     em.add_field(name="Server for appealing your ban", value="This ban can not be appealed.",
    #                                  inline=False)
    #     if not slash:
    #         await utils.safe_send(ctx, f"You are about to ban {', '.join([t.mention for t in targets])}: ", embed=em)
    #     msg2 = "Do you wish to continue?  Options:\n" \
    #            "⠀・ `Yes` Silently ban the user\n" \
    #            "⠀・ `Send` Ban the user and send them the above notification\n" \
    #            "⠀・ `No` Cancel the ban\n" \
    #            "⠀・ Add `delete` or `del` to delete last 24 hours of messages (example `send del`)\n" \
    #            "⠀*(Cancel this ban and add `-noappeal` to your ban reason to prevent users from appealing their ban)*\n"
    #
    #     あれ = self.bot.get_guild(257984339025985546)
    #     if あれ:
    #         if ctx.author in あれ.members:
    #             try:
    #                 if 'crosspost' in self.bot.db['bans'][str(ctx.guild.id)]:
    #                     if not reason.startswith('⁣') and str(ctx.guild.id) in self.bot.db['bans']:  # no width space
    #                         if self.bot.db['bans'][str(ctx.guild.id)]['crosspost']:
    #                             # crosspost_check = 1  # to cancel crosspost
    #                             msg2 += "⠀・ `Yes/Send -s` Do not crosspost this ban"
    #                     if not reason.startswith('⠀') and str(ctx.guild.id) in self.bot.db['bans']:  # invisible space
    #                         if not self.bot.db['bans'][str(ctx.guild.id)]['crosspost']:
    #                             # crosspost_check = 2  # to specially crosspost
    #                             msg2 += "⠀・ `Yes/Send -c` Specially crosspost this ban"
    #             except KeyError:
    #                 pass
    #
    #     if not slash:
    #         msg2 = await utils.safe_send(ctx, msg2)
    #
    #         try:
    #             msg = await self.bot.wait_for('message',
    #                                           timeout=40.0,
    #                                           check=lambda x: x.author == ctx.author and
    #                                           x.content.casefold()[:4] in ['yes', 'yes ', 'no', 'send'])
    #         except asyncio.TimeoutError:
    #             try:
    #                 await msg2.delete()
    #             except (discord.Forbidden, discord.NotFound):
    #                 pass
    #             await utils.safe_send(ctx, "Timed out.  Canceling ban.")
    #             return
    #         content = msg.content.casefold()
    #         if content == 'no':
    #             try:
    #                 await msg2.delete()
    #             except (discord.Forbidden, discord.NotFound):
    #                 pass
    #             await utils.safe_send(ctx, "Canceling ban")
    #             return
    #
    #         try:
    #             await msg2.delete()
    #         except (discord.Forbidden, discord.NotFound):
    #             pass
    #
    #         if 'delete' in content or 'del' in content:
    #             delete = 1
    #         else:
    #             delete = 0
    #     else:  # if slash command
    #         content = 'send'
    #
    #     author_tag = f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** "
    #     text = f"{author_tag}{reason}"
    #     if len(text) > 512:
    #         await utils.safe_send(ctx, f"Discord only allows bans with a length of __512 characters__. With my included "
    #                                 f"author tag, you are allowed __{512 - len(author_tag)} characters__. Please reduce the "
    #                                 f"length of your ban message by __{len(text) - 512} characters__. \n\nAlternatively, "
    #                                    f"consider sending the full length of the ban text as a separate warning "
    #                                    f"immediately before the ban itself if reducing characters would be difficult.")
    #         return
    #
    #     if content.endswith('-s'):  # these will be parsed in the on_member_ban event in logger.py
    #         text = '⁣' + text
    #     if content.endswith('-c'):
    #         text = '⠀' + text
    #
    #     # check all targets for flags
    #     # 1. await hf.unusual_dm_activity(guildid, targetid) --> Optional[datetime]
    #     # 2. target.public_flags.spammer --> bool  # Flagged for potential spamming activities
    #     flags = {}
    #     any_flags = False
    #     for target in targets:
    #         flag_one = bool(await hf.suspected_spam_activity_flag(ctx.guild.id, target.id))
    #         flag_two = bool(await hf.excessive_dm_activity(ctx.guild.id, target.id))
    #         if flag_one or flag_two:
    #             any_flags = True
    #         flags[target.id] = (flag_one, flag_two)
    #
    #     successes = []
    #     for target in targets:
    #         if 'send' in content:
    #             try:
    #                 await utils.safe_send(target, embed=em)
    #             except discord.Forbidden:
    #                 await utils.safe_send(ctx, f"{target.mention} has PMs disabled so I didn't send the notification.")
    #
    #         try:
    #             await ctx.guild.ban(target, reason=text, delete_message_seconds=delete*60*60*24)
    #             successes.append(target)
    #         except discord.Forbidden:
    #             await utils.safe_send(ctx, f"I couldn't ban {target.mention}. They're probably above me in the role list.")
    #             continue
    #
    #         if length:
    #             config = self.bot.db['bans'].setdefault(str(ctx.guild.id),
    #                                                     {'enable': False, 'channel': None, 'timed_bans': {}})
    #             timed_bans = config.setdefault('timed_bans', {})
    #             timed_bans[str(target.id)] = time_string
    #
    #         if length:
    #             length_str = f"{length[0]}d{length[1]}h"
    #         else:
    #             length_str = None
    #         if reason.startswith("*by*"):
    #             reason = reason.replace(f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** ", '')
    #         modlog_entry = hf.ModlogEntry(event="Ban", user=target,
    #                                       guild=ctx.guild, ctx=ctx,
    #                                       length=length_str, reason=reason,
    #                                       silent=silent)
    #         modlog_entry.add_to_modlog()
    #
    #     if not any_flags:  # simple message
    #         conf = f"Successfully banned {', '.join([member.mention for member in successes])}"
    #     else:
    #         conf = f"Successfully banned the following users:\n"
    #         for member in successes:
    #             if flags[member.id][0] and not flags[member.id][1]:
    #                 conf += f"- {member.mention} ***(Was flagged for suspected spam activity)***\n"
    #             elif not flags[member.id][0] and flags[member.id][1]:
    #                 conf += f"- {member.mention} ***(Was flagged for excessive DMs at one point)***\n"
    #             elif flags[member.id][0] and flags[member.id][1]:
    #                 conf += (f"- {member.mention} ***(Was flagged for both excessive DM activity "
    #                          f"and potential spamming activities)***\n")
    #             else:
    #                 conf += f"- {member.mention}\n"
    #         conf += f"-# ||<@{self.bot.owner_id}>||\n"
    #
    #     await utils.safe_send(ctx, conf)
        
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
                await interaction.response.send_message("Only the person who initiated the ban can interact with this.",
                                                        ephemeral=True)
                return False
            
        def get_embed(self) -> discord.Embed:
            """The embed that will be sent to the user"""
            emb = discord.Embed(title=f"You've been banned from {self.ctx.guild.name}")
            if self.length:
                emb.description = f"You will be unbanned automatically at {self.time_string} " \
                                 f"(in {self.length[0]} days and {self.length[1]} hours)"
            else:
                emb.description = "This ban is indefinite."
            
            emb.add_field(name="Reason:", value=self.reason)
            
            if self.appeal:
                ban_appeal_server: discord.Guild = self.ctx.bot.get_guild(985963522796183622)
                ban_appeal_server_invite_link = "https://discord.gg/pnHEGPah8X"
                if ban_appeal_server:
                    if discord.utils.get(ban_appeal_server.text_channels, topic=str(self.ctx.guild.id)):
                        emb.add_field(name="Server for appealing your ban", value=ban_appeal_server_invite_link,
                                     inline=False)
            else:
                # say an appeal will not be possible
                emb.add_field(name="Appeal", value="This ban can not be appealed.", inline=False)
                
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
        async def silent_confirm_button(self, interaction: discord.Interaction, _: discord.ui.Button):
            self.silent = True
            await self.handle_response(interaction, True)
        
        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, row=1)
        async def cancel_button(self, interaction: discord.Interaction, _: discord.ui.Button):
            await self.handle_response(interaction, False)
            
        @discord.ui.button(label="Toggle Delete Messages", style=discord.ButtonStyle.blurple, row=2)
        async def toggle_delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.delete_message_seconds = 24 * 60 * 60 if self.delete_message_seconds == 0 else 0
            button.style = discord.ButtonStyle.blurple if not self.delete_message_seconds else discord.ButtonStyle.red
            # noinspection PyUnresolvedReferences
            await interaction.response.edit_message(content=self.get_message_content(),
                                                    embed=self.get_embed(),
                                                    view=self)
            
        @discord.ui.button(label="Toggle Appeal", style=discord.ButtonStyle.blurple, row=2)
        async def toggle_appeal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.appeal = not self.appeal
            button.style = discord.ButtonStyle.blurple if self.appeal else discord.ButtonStyle.red
            # noinspection PyUnresolvedReferences
            await interaction.response.edit_message(content=self.get_message_content(),
                                                    embed=self.get_embed(),
                                                    view=self)
   
    @discord.app_commands.command(name="ban", description="Ban a user from the server.")
    @app_commands.describe(reason="The reason for the ban",
                           member="The user to ban",member_id="The ID of the user to ban",
                           member_two="The user to ban", member_id_two="The ID of the user to ban",
                           member_three="The user to ban", member_id_three="The ID of the user to ban",
                           member_four="The user to ban", member_id_four="The ID of the user to ban")
    @commands.bot_has_permissions(ban_members=True)
    @commands.has_permissions(ban_members=True)
    @app_commands.default_permissions()
    @app_commands.guilds(SP_SERV_ID)
    async def slash_cmd_ban(self,
                            interaction: discord.Interaction,
                            reason: str = "No reason provided",
                            member: discord.Member = None,
                            member_id: str = None,
                            member_two: discord.Member = None,
                            member_id_two: str = None,
                            member_three: discord.Member = None,
                            member_id_three: str = None,
                            member_four: discord.Member = None,
                            member_id_four: str = None,):
        """Pass arguments received into the ban command."""
        ctx = await commands.Context.from_interaction(interaction)
        members = ' '.join([m.mention for m in [member, member_two, member_three, member_four] if m])
        member_ids = ' '.join(i for i in [member_id, member_id_two, member_id_three, member_id_four] if i)
        if not members and not member_ids:
            await interaction.response.send_message("You must provide at least one user to ban.", ephemeral=True)
            return
        await interaction.response.send_message("Starting ban process...", ephemeral=True)
        await self.prefix_cmd_ban(ctx, args_in=f"{members} {member_ids} {reason}")
        
    @commands.command(name="ban")
    @commands.bot_has_permissions(ban_members=True)
    @hf.is_submod()
    async def prefix_cmd_ban(self, ctx: Union[commands.Context, discord.Interaction], *, args_in: str):
        args = hf.args_discriminator(args_in)
        
        user_ids = args.user_ids
        reason = args.reason
        length = args.length
        time_string = args.time_string
        
        targets: List[discord.Member] = []
        for user_id in user_ids:
            target: Union[discord.User, discord.Member, None] = await utils.member_converter(ctx, user_id)
            if target:
                targets.append(target)
            else:
                # Check users who have recently left the server
                try:
                    recently_removed = self.bot.recently_removed_members[str(ctx.guild.id)]
                    id_to_member_dict: dict[int: discord.Member] = {m.id: m for m in recently_removed}
                    if user_id in id_to_member_dict:  # target is an ID
                        targets.append(id_to_member_dict[user_id])
                        continue
                except KeyError:
                    pass
                
                # Try manually fetching an ID through an API call
                try:
                    target = await self.bot.fetch_user(user_id)
                    if target:
                        targets.append(target)
                        continue
                    else:
                        await utils.safe_send(ctx, f"I could not find the user {user_id}.")
                except discord.NotFound:
                    await utils.safe_send(ctx, f"I could not find the user {user_id}.")
                except ValueError:
                    await utils.safe_send(ctx, f"I could not find the user {user_id}.")
        
        if not targets:
            await utils.safe_send(ctx, "I couldn't resolve any users to ban. "
                                       "Please check the IDs you gave again.")
            return
        
        # check permissions for target, and also the person calling the command
        for target in targets.copy():
            if hasattr(target, "joined_at"):  # will be false if the user is not in the server
                joined_at = discord.utils.utcnow() - target.joined_at
            else:
                joined_at = timedelta(hours=25)  # arbitrarily bigger than 24 to fail the conditional

            # check if top role of target user is higher than Rai
            if hasattr(target, "top_role"):
                if target.top_role > ctx.guild.me.top_role:
                    await utils.safe_send(ctx,
                                       f"I won't be able to ban {str(target)} "
                                       f"as their top role is higher than mine.")
                    targets.remove(target)
                    continue

            # Allow server helpers on Spanish/JP server to ban users who joined within last 60 minutes
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
        ban_reason = f"{author_tag}{reason}"  # this will only be used in the internal discord ban reason
        if len(ban_reason) > 512:
            await utils.safe_send(ctx,
                                  f"Discord only allows bans with a length of __512 characters__. With my included "
                                  f"author tag, you are allowed __{512 - len(author_tag)} characters__. Please reduce the "
                                  f"length of your ban message by __{len(ban_reason) - 512} characters__. \n\nAlternatively, "
                                  f"consider sending the full length of the ban text as a separate warning "
                                  f"immediately before the ban itself if reducing characters would be difficult.")
            return
        
        view = self.BanConfirmationView(targets, reason, length=length, time_string=time_string, ctx=ctx)
        confirmation_msg = await ctx.send(content=view.get_message_content(), embed=view.get_embed(), view=view)
        await view.wait()  # wait for response to view to complete
        
        flags = {}
        any_flags = False
        if view.confirmed:
            successes = []
            failures = []
            for target in targets:
                try:
                    if not view.silent:
                        await utils.safe_send(target, embed=view.get_embed())
                    await ctx.guild.ban(target, reason=ban_reason, delete_message_seconds=view.delete_message_seconds)
                    successes.append(target)
                except Exception as e:
                    await utils.safe_send(ctx, f"I couldn't ban {target.mention}: `{e}`")
                    failures.append(target)
                else:
                    # calculate length of temporary ban
                    if length:
                        config = self.bot.db['bans'].setdefault(str(ctx.guild.id),
                                                                {'enable': False, 'channel': None, 'timed_bans': {}})
                        timed_bans = config.setdefault('timed_bans', {})
                        timed_bans[str(target.id)] = time_string
                    
                    # format length string and add to modlog
                    if length:
                        length_str = f"{length[0]}d{length[1]}h"
                    else:
                        length_str = None
                    if reason.startswith("*by*"):
                        reason = reason.replace(f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** ", '')
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
                            flag_msg += (f"- {member.mention} ***(Was flagged for both excessive DM activity "
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

    
    submod = app_commands.Group(name="submod", description="Commands to configure server submods",
                                guild_ids=[SP_SERV_ID, CH_SERV_ID, 275146036178059265, JP_SERVER_ID])

    @submod.command(name="role")
    @app_commands.default_permissions()
    async def set_submod_role(self, itx: discord.Interaction, *, role: discord.Role):
        """Set the submod role for your server."""
        config = self.bot.db['submod_role'].setdefault(str(itx.guild.id), {'id': []})

        if not config['id']:
            config['id'] = []

        if role.id in config['id']:
            config['id'].remove(role.id)
            await itx.response.send_message(f"Removed {role.name} ({role.id}) as a submod role.")

        else:
            config['id'].append(role.id)
            await itx.response.send_message(f"Added {role.name} ({role.id}) as a submod role")

        # create and send a list of current roles
        remaining_roles = []
        for role_id in config['id']:
            potential_remaining_role = itx.guild.get_role(role_id)
            if potential_remaining_role:
                remaining_roles.append(f"{potential_remaining_role.name} ({potential_remaining_role.id})")
            else:
                config['id'].remove(role_id)
        remaining_roles_str = "- " + '\n- '.join(remaining_roles)

        await itx.followup.send(f"Current submod roles are:\n{remaining_roles_str}")

    @submod.command(name="channel")
    @app_commands.default_permissions()
    async def set_submod_channel(self, itx: discord.Interaction, channel: discord.TextChannel = None):
        """Sets the channel for submods"""
        if not channel:
            channel = itx.channel
        self.bot.db['submod_channel'][str(itx.guild.id)] = channel.id
        await itx.response.send_message(f"Set the submod channel for this server as {channel.mention}.")

    @commands.group(invoke_without_command=True, aliases=['w'])
    @hf.is_submod()
    async def warn(self, ctx, *, args):
        """Log a mod incident"""
        # If log came from context command, first two characters of args will be "⁣⁣". Remove those and set ephemeral
        # variable:
        if ephemeral := args.startswith('⁣⁣'):
            args = args[2:]

        args = hf.args_discriminator(args)

        user_ids = args.user_ids
        reason = args.reason

        # If silent, remove -s from reason if it's there
        if silent := "-s" in reason:
            reason = reason.replace(' -s', '').replace('-s ', '').replace('-s', '')

        if not reason:
            await utils.safe_send(ctx, "You must include a reason in your warning, please try again.")
            return

        users: List[discord.User] = []
        for user_id in user_ids:
            user = ctx.guild.get_member(user_id)  # Try finding user in guild
            if user:
                users.append(user)
            else:  # Couldn't find user in guild
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.NotFound:
                    user = None
                else:
                    if silent:
                        users.append(user)
                    else:
                        await utils.safe_send(ctx, f"The user {user} is not a member of this server so I couldn't "
                                                f"send the warning. I am aborting their warning.")
                        continue  # don't let code get to the addition of ModlogEntry object

            if not user:
                await utils.safe_send(ctx, f"I could not find the user {user_id}.  For warnings and mutes, "
                                        "please use either an ID or a mention to the user "
                                        "(this is to prevent mistaking people).")

        for user in users:
            modlog_entry = hf.ModlogEntry(event="Warning",
                                          user=user,
                                          guild=ctx.guild,
                                          ctx=ctx,
                                          silent=silent,
                                          reason=reason
                                          )

            emb = utils.red_embed("")
            emb.title = f"Warning from {ctx.guild.name}"
            emb.color = 0xffff00  # embed ff8800

            # Add reason to embed
            modlog_entry.reason = reason
            if len(reason) <= 1024:
                emb.add_field(name="Reason", value=reason, inline=False)
            elif 1024 < len(reason) <= 2048:
                emb.add_field(name="Reason", value=reason[:1024], inline=False)
                emb.add_field(name="Reason (cont.)", value=reason[1024:2048], inline=False)
            else:
                await utils.safe_send(ctx, f"Your warning text is too long ({len(reason)} characters). Please write "
                                        f"a message shorter than 2048 characters.")
                return

            # Add default prompt to go to modbot for questions about the warning
            modbot = ctx.guild.get_member(713245294657273856)
            if not modlog_entry.silent:
                if modbot:
                    emb.add_field(name="Questions about this warning?",
                                  value=f"Please send a message to {modbot.mention}.",
                                  inline=False)
                    content = f"Questions → {modbot.mention}"
                else:
                    content = ""

            # Send notification to warned user if not a log
            if not modlog_entry.silent:
                try:
                    await utils.safe_send(user, content, embed=emb)
                # if bot fails to send message to user, offer to send warning to a public channel
                except discord.Forbidden:
                    try:
                        # This will attempt to warn the user in a public channel if possible on your server
                        await self.attempt_public_warn(ctx, user, emb)
                    except discord.Forbidden:
                        continue  # failure in above command
                    except asyncio.TimeoutError:
                        return
                except discord.HTTPException:
                    await utils.safe_send(ctx, f"I cannot send messages to {user.mention}.")
                    continue

            # Edit embed for internal logging view after sending initial embed to user
            emb.insert_field_at(0, name="User", value=f"{user.name} ({user.id})", inline=False)

            if silent:
                emb.title = "Log *(This incident was not sent to the user)*"
                footer_text = f"Logged by {ctx.author.name} ({ctx.author.id})"
            else:
                emb.title = "Warning"
                footer_text = f"Warned by {ctx.author.name} ({ctx.author.id})"

            emb.set_footer(text=footer_text)

            emb.add_field(name="Jump URL", value=ctx.message.jump_url, inline=False)

            # Add to modlog
            config = modlog_entry.add_to_modlog()

            # Add field to confirmation showing how many incidents the user has if it's more than one
            modlog_channel = self.bot.get_channel(config['channel'])
            try:
                num_of_entries = len(config[str(user.id)])
                if num_of_entries > 1:
                    emb.add_field(name="Total number of modlog entries", value=num_of_entries)
            except KeyError:
                pass

            # Send notification to modlog channel if the modlog channel isn't current channel
            if modlog_channel:
                if modlog_channel != ctx.channel:
                    await utils.safe_send(modlog_channel, user.id, embed=emb)

            # Send notification (confirmation) to current channel
            if ephemeral:  # True if this came from context command
                return emb  # send the embed back to be used in the ephemeral followup send
            else:
                await utils.safe_send(ctx, embed=emb)

    async def attempt_public_warn(self, ctx, user, emb):
        if notif_channel_id := self.bot.db['modlog'] \
                .get(str(ctx.guild.id), {}) \
                .get("warn_notification_channel", None):
            notif_channel = self.bot.get_channel(notif_channel_id)
        else:
            await utils.safe_send(ctx, "I was unable to send the warning to this user. "
                                    "In the future you can type `;warn set` in a text channel in your "
                                    "server and I will offer to send a public warning to the user in "
                                    "these cases.")
            raise discord.Forbidden

        if notif_channel:
            question = await utils.safe_send(ctx, f"I could not send a message to {user.mention}. "
                                               f"Would you like to send a public warning to "
                                               f"{notif_channel.mention}?")
            await question.add_reaction('✅')
            await question.add_reaction('❌')

            def reaction_check(r, u):
                return u == ctx.author and str(r) in '✅❌'

            try:
                reaction_added, user_react = await self.bot.wait_for("reaction_add",
                                                                     check=reaction_check,
                                                                     timeout=10)
            except asyncio.TimeoutError:
                await utils.safe_send(ctx, f"Action timed out, I will not warn the user {user.mention}.")
                raise
            else:
                if str(reaction_added) == '✅':
                    try:
                        await utils.safe_send(notif_channel,
                                           f"{user.mention}: Due to your privacy settings "
                                           f"disabling messages from bots, we are "
                                           f"delivering this warning in a "
                                           f"public channel. If you believe this to be an "
                                           f"error, please contact a mod.",
                                           embed=emb)
                    except discord.Forbidden:
                        await utils.safe_send(ctx, "I can't send messages to the channel you have marked "
                                                "in this server as the warn notifications channel. Please "
                                                "go to a new channel and type `;warns set`.")
                        raise discord.Forbidden
                elif str(reaction_added) == '❌':
                    await utils.safe_send(ctx, f"I will not warn the user {user.mention}.")
                else:
                    raise ValueError(f"The reaction I detected was not ✅❌, I got {reaction_added}")

    @warn.command(name="set")
    @hf.is_submod()
    async def set_warn_notification_channel(self, ctx, channel_id: Optional[str] = None):
        """
        For the case where you wish to warn a user, but they have their DMs closed,
        you can choose to send the notification of the ban to the channel set
        by this command.

        Either go to the channel and type `;warn set` or specify a channel like `;warn set #channel_name` (or an ID)
        """
        if str(ctx.guild.id) not in self.bot.db['modlog']:
            return
        config: dict = self.bot.db['modlog'][str(ctx.guild.id)]

        if channel_id:
            if regex_result := re.search(r"^<?#?(\d{17,22})>?$", channel_id):
                channel = self.bot.get_channel(int(regex_result.group(1)))
            else:
                channel = None

            if not channel:
                await utils.safe_send(ctx, "I failed to find the channel you mentioned. Please try again.")
                return
        else:
            channel = ctx.channel

        config['warn_notification_channel'] = channel.id
        await utils.safe_send(ctx, f"Set warning channel for users with DMs disabled to {channel.mention}.")

    @commands.command(aliases=["cleanup", "bclr", "bc"])
    @commands.bot_has_permissions(manage_messages=True)
    @hf.is_submod()
    async def botclear(self, ctx, num_of_messages=10):
        """Usage: `;botclear num[default:10]`

        Deletes all bot messages in the last `num` messages.

        Defaults to 10, so just `;botclear` searches last ten messages."""
        try:
            num_of_messages = int(num_of_messages)
        except ValueError:
            await utils.safe_send(ctx, "Please input an integer number of messages")
            return
        if num_of_messages > 50:
            num_of_messages = 50
            await utils.safe_send(ctx, "Setting number of messages to the maximum of `50`.", delete_after=3)

        await ctx.channel.purge(limit=num_of_messages, check=lambda m: m.author.bot and m.content[0:7] != "Setting",
                                after=discord.utils.utcnow() - timedelta(minutes=60), oldest_first=False)
        try:
            await ctx.message.add_reaction('✅')
            await asyncio.sleep(1)
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        
    # command to calculate users with most incidents in last 30 days
    @commands.command(aliases=["topwarns", "topwarn", "topwarners", "topwarning"])
    @hf.is_submod()
    async def topwarnings(self, ctx: commands.Context, days=30):
        """Shows the top 10 users with the most warnings in the last 30 days."""
        config = self.bot.db['modlog'].get(str(ctx.guild.id), {})
        if not config:
            await utils.safe_send(ctx, "This guild does not have any modlogs")
            return
        top_warnings = Counter()
        for user_id, entries in config.items():
            if not isinstance(entries, list):
                continue
            user_warnings = 0
            for entry in entries:
                # "date": "2019/07/10 03:14 UTC"
                time_str = entry['date']
                time_datetime = datetime.strptime(time_str, "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
                if (discord.utils.utcnow() - time_datetime).days < days:
                    user_warnings += 1
            if user_warnings:
                top_warnings[user_id] = user_warnings
        sorted_warnings = sorted(top_warnings.items(), key=lambda x: x[1], reverse=True)
        top_ten = sorted_warnings[:10]
        emb = discord.Embed(title=f"Top 10 Users with Most Logs in Last {days} Days")
        emb.description = ""
        for user_id, warnings in top_ten:
            user: Union[discord.User, discord.Member] = ctx.guild.get_member(int(user_id))
            if not user:
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.NotFound:
                    pass
            try:
                ban_status = await ctx.guild.fetch_ban(user)
            except (discord.NotFound, discord.Forbidden):
                ban_status = None
            if user in ctx.guild.members:
                emb.description += f"- {user.display_name} / {user.name} ({user.mention}) - {warnings} logs\n"
            elif ban_status:
                emb.description += (f"- {user.display_name} / {user.name} - "
                                    f"{warnings} logs **(banned user)**\n")
            elif user and not user in ctx.guild.members:
                emb.description += f"- {user.name} - {warnings} logs (user not in server)\n"
            else:
                emb.description += f"- {user.id} - {warnings} logs (user could not be found)\n"
        await utils.safe_send(ctx, embed=emb)
    

async def setup(bot):
    await bot.add_cog(Submod(bot))
