from typing import Optional, List

import discord
from discord.ext import commands
from .utils import helper_functions as hf
import asyncio
from datetime import datetime, timedelta
import re

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

SP_SERV_ID = 243838819743432704
JP_SERVER_ID = 189571157446492161


class Submod(commands.Cog):
    """Help"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel':
            if not ctx.message.content.endswith("help"):  # ignore if it's the help command
                print("submod", ctx.message.content)
                await hf.safe_send(ctx, "Please set a mod channel using `;set_mod_channel`.")
            return
        return True

    @commands.command()
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    @hf.is_submod()
    async def ban(self, ctx, *, args):
        """Bans a user.  Usage: `;ban <list of users> [time #y#d#h] [reason]`
        Examples:
        - `;ban @Ryry013 being mean`
        - `;ban @Abelian 2d3h specify a time for a temporary ban`
        - `;ban 2d3h @Abelian swapping time and user mention`
        - `;ban 202995638860906496 414873201349361664 specify multiple IDs`

        Helpers on Sp-En server can ban users within an hour after they join the server.
        """
        if not args:
            await hf.safe_send(ctx, ctx.command.help)
            return

        args = hf.args_discriminator(ctx, args)

        user_ids = args.users
        reason = args.reason
        length = args.length
        time_string = args.time_string

        #
        # time_regex = re.compile(r'^((\d+)y)?((\d+)d)?((\d+)h)?$')  # group 2, 4, 6: years, days, hours
        # user_regex = re.compile(r'^<?@?!?(\d{17,22})>?$')  # group 1: ID
        # user_ids: List[int] = []  # list of users to ban
        # timed_ban = None
        #
        # # Iterate through beginning arguments taking all IDs and times until you reach the reason
        # for arg in args.copy():
        #     print(arg)
        #     if user_id_match := re.search(user_regex, arg):
        #         user_ids.append(int(user_id_match.group(1)))
        #         args.remove(arg)
        #     elif t := re.search(time_regex, arg):
        #         timed_ban = t
        #         args.remove(arg)
        #     else:
        #         break
        # reason = ' '.join(args)
        #
        # if not user_ids:
        #     await hf.safe_send(ctx, "I could not find where you specified the user. Please check your syntax.")
        #     return
        #
        # if timed_ban:
        #     if years := timed_ban.group(2):
        #         years = int(years)
        #     else:
        #         years = 0
        #
        #     if days := timed_ban.group(4):
        #         days = years * 365 + int(days)
        #     else:
        #         days = years * 365
        #
        #     if hours := timed_ban.group(6):
        #         hours = int(hours)
        #     else:
        #         hours = 0
        #
        #     length = [days, hours]
        #
        #     try:
        #         unban_time = discord.utils.utcnow() + timedelta(days=length[0], hours=length[1])
        #     except OverflowError:
        #         await hf.safe_send(ctx, "Give smaller number please :(")
        #         return
        #
        #     time_string = unban_time.strftime("%Y/%m/%d %H:%M UTC")
        #
        #     # """
        #     # if re.findall('^\d+d\d+h$', args[0]):  # format: #d#h
        #     #     length = timed_ban[0][:-1].split('d')
        #     #     length = [length[0], length[1]]
        #     # elif re.findall('^\d+d$', args[0]):  # format: #d
        #     #     length = [timed_ban[0][:-1], '0']
        #     # else:  # format: #h
        #     #     length = ['0', timed_ban[0][:-1]]
        #     # """
        #
        # else:
        #     length = []
        #     time_string = None

        targets: List[discord.Member] = []
        for user_id in user_ids:
            target = await hf.member_converter(ctx, user_id)
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
                        await hf.safe_send(ctx, f"I could not find the user {user_id}.")
                except discord.NotFound:
                    await hf.safe_send(ctx, f"I could not find the user {user_id}.")
                except ValueError:
                    await hf.safe_send(ctx, f"I could not find the user {user_id}.")

        if not targets:
            await hf.safe_send(ctx, "I couldn't resolve any users to ban. Please check the IDs you gave again.")
            return

        if not reason:
            reason = '(no reason given)'

        text = f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** XX"
        new_text = text.replace("XX", reason)
        if len(new_text) > 512:
            await hf.safe_send(ctx, "Discord only allows bans with a length of 512 characters. With my included "
                                    f"author tag, you are allowed {513 - len(text)} characters. Please reduce the "
                                    f"length of your ban message. ")
            return

        # this memorial exists to forever remember the robot head, may you rest in peace ['_']
        # this comment exists to wonder what the hell the robot head was...
        for target in targets:
            if hasattr(target, "joined_at"):  # will be false if the user is not in the server
                joined_at = discord.utils.utcnow() - target.joined_at
            else:
                joined_at = timedelta(minutes=61)  # arbitrarily bigger than 60 to fail the conditional

            # Allow server helpers on Spanish server to ban users who joined within last 60 minutes
            if not (ctx.guild.id == SP_SERV_ID and
                    ctx.guild.get_role(258819531193974784) in ctx.author.roles and
                    joined_at < timedelta(minutes=60)) and not \
                    hf.admin_check(ctx):
                raise commands.MissingPermissions(['ban_members'])

        em = discord.Embed(title=f"You've been banned from {ctx.guild.name}")
        if length:
            em.description = f"You will be unbanned automatically at {time_string} " \
                             f"(in {length[0]} days and {length[1]} hours)"
        else:
            em.description = "This ban is indefinite."
        silent = False
        if reason != '(no reason given)':
            if '-silent' in reason or '-s' in reason:
                silent = True
                reason = reason.replace('-silent ⁣', '').replace('-s ', '')
                reason = '⁣' + reason  # no width space = silent
            if '-c' in reason:
                reason = '⠀' + reason  # invisible space = crosspost
            em.add_field(name="Reason:", value=reason)
        await hf.safe_send(ctx, f"You are about to ban {', '.join([t.mention for t in targets])}: ", embed=em)
        msg2 = f"Do you wish to continue?  Options:\n" \
               f"⠀・ `Yes` Silently ban the user\n" \
               f"⠀・ `Send` Ban the user and send them the above notification\n" \
               f"⠀・ `No` Cancel the ban\n" \
               f"⠀・ Add `delete` or `del` to delete last 24 hours of messages (example `send del`)\n"

        are = self.bot.get_guild(257984339025985546)
        if are:
            if ctx.author in are.members:
                try:
                    if 'crosspost' in self.bot.db['bans'][str(ctx.guild.id)]:
                        if not reason.startswith('⁣') and str(ctx.guild.id) in self.bot.db['bans']:  # no width space
                            if self.bot.db['bans'][str(ctx.guild.id)]['crosspost']:
                                crosspost_check = 1  # to cancel crosspost
                                msg2 += "⠀・ `Yes/Send -s` Do not crosspost this ban"
                        if not reason.startswith('⠀') and str(ctx.guild.id) in self.bot.db['bans']:  # invisible space
                            if not self.bot.db['bans'][str(ctx.guild.id)]['crosspost']:
                                crosspost_check = 2  # to specially crosspost
                                msg2 += "⠀・ `Yes/Send -c` Specially crosspost this ban"
                except KeyError:
                    pass
        msg2 = await hf.safe_send(ctx, msg2)
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=40.0,
                                          check=lambda x: x.author == ctx.author and
                                          x.content.casefold()[:4] in ['yes', 'yes ', 'no', 'send'])
        except asyncio.TimeoutError:
            try:
                await msg2.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
            await hf.safe_send(ctx, f"Timed out.  Canceling ban.")
            return
        content = msg.content.casefold()
        if content == 'no':
            try:
                await msg2.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
            await hf.safe_send(ctx, f"Canceling ban")
            return

        try:
            await msg2.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        text = text.replace("XX", reason)

        if content.endswith('-s'):  # these will be parsed in the on_member_ban event in logger.py
            text = '⁣' + text
        if content.endswith('-c'):
            text = '⠀' + text

        if 'delete' in content or 'del' in content:
            delete = 1
        else:
            delete = 0

        successes = []
        for target in targets:
            try:
                await ctx.guild.ban(target, reason=text, delete_message_days=delete)
                successes.append(target)
            except discord.Forbidden:
                await hf.safe_send(ctx, f"I couldn't ban {target.mention}. They're probably above me in the role list.")
                continue

            if 'send' in content:
                try:
                    await hf.safe_send(target, embed=em)
                except discord.Forbidden:
                    await hf.safe_send(ctx, f"{target.mention} has PMs disabled so I didn't send the notification.")

            if length:
                config = self.bot.db['bans'].setdefault(str(ctx.guild.id),
                                                        {'enable': False, 'channel': None, 'timed_bans': {}})
                timed_bans = config.setdefault('timed_bans', {})
                timed_bans[str(target.id)] = time_string

            if length:
                length_str = f"{length[0]}d{length[1]}h"
            else:
                length_str = None
            if reason.startswith("*by*"):
                reason = reason.replace(f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** ", '')
            modlog_entry = hf.ModlogEntry(event="Ban", user=target,
                                          guild=ctx.guild, ctx=ctx,
                                          length=length_str, reason=reason,
                                          silent=silent)
            modlog_entry.add_to_modlog()
        await hf.safe_send(ctx, f"Successfully banned {', '.join([member.mention for member in successes])}")

    @commands.command()
    @hf.is_admin()
    async def set_submod_role(self, ctx, *, role_name):
        """Set the submod role for your server.  Type the exact name of the role like `;set_submod_role Mods`."""
        config = hf.database_toggle(ctx, self.bot.db['submod_role'])
        if 'enable' in config:
            del (config['enable'])
        submod_role: Optional[discord.Role] = discord.utils.find(lambda role: role.name == role_name, ctx.guild.roles)
        if not submod_role:
            await hf.safe_send(ctx, "The role with that name was not found")
            return None
        config['id'] = submod_role.id
        await hf.safe_send(ctx, f"Set the submod role to {submod_role.name} ({submod_role.id})")

    @commands.command(aliases=['setsubmodchannel'])
    @hf.is_admin()
    async def set_submod_channel(self, ctx, channel_id=None):
        """Sets the channel for submods"""
        if not channel_id:
            channel_id = ctx.channel.id
        self.bot.db['submod_channel'][str(ctx.guild.id)] = channel_id
        await hf.safe_send(ctx, f"Set the submod channel for this server as {ctx.channel.mention}.")

    @commands.group(invoke_without_command=True, aliases=['w'])
    @hf.is_submod()
    async def warn(self, ctx, *, args):
        """Log a mod incident"""
        args = hf.args_discriminator(ctx, args)

        user_ids = args.users
        reason = args.reason

        # If silent, remove -s from reason if it's there
        if silent := "-s" in reason:
            reason = reason.replace(' -s', '').replace('-s ', '').replace('-s', '')

        if not reason:
            await hf.safe_send(ctx, "You must include a reason in your warning, please try again.")
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
                        await hf.safe_send(ctx, f"The user {user} is not a member of this server so I couldn't "
                                                f"send the warning. I am aborting their warning.")
                        continue  # don't let code get to the addition of ModlogEntry object

            if not user:
                await hf.safe_send(ctx, f"I could not find the user {user_id}.  For warnings and mutes, "
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

            emb = hf.red_embed(f"Warned on {ctx.guild.name} server")
            emb.color = 0xffff00  # embed ff8800
            emb.add_field(name="User", value=f"{user.name} ({user.id})", inline=False)

            if silent:
                emb.description = "Log *(This incident was not sent to the user)*"
            else:
                emb.description = "Warning"

            # Add reason to embed
            modlog_entry.reason = reason
            emb.add_field(name="Reason", value=reason, inline=False)

            # Send notification to warned user if not a log
            if not modlog_entry.silent:
                try:
                    await hf.safe_send(user, embed=emb)
                # if bot fails to send message to user, offer to send warning to a public channel
                except discord.Forbidden:
                    if notif_channel_id := self.bot.db['modlog'] \
                            .get(str(ctx.guild.id), {}) \
                            .get("warn_notification_channel", None):
                        notif_channel = self.bot.get_channel(notif_channel_id)
                    else:
                        await hf.safe_send(ctx, "I was unable to send the warning to this user. "
                                                "In the future you can type `;warn set` in a text channel in your "
                                                "server and I will offer to send a public warning to the user in "
                                                "these cases.")
                        continue

                    if notif_channel:
                        question = await hf.safe_send(ctx, f"I could not send a message to {user.mention}. "
                                                           f"Would you like to send a pubic warning to "
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
                            await hf.safe_send(ctx, f"I will not warn the user {user.mention}.")
                            continue
                        else:
                            if str(reaction_added) == '✅':
                                try:
                                    await hf.safe_send(notif_channel,
                                                       f"{user.mention}: Due to your privacy settings "
                                                       f"disabling messages from bots, we are "
                                                       f"delivering this warning in a "
                                                       f"public channel. If you believe this to be an "
                                                       f"error, please contact a mod.",
                                                       embed=emb)
                                except discord.Forbidden:
                                    await hf.safe_send(ctx, "I can't send messages to the channel you have marked "
                                                            "in this server as the warn notifications channel. Please "
                                                            "go to a new channel and type `;warns set`.")
                                    continue
                            else:
                                await hf.safe_send(ctx, f"I will not warn the user {user.mention}.")
                                continue
                except discord.HTTPException:
                    await hf.safe_send(ctx, f"I cannot send messages to {user.mention}.")
                    continue

            # Add this footer/field only after potentially sending warn notification to user
            if silent:
                footer_text = f"Logged by {ctx.author.name} ({ctx.author.id})"
            else:
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
                    await hf.safe_send(modlog_channel, embed=emb)

            # Send notification (confirmation) to current channel
            await hf.safe_send(ctx, embed=emb)

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
                await hf.safe_send(ctx, "I failed to find the channel you mentioned. Please try again.")
                return
        else:
            channel = ctx.channel

        config['warn_notification_channel'] = channel.id

    @commands.command(aliases=["cleanup", "bclr"])
    @commands.bot_has_permissions(manage_messages=True)
    @hf.is_submod()
    async def botclear(self, ctx, num_of_messages=10):
        """Usage: `;botclear num[default:10]`

        Deletes all bot messages in the last `num` messages.

        Defaults to 10, so just `;botclear` searches last ten messages."""
        try:
            num_of_messages = int(num_of_messages)
        except ValueError:
            await hf.safe_send(ctx, "Please input an integer number of messages")
            return
        if num_of_messages > 50:
            num_of_messages = 50
            await hf.safe_send(ctx, "Setting number of messages to the maximum of `50`.", delete_after=3)

        await ctx.channel.purge(limit=num_of_messages, check=lambda m: m.author.bot and m.content[0:7] != "Setting",
                                after=discord.utils.utcnow() - timedelta(minutes=60))
        try:
            await ctx.message.add_reaction('✅')
            await asyncio.sleep(1)
            await ctx.message.delete()
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(Submod(bot))
