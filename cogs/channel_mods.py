from copy import deepcopy
from typing import Optional, Union, List
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from .utils import helper_functions as hf
from .utils.helper_functions import format_interval
from cogs.utils.BotUtils import bot_utils as utils
import re

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SP_SERV = 243838819743432704
JP_SERV = 189571157446492161


async def fix_join_history_invite(ctx: commands.Context, user_id: int, join_history: dict) -> dict:
    """Fix the invite used in join_history database for the year period of bugged logging"""
    if not join_history:
        return join_history
    notification_message_url = join_history['jump_url']
    # example: https://discord.com/channels/266695661670367232/321837027295363073/858265556297187328
    guild_id, channel_id, message_id = map(
        int, notification_message_url.split('/')[-3:])
    channel = ctx.bot.get_channel(channel_id)

    if not channel:
        return join_history

    try:
        message = await channel.fetch_message(message_id)
    except (discord.NotFound, discord.HTTPException):
        return join_history

    if not message.embeds:
        return join_history

    embed = message.embeds[0]
    invite_field = discord.utils.get(embed.fields, name="Invite link used")
    if not invite_field:
        return join_history
    if invite_field.value == "Through server discovery":
        used_invite = "Through server discovery"
    else:
        used_invite = invite_field.value.replace("`", "").split(' ')[0]
    join_history['invite'] = used_invite
    return join_history


class ChannelMods(commands.Cog):
    """Commands that channel mods can use in their specific channels only. For adding channel \
    mods, see `;help channel_mod`. Submods and admins can also use these commands."""

    def __init__(self, bot):
        self.bot: commands.Bot = bot

    async def cog_load(self):
        await self.test_role_command()

    async def cog_check(self, ctx):
        # only usable in guilds
        if not ctx.guild:
            return

        # mod channel must be set
        if str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel':
            # ignore if it's the help command
            if not ctx.message.content.endswith("help"):
                await utils.safe_send(ctx, "Please set a mod channel using `;set_mod_channel`.")
            return

        # submods can use all channel mod commands
        if hf.submod_check(ctx):
            return True

        # check if helper
        if hf.helper_check(ctx):
            return True

        # special SP server voice helper role
        if ctx.guild:
            voice_helper_role = ctx.guild.get_role(1039366362851721287)
            if voice_helper_role in ctx.author.roles:
                return True

        # voice mods...
        if ctx.author.id in self.bot.db['voicemod'].get(ctx.guild.id, []):
            # ...can use staffping
            if ctx.command.name == "staffping":
                return True

            # ...can use commands in text channels with the word "voice" in them
            elif "voice" in ctx.channel.name.casefold() or "vc" in ctx.channel.name.casefold():
                return True

            # ...can use commands in the text channels associated with voice channels
            elif isinstance(ctx.channel, discord.VoiceChannel):
                return True

        # able to use commands (mainly modlog) in staff category in spanish server
        if ctx.channel.category.id == 817780000807583774:
            return True

    helper = app_commands.Group(
        name="helper", description="Commands to configure server helpers", guild_ids=[SP_SERV])

    @helper.command(name="role")
    @app_commands.default_permissions()
    async def set_helper_role(self, itx: discord.Interaction, *, role: discord.Role):
        """Set the helper role for your server."""
        config = hf.database_toggle(itx.guild, self.bot.db['helper_role'])
        if 'enable' in config:
            del config['enable']

        config['id'] = role.id
        await itx.response.send_message(f"Set the helper role to {role.name} ({role.id})")

    @helper.command(name="channel")
    @app_commands.default_permissions()
    async def set_helper_channel(self, itx: discord.Interaction, channel: discord.TextChannel = None):
        """Sets the channel for helpers"""
        if not channel:
            channel = itx.channel
        self.bot.db['helper_channel'][str(itx.guild.id)] = channel.id
        await itx.response.send_message(f"Set the helper channel for this server as {channel.mention}.")

    @commands.command(name="delete", aliases=['del'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_messages=True)
    async def msg_delete(self, ctx, *ids):
        """A command to delete messages for submods.  Usage: `;del <list of IDs>`\n\n
        Example: `;del 589654995956269086 589654963337166886 589654194189893642`"""
        try:
            await ctx.message.delete()
            try:
                await utils.safe_send(ctx.author,
                                      f"I'm gonna delete your message to potentially keep your privacy, "
                                      f"but in case "
                                      f"something goes wrong, here was what you sent: \n{ctx.message.content}")
            except (discord.Forbidden, discord.HTTPException):
                pass
        except (discord.NotFound, AttributeError):
            pass

        msg: Optional[discord.Message] = None
        msgs: List[discord.Message] = []
        failed_ids: List[int] = []
        invalid_ids: List[int] = []

        if len(ids) == 1:
            if not 17 < len(ids[0]) < 22:
                try:
                    int(ids[0])
                except ValueError:
                    pass
                else:
                    await utils.safe_send(ctx, "This is a command to delete a certain message by specifying its "
                                               f"message ID. \n\nMaybe you meant to use `;clear {ids[0]}`?")

        # search ctx.channel for the ids
        for msg_id in ids:
            try:
                msg_id = int(msg_id)
                if not 17 < len(str(msg_id)) < 22:
                    raise ValueError
                msg = await ctx.channel.fetch_message(msg_id)
                msgs.append(msg)
            except discord.NotFound:
                failed_ids.append(msg_id)
            except (discord.HTTPException, ValueError):
                invalid_ids.append(msg_id)

        if invalid_ids:
            await utils.safe_send(ctx, f"The following IDs were not properly formatted: "
                                  f"`{'`, `'.join([str(i) for i in invalid_ids])}`")

        # search every channel, not just ctx.channel for the missing IDs
        if failed_ids:
            for channel in ctx.guild.text_channels:
                for msg_id in failed_ids.copy():
                    try:
                        msg = await channel.fetch_message(msg_id)
                        msgs.append(msg)
                        failed_ids.remove(msg_id)
                    except discord.NotFound:
                        break
                    except discord.Forbidden:
                        break
                if not failed_ids:
                    break
        if failed_ids:
            await utils.safe_send(ctx, f"Unable to find ID(s) `{'`, `'.join([str(i) for i in failed_ids])}`.")

        if not msgs:
            return  # no messages found

        emb = discord.Embed(title=f"Deleted messages in #{msg.channel.name}", color=discord.Color(int('ff0000', 16)),
                            description="")
        embeds = []
        for msg_index in range(len(msgs)):
            msg = msgs[msg_index]
            jump_url = ''
            async for msg_history in msg.channel.history(limit=1, before=msg):
                jump_url = msg_history.jump_url
            try:
                await msg.delete()
            except discord.NotFound:
                continue
            except discord.Forbidden:
                await ctx.send(f"I lack the permission to delete messages in {msg.channel.mention}.")
                return
            if msg.embeds:
                for embed in msg.embeds:
                    if embed.title or embed.description or embed.fields:
                        embeds.append(embed)
                        emb.add_field(
                            name="Embed deleted", value=f"Content shown below ([Jump URL]({jump_url}))")
            split_message_content = utils.split_text_into_segments(
                msg.content, 900)
            for index, segment in enumerate(split_message_content):
                if not segment:
                    continue
                if index == 0:
                    if len(split_message_content) == 1:
                        emb.add_field(name=f"Message {msg_index} by {str(msg.author)} ({msg.author.id})",
                                      value=f"{segment} ([Jump URL]({jump_url}))")
                    else:
                        emb.add_field(name=f"Message {msg_index} by {str(msg.author)} ({msg.author.id})",
                                      value=f"{segment}")
                elif index == len(split_message_content) - 1:
                    emb.add_field(name="continued",
                                  value=f"{segment} ([Jump URL]({jump_url}))")
                else:
                    emb.add_field(name="continued", value=f"{segment}")
            if not msg.content:
                emb.add_field(name=f"Message {msg_index} by {str(msg.author)} ({msg.author.id})",
                              value=f"Message had no content. ([Jump URL]({jump_url}))")

            if msg.attachments:
                emb.description = "Attachments in below thread"
            # if msg.attachments:
            #     x = [f"{att.filename}: {att.proxy_url}" for att in msg.attachments]
            #     if not msg.content:
            #         name = f"Message attachments by {str(msg.author)} (might expire soon):"
            #     else:
            #         name = "Attachments (might expire soon):"
            #     emb.add_field(name=name, value='\n'.join(x))
            emb.timestamp = msg.created_at
        emb.set_footer(text=f"Deleted by {str(ctx.author)} - Message sent at:")
        if str(ctx.guild.id) in self.bot.db['submod_channel']:
            channel = self.bot.get_channel(
                self.bot.db['submod_channel'][str(ctx.guild.id)])
            if not channel:
                await utils.safe_send(ctx, "I couldn't find the channel you had set as your submod channel. Please "
                                           "set it again.")
                del self.bot.db['submod_channel'][str(ctx.guild.id)]
                return
        elif str(ctx.guild.id) in self.bot.db['mod_channel']:
            channel = self.bot.get_channel(
                self.bot.db['mod_channel'][str(ctx.guild.id)])
            if not channel:
                await utils.safe_send(ctx, "I couldn't find the channel you had set as your submod channel. Please "
                                           "set it again.")
                del self.bot.db['submod_channel'][str(ctx.guild.id)]
                return
        else:
            await utils.safe_send(ctx, "Please set either a mod channel or a submod channel with "
                                       "`;set_mod_channel` or `;set_submod_channel`")
            return

        log_message = await utils.safe_send(channel, str(msg.author.id), embed=emb)
        if not log_message:
            # error
            await utils.safe_send(ctx, "I couldn't send the log message to the submod channel.")
            return
        for msg in msgs:
            await hf.send_attachments_to_thread_on_message(log_message, msg)
        if embeds:
            for embed in embeds:
                if not embed:
                    continue
                await utils.safe_send(channel, embed=embed)

    @commands.command(name="setdelay", aliases=["delay", "sd", "slowmode"])
    @commands.bot_has_permissions(send_messages=True, manage_channels=True)
    async def setdelay(self, ctx, time_in: str = ''):
        """
        Set slowmode for a channel.
        Usage: `;setdelay/sd/delay/slowmode <time: 1h, 3h10m, etc>`.
        Examples:
        - `;slowmode 5s`  Sets five second slowmode
        - `;sd 2h`  Sets two hour slowmode
        - `;delay 0` (or `0s`, `0m`, `0h`)  Disables slowmode
        """
        if not time_in:
            # if no argument was passed in
            # this will cause slowmode to be disabled
            time_in = '0s'

        if re.search(r'^\d+$', time_in):
            # they passed a single number as argument
            time_in = time_in + 's'
            # default to seconds

        if len(time_in) == 2 and time_in[0] == '0':
            time_in = "0s"  # to be checked at final confirmation message again

        time_string, (days, hours, minutes, seconds) = hf.parse_time(
            time_in, return_seconds=True)
        if not time_string:
            await utils.safe_reply(ctx,
                                   "I could not parse your input. Please see the following.\n" + ctx.command.help)
            return
        total_seconds = days * 86400 + hours * 3600 + minutes * 60 + seconds
        if not (0 <= total_seconds <= 21600):
            await utils.safe_reply(ctx, "Slowmode must be between 0s and 6h.")
            return
        await ctx.channel.edit(slowmode_delay=total_seconds)
        if time_in == '0s':
            await utils.safe_reply(ctx, "Turned off slowmode!")
        else:
            await utils.safe_reply(ctx, f"Set the slowmode delay in this channel to {time_in}!")

    @commands.command(name="pin")
    # @commands.bot_has_permissions(send_messages=True, manage_messages=True)
    async def pin_message(self, ctx, *args):
        """Pin a message. Type the message ID afterwards like `;pin 700749853021438022` or include no ID to pin
        the last message in the channel (just type `;pin`). To pin a message from another channel, type either
        `;pin <channel_id> <message_id>` or `;pin <channel_id>-<message_id>` (with a dash in the middle)."""
        to_be_pinned_msg = None
        if len(args) == 0:
            async for message in ctx.channel.history(limit=2):
                if message.content == ';pin':
                    continue
                to_be_pinned_msg = message
        elif len(args) == 1:
            if re.search(r'^\d{17,22}$', args[0]):
                try:
                    to_be_pinned_msg = await ctx.channel.fetch_message(args[0])
                except discord.NotFound:
                    await utils.safe_send(ctx, "I couldn't find the message you were looking for.")
                    return
            elif re.search(r'^\d{17,22}-\d{17,22}$', args[0]):
                channel_id = int(args[0].split('-')[0])
                channel = ctx.guild.get_channel_or_thread(channel_id)
                if not channel:
                    await utils.safe_send(ctx, "I couldn't find the channel you specified!")
                    return
                message_id = int(args[0].split('-')[1])
                to_be_pinned_msg = await channel.fetch_message(message_id)
            else:
                await utils.safe_send(ctx, "Please input a valid ID")
                return
        elif len(args) == 2:
            channel_id = int(args[0])
            channel = ctx.guild.get_channel_or_thread(channel_id)
            if not channel:
                await utils.safe_send(ctx, "I couldn't find the channel you specified!")
                return
            message_id = int(args[1])
            to_be_pinned_msg = await channel.fetch_message(message_id)
        else:
            await utils.safe_send(ctx, "You gave too many arguments!")
            return

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        if to_be_pinned_msg.pinned:
            if not to_be_pinned_msg.author.bot:
                await utils.safe_send(ctx, "Unfortunately, this command can only unpin bot messages.", delete_after=5.0)
                return
            try:
                await to_be_pinned_msg.unpin()
                await utils.safe_send(ctx, "I've unpinned that message.", delete_after=5.0)
            except discord.Forbidden:
                await utils.safe_send(ctx, "I lack the permission to unpin messages in this channel.", delete_after=5.0)
        else:
            try:
                await to_be_pinned_msg.pin()
            except discord.Forbidden:
                await utils.safe_send(ctx, "I lack the permission to pin messages in this channel", delete_after=5.0)

    @commands.command()
    async def log(self, ctx: commands.Context, *, args="None"):
        """Same as `;warn` but it adds `-s` into the reason which makes it just silently log the warning
        without sending a notification to the user."""
        warn = self.bot.get_command('warn')
        if args:
            args += ' -s'
        else:
            args = ' -s'
        # noinspection PyTypeChecker
        emb = await ctx.invoke(warn, args=args)
        return emb

    @commands.command()
    async def evidence(self, ctx: commands.Context, *, args):
        """This command will add evidence to the last log of a user.
        Example: `;evidence 123456789012345678 <link to message or picture>`
        Note, if it is a link to an image hosted in Discord, the link might break so message links are good."""
        if not args:
            await utils.safe_reply(ctx, "Please provide a user ID and a link to the evidence.")
            return
        split_args = args.split()

        # if there's only one argument, it should be the evidence; search for the ID in the message history
        if len(split_args) == 1:
            try:
                # works if this is the ID
                int(split_args[0])
            except ValueError:
                id = await self.check_for_id_reference(ctx)
                if not id:
                    await utils.safe_reply(ctx, "Please provide a valid user ID.")
                    return
                else:
                    user_id = id
                    user_id_str = str(user_id)
                    # since there was only one arg passed and it was the evidence
                    evidence = split_args[0]
            else:
                # int(id) worked, so no evidence was given
                await utils.safe_reply(ctx, "Please provide a link to the evidence.")
                return
        else:
            # there were multiple arguments passed, first was ID, rest was evidence
            # take just the evidence
            user_id_str, *_ = split_args
            # remove the ID from the original args string, and then use that over the split verison (to preserve new
            # lines inserted in original command invocation)
            args_without_id = args[len(user_id_str) + 1:]
            evidence = args_without_id

        # check to make sure the ID is actually an ID
        if not re.match(r'^\d{17,22}$', user_id_str):
            possible_id = await self.check_for_id_reference(ctx)
            if possible_id:
                user_id = possible_id
                evidence = args
            else:
                await utils.safe_reply(ctx, "Please provide a valid user ID.")
                return
        else:
            user_id = int(user_id_str)

        url = True
        if not re.match(r'^https?://', evidence):
            url = False

        # Replace any lone instance of the word "ctx" in the evidence with a link to the jump_url of the ctx message
        evidence = re.sub(
            r'\bctx\b', f"[(Message Link)]({ctx.message.jump_url})", evidence)

        modlog = self.bot.db['modlog'].get(
            str(ctx.guild.id), {}).get(str(user_id), [])
        if not modlog:
            await utils.safe_reply(ctx, "I couldn't find any logs for that user.")
            return

        most_recent_log = modlog[-1]
        if url:
            most_recent_log['reason'] += f"\n- [`Evidence`](<{evidence}>)"
        else:
            evidence = evidence.replace('\n', '\n  ')
            most_recent_log['reason'] += f"\n- {evidence}"

        await utils.safe_reply(ctx.message, f"Added evidence to the last log for {user_id} (<@{user_id}>). "
                               f"New reason: "
                               f"\n>>> {most_recent_log['reason']}")

    async def check_for_id_reference(self, ctx: commands.Context):
        """This will check the last five messages for any message starting with ;log, ;mute, or ;warn and pull
        the ID out"""
        async for message in ctx.channel.history(limit=15, oldest_first=False):
            if message.author == ctx.author:
                if message.content.startswith((';log', ';mute', ';warn', ';ban')):
                    id_str = message.content.split()[1]
                    # remove <@...> if it's there
                    id_str = re.sub(r'<@!?(\d+)>', r'\1', id_str)
                    try:
                        id = int(id_str)
                    except ValueError:
                        return
                    else:
                        return id

    # @commands.command(aliases=['channel_helper', 'cm', 'ch'])
    # @hf.is_admin()
    # async def channel_mod(self, ctx, *, user):
    #     """Assigns a channel mod. You must do this command in the channel you
    #     where you wish to assign them as a channel helper.
    #
    #     Usage (in the channel): `;cm <user name>`"""
    #     config = self.bot.db['channel_mods'].setdefault(str(ctx.guild.id), {})
    #     user = await utils.member_converter(ctx, user)
    #     if not user:
    #         await ctx.invoke(self.list_channel_mods)
    #         return
    #     if str(ctx.channel.id) in config:
    #         if user.id in config[str(ctx.channel.id)]:
    #             await utils.safe_send(ctx, "That user is already a channel mod in this channel.")
    #             return
    #         else:
    #             config[str(ctx.channel.id)].append(user.id)
    #     else:
    #         config[str(ctx.channel.id)] = [user.id]
    #     await ctx.message.delete()
    #     await utils.safe_send(ctx, f"Set {user.name} as a channel mod for this channel", delete_after=5.0)

    # @commands.command(aliases=['list_channel_helpers', 'lcm', 'lch'])
    # async def list_channel_mods(self, ctx):
    #     """Lists current channel mods"""
    #     output_msg = '```md\n'
    #     if str(ctx.guild.id) not in self.bot.db['channel_mods']:
    #         return
    #     config = self.bot.db['channel_mods'][str(ctx.guild.id)]
    #     for channel_id in config.copy():
    #         channel = self.bot.get_channel(int(channel_id))
    #         if not channel:
    #             await utils.safe_send(ctx, f"Removing deleted channel {channel_id} from list with helpers "
    #                                     f"{', '.join([str(i) for i in config[channel_id]])}")
    #             del config[channel_id]
    #             continue
    #         output_msg += f"#{channel.name}\n"
    #         for user_id in config[channel_id]:
    #             user = self.bot.get_user(int(user_id))
    #             if not user:
    #                 await utils.safe_send(ctx, f"<@{user_id}> was not found.  Removing from list...")
    #                 config[channel_id].remove(user_id)
    #                 continue
    #             output_msg += f"{user.display_name}\n"
    #         output_msg += '\n'
    #     output_msg += '```'
    #     await utils.safe_send(ctx, output_msg)
    #
    # @commands.command(aliases=['rcm', 'rch'])
    # @hf.is_admin()
    # async def remove_channel_mod(self, ctx, user):
    #     """Removes a channel mod. You must do this in the channel they're a channel mod in.
    #
    #     Usage: `;rcm <user name>`"""
    #     config = self.bot.db['channel_mods'].setdefault(str(ctx.guild.id), {})
    #     user_obj = await utils.member_converter(ctx, user)
    #     if user_obj:
    #         user_id = user_obj.id
    #         user_name = user_obj.name
    #     else:
    #         try:
    #             user_id = int(user)
    #             user_name = user
    #         except ValueError:
    #             await utils.safe_send(ctx, "I couldn't parse the user you listed and couldn't find them in the server. "
    #                                     "Please check your input.", delete_after=5.0)
    #             return
    #         await utils.safe_send(ctx, "Note: I couldn't find that user in the server.", delete_after=5.0)
    #     if str(ctx.channel.id) in config:
    #         if user_id not in config[str(ctx.channel.id)]:
    #             await utils.safe_send(ctx, "That user is not a channel mod in this channel. You must call this command "
    #                                     "in their channel.")
    #             return
    #         else:
    #             config[str(ctx.channel.id)].remove(user_id)
    #             if not config[str(ctx.channel.id)]:
    #                 del config[str(ctx.channel.id)]
    #     else:
    #         return
    #     await ctx.message.delete()
    #     await utils.safe_send(ctx, f"Removed {user_name} as a channel mod for this channel", delete_after=5.0)

    @commands.check(lambda x: x.guild.id in [SP_SERV, JP_SERV])
    @commands.command(aliases=['staff'])
    async def staffrole(self, ctx: commands.Context):
        """You can add/remove the staff role from yourself with this"""
        if ctx.guild.id == SP_SERV:
            staffrole = ctx.guild.get_role(642782671109488641)
        else:
            staffrole = ctx.guild.get_role(240647591770062848)
        if not staffrole:
            await utils.safe_reply(ctx.message, "I couldn't find the staff role for this server.")
            return

        if staffrole in ctx.author.roles:
            await ctx.author.remove_roles(staffrole)
            await utils.safe_send(ctx, "I've removed the staff role from you")
        else:
            try:
                await ctx.author.add_roles(staffrole)
            except discord.Forbidden:
                await utils.safe_send(ctx,
                                      "I lack the ability to attach the staff role. Please make sure I have the ability "
                                      "to manage roles, and that the staff role isn't above my highest user role.")
                return
            await utils.safe_send(ctx, "I've given you the staff role.")

    @commands.group(invoke_without_command=True)
    async def staffping(self, ctx):
        """Subscribe yourself to staff ping notifications in your DM for when the staff role is pinged on this server"""
        if str(ctx.guild.id) not in self.bot.db['staff_ping']:
            self.bot.db['staff_ping'][str(ctx.guild.id)] = {'users': []}
        subscribed_users = self.bot.db['staff_ping'][str(
            ctx.guild.id)]['users']
        if ctx.author.id in subscribed_users:
            subscribed_users.remove(ctx.author.id)
            await utils.safe_send(ctx, "You will no longer receive notifications for staff pings.")
        else:
            subscribed_users.append(ctx.author.id)
            await utils.safe_send(ctx, "You will receive notifications for staff pings.")

    @staffping.command(name="set")
    async def staffping_set(self, ctx, input_id=None):
        """Does one of two things:
        1) Sets notification channel for pings to a selected channel
        ⠀(`;staffping set <channel_mention>`)
        ⠀(if no channel is specified, sets to current channel)
        2) Sets the watched role for staff pings
        ⠀(specify an ID or role: `;staffping set <role mention/ID>`)
        If neither are set, it will watch for the mod role (`;set_mod_role`) and notify to the
        submod channel (`;set_submod_channel`)."""
        if str(ctx.guild.id) not in self.bot.db['staff_ping']:
            await ctx.invoke(self.staffping)

        config = self.bot.db['staff_ping'][str(ctx.guild.id)]

        if not input_id:  # nothing, assume setting channel to current channel
            config['channel'] = ctx.channel.id
            await utils.safe_send(ctx, f"I've set the notification channel for staff pings as {ctx.channel.mention}.")
            return

        channel = role = None
        # a channel or role mention/ID
        if regex := re.search(r"^<?#?@?&?(\d{17,22})>$", input_id):
            object_id = int(regex.group(1))
            channel = self.bot.get_channel(object_id)
            role = ctx.guild.get_role(object_id)
            if channel:
                config['channel'] = channel.id
                await utils.safe_send(ctx, f"I've set the notification channel for staff pings to {channel.mention}.")
            elif role:
                config['role'] = role.id
                await utils.safe_send(ctx, f"I've set the watched staff role to **{role.name}** (`{role.mention}`)")

        if not channel and not role:
            await utils.safe_send(ctx, "I couldn't figure out what you wanted to do.")
            await utils.safe_send(ctx, ctx.command.help)

    # external-facing user command
    @commands.command(aliases=['r', 't', 'tag'])
    async def role(self, ctx, *, args):
        if ctx.guild.id != SP_SERV:
            return

        args = args.split()

        if len(args) < 1:
            await utils.safe_reply(ctx, "Gimme something at least! Run `;help role`")
            return

        user = await utils.member_converter(ctx, args[0])
        if not user:
            await utils.safe_reply(ctx, "I couldn't find the user you were looking for.")
            return

        langs = set(args[1:]) if len(args) > 1 else set()
        user_roles = {role.id for role in user.roles}

        try:
            to_add_lang_roles, to_remove, final_roles = await self.process_role_changes(ctx.guild, user_roles, langs)
        except ValueError as e:
            await utils.safe_reply(ctx, f"Error: {e}")
            return
        if not to_add_lang_roles:
            await utils.safe_reply(ctx, "There was an error with one of the roles you tried to specify.")
            return

        try:
            if to_remove:
                await user.remove_roles(*to_remove)
            if to_add_lang_roles:
                await user.add_roles(*to_add_lang_roles)
        except discord.Forbidden:
            return utils.red_embed("Permission error: Can't manage these roles.")

        msg = f"Role changes for {user.display_name}:\n"
        if to_add_lang_roles:
            sorted_adds = sorted(
                to_add_lang_roles, key=lambda x: x.position, reverse=True)
            adds = '\n'.join([f'＋ {r.mention}' for r in sorted_adds])
            msg += f"__Added__\n{adds}\n"
        if to_remove:
            sorted_removes = sorted(
                to_remove, key=lambda x: x.position, reverse=True)
            removes = '\n'.join([f'－ {r.mention}' for r in sorted_removes])
            msg += f"__Removed__\n{removes}\n"

        sorted_current = sorted(
            final_roles, key=lambda x: x.position, reverse=True)
        current = '\n'.join([f'- {r.mention}' for r in sorted_current])
        msg += f"\n__Current roles__\n{current or '- None'}"
        embed = utils.green_embed(msg)
        await utils.safe_reply(ctx, embed=embed)

    # internal logic function
    async def process_role_changes(self, guild: discord.Guild,
                                   user_roles_in: Union[set[str], set[int]],
                                   langs: set[str]
                                   ) -> tuple[set[discord.Role], set[discord.Role], set[discord.Role]]:
        role_ids = {
            'english': 243853718758359040,
            'spanish': 243854128424550401,
            'other': 247020385730691073,
            'fluentenglish': 708704078540046346,
            'intermediateenglish': 708704480161431602,
            'beginnerenglish': 708704491180130326,
            'fluentspanish': 708704473358532698,
            'intermediatespanish': 708704486994215002,
            'beginnerspanish': 708704495302869003,
            'learningenglish': 247021017740869632,
            'learningspanish': 297415063302832128,
            'heritageenglish': 1001176425296052324,
            'heritagespanish': 1001176351874752512
        }

        roles = {name: guild.get_role(rid) for name, rid in role_ids.items()}

        language_roles = {roles['english'], roles['spanish'], roles['other']}
        level_roles = {roles['fluentenglish'], roles['intermediateenglish'], roles['beginnerenglish'],
                       roles['fluentspanish'], roles['intermediatespanish'], roles['beginnerspanish']}
        learning_roles = {roles['learningenglish'], roles['learningspanish']}
        heritage_roles = {roles['heritageenglish'], roles['heritagespanish']}
        all_roles = language_roles | level_roles | learning_roles | heritage_roles

        langs_dict = {'english': roles['english'], 'e': roles['english'], 'en': roles['english'],
                      'ne': roles['english'],
                      's': roles['spanish'], 'spanish': roles['spanish'], 'sn': roles['spanish'],
                      'ns': roles['spanish'],
                      'other': roles['other'], 'ol': roles['other'], 'on': roles['other'], 'o': roles['other'],
                      'ae': roles['fluentenglish'], 'fe': roles['fluentenglish'], 'ie': roles['intermediateenglish'],
                      'be': roles['beginnerenglish'],
                      'as': roles['fluentspanish'], 'fs': roles['fluentspanish'], 'is': roles['intermediatespanish'],
                      'bs': roles['beginnerspanish'],
                      'le': roles['learningenglish'], 'ls': roles['learningspanish'], 'he': roles['heritageenglish'],
                      'hs': roles['heritagespanish'],
                      'none': None, 'n': None}

        # langs_dict.update({role.id: role for role in all_roles})
        for role in all_roles:
            if role:
                langs_dict.update({role.id: role})

        user_roles = {langs_dict.get(role) for role in user_roles_in}

        remove_all = 'none' in langs or 'n' in langs
        langs -= {'none', 'n'}

        # main two sets for roles to add and remove
        to_add_lang_roles = set()
        to_remove = set()

        # in "specially_add" list are roles specified with "+" in front of them
        # adding a role in this way will not cause the removal of other roles in its category
        # for example, doing ;r ... ne  --> adds native english, removes other native roles
        # but        , doing ;r ... +ne --> adds native english, keeps other native roles
        specially_add = set()

        for lang in langs:
            lang_name = lang.lstrip('+-')
            role_obj = langs_dict.get(lang_name)

            if not role_obj:
                raise ValueError(
                    f"Role {lang_name} not found in guild {guild.id}")

            if lang.startswith('-'):
                to_remove.add(role_obj)
            elif lang.startswith('+'):
                specially_add.add(role_obj)
            else:
                to_add_lang_roles.add(role_obj)

        # possibilities at this point for duplicate roles to exist across the sets:
        # ;r ... ne +ne
        # ;r ... ne ne
        # ;r ... ne -ne
        # ;r ... -ne -ne
        # remove "ne" from all three sets in all of these cases
        duplicate_roles = (to_add_lang_roles & specially_add) | (
            to_add_lang_roles & to_remove) | (specially_add & to_remove)
        to_add_lang_roles -= duplicate_roles
        specially_add -= duplicate_roles
        to_remove -= duplicate_roles

        # if a role is being added, remove all other roles in the same category
        # create these sets using set logic
        if to_add_lang_roles & language_roles:
            to_remove.update(language_roles - to_add_lang_roles)
        if to_add_lang_roles & level_roles:
            to_remove.update(level_roles - to_add_lang_roles)
        if to_add_lang_roles & learning_roles:
            to_remove.update(learning_roles - to_add_lang_roles)
        if to_add_lang_roles & heritage_roles:
            to_remove.update(heritage_roles - to_add_lang_roles)

        # if you specify "none", then just add everything to remove
        if remove_all:
            to_remove = all_roles - to_add_lang_roles

        # remake to_add set to only include roles that aren't already in user roles
        to_add_lang_roles = {
            role for role in to_add_lang_roles if role not in user_roles}
        to_add_lang_roles |= specially_add

        # remake to_remove set to only include roles that are in user roles
        to_remove = {role for role in to_remove if role in user_roles}

        final_roles = set(user_roles) - to_remove | to_add_lang_roles
        final_language_roles = final_roles & all_roles

        return to_add_lang_roles, to_remove, final_language_roles

    async def test_role_command(self):
        guild = self.bot.get_guild(SP_SERV)
        if not guild:
            print("Skipping test_role_command: Spanish server not found")
            return
        roles = {243853718758359040: 'english',
                 243854128424550401: 'spanish',
                 247020385730691073: 'other',
                 708704078540046346: 'fluentenglish',
                 708704480161431602: 'intermediateenglish',
                 708704491180130326: 'beginnerenglish',
                 708704473358532698: 'fluentspanish',
                 708704486994215002: 'intermediatespanish',
                 708704495302869003: 'beginnerspanish',
                 247021017740869632: 'learningenglish',
                 297415063302832128: 'learningspanish',
                 1001176425296052324: 'heritageenglish',
                 1001176351874752512: 'heritagespanish'}
        test_cases = [
            ({'ne', 's'}, {'ol'}, {'other'}),
            ({'ne', 's', 'fs'}, {'ol'}, {'other', 'fluentspanish'}),
            ({'ne', 's', 'fs', 'ne'}, {'ol'}, {'other', 'fluentspanish'}),
            ({'ne', 's', 'fs'}, {'+ol'}, {'english',
             'spanish', 'other', 'fluentspanish'}),
            ({'ns', 'fs'}, {'-ol'}, {'spanish', 'fluentspanish'}),
            ({'e', 's', 'fs'}, {'e', '+fe'},
             {'english', 'fluentenglish', 'fluentspanish'}),
            ({'ne', 'ns', 'fs', 'le'}, {'none', 'o', 'le', 'ls'},
             {'other', 'learningenglish', 'learningspanish'}),
            ({'ne', 'ns', 'fs', 'le'}, {'+o', 'le', 'ls'}, {'other', 'english', 'spanish', 'fluentspanish',
                                                            'learningenglish', 'learningspanish'}),
            ({'on', 'le'}, {'sn', 'ls', 'le', '-en'},
             {'spanish', 'learningspanish', 'learningenglish'}),
            ({'on', 'le', 'en'}, {'sn', 'ls', 'le', '-en'},
             {'spanish', 'learningspanish', 'learningenglish'}),
        ]

        # chatgpt test cases
        test_cases += [
            # Initial roles, command input, expected final roles after processing
            ({'ne', 'fs'}, {'-ne', 'ns'}, {'spanish', 'fluentspanish'}),
            # Replace English with Spanish, keep fluentspanish
            # Upgrade intermediate to fluent, remove other
            ({'ol', 'ie'}, {'fe', '-ol'}, {'fluentenglish'}),
            ({'ol', 'ie', 'ls'}, {'none', '+he'}, {'heritageenglish'}),
            # Remove all except explicitly added heritageenglish
            # Explicitly keep other, remove learningspanish
            ({'ol', 'ls'}, {'+ol', '-ls'}, {'other'}),
            ({'ns', 'bs', 'le'}, {'+be', '-bs'},
             {'spanish', 'learningenglish', 'beginnerenglish'}),
            # Swap beginner Spanish to beginner English
            # Remove all roles explicitly
            ({'fs', 'ie'}, {'-fs', '-ie'}, set()),
            ({'he', 'ne'}, {'hs', '+he'},
             {'heritagespanish', 'heritageenglish', 'english'}),
            # Add heritagespanish, keep heritageenglish, maintain english
            # Change from fluentspanish and other to just English
            ({'ol', 'as'}, {'ne', '-as'}, {'english'}),
            ({'le', 'ol', 'be'}, {'-le', '+fe'},
             {'other', 'beginnerenglish', 'fluentenglish'}),
            # Upgrade beginner English to fluent, remove learning English
            ({'on'}, {'none', '+on', '+ls'}, {'other', 'learningspanish'}),
            # Clear all roles except explicitly kept other and add learningspanish
        ]

        for test_case in test_cases:
            to_add_lang_roles, to_remove, final_roles = await self.process_role_changes(guild, test_case[0], test_case[1])
            final_roles = {roles[role.id] for role in final_roles}

            assert final_roles == test_case[2], f"Failed test case: {test_case}, result: {final_roles}"

    @commands.group(aliases=['warnlog', 'ml', 'wl'], invoke_without_command=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @hf.basic_timer(0.5)
    async def modlog(self, ctx: commands.Context, id_in, delete_parameter: Optional[int] = None, post_embed=True):
        """View modlog of a user"""
        if str(ctx.guild.id) not in ctx.bot.db['modlog']:
            return
        config = ctx.bot.db['modlog'][str(ctx.guild.id)]
        member: discord.Member = await utils.member_converter(ctx, id_in)
        if member:
            user: Optional[Union[discord.User, discord.Member]] = member
            user_id = str(member.id)
        else:
            try:
                user = await self.bot.fetch_user(int(id_in))
                user_id = id_in
            except discord.NotFound:
                user = user_id = None
            except discord.HTTPException:
                await utils.safe_send(ctx, "Your ID was not properly formatted. Try again.")
                return
            except ValueError:
                await utils.safe_send(ctx, "I couldn't find the user you were looking for. If they left the server, "
                                           "use an ID")
                return

        #
        #
        # ######### Start building embed #########
        #
        #

        if not member and not user:  # Can't find user at all
            emb = utils.red_embed("")
            emb.set_author(name="COULD NOT FIND USER")

        else:

            #
            #
            # ######### Check whether the user is muted or banned #########
            #
            #

            # Check DB for mute entry
            muted = False
            unmute_date: Optional[datetime]
            unmute_date_str: str  # unmute_date_str looks like "2021/06/26 23:24 UTC"
            guild_id = str(ctx.guild.id)
            if unmute_date_str := self.bot.db['mutes'].get(guild_id, {}).get('timed_mutes', {}).get(user_id, ""):
                muted = True
                unmute_date = hf.convert_to_datetime(unmute_date_str)
            else:
                unmute_date = None

            # Check DB for voice mute entry
            voice_muted = False
            # unmute_date looks like "2021/06/26 23:24 UTC"
            voice_unmute_time_left_str: Optional[str]
            if voice_unmute_time_left_str := self.bot.db['voice_mutes'] \
                    .get(str(ctx.guild.id), {}) \
                    .get('timed_mutes', {}) \
                    .get(user_id, None):
                voice_muted = True
                voice_unmute_date = hf.convert_to_datetime(
                    voice_unmute_time_left_str)
            else:
                voice_unmute_date = None

            # Check for mute role in member roles
            if member:
                mute_role_id: str = self.bot.db['mutes'].get(
                    str(ctx.guild.id), {}).get('role', 0)
                mute_role: discord.Role = ctx.guild.get_role(int(mute_role_id))
                if mute_role in member.roles:
                    muted = True
                else:
                    muted = False  # even if the user is in the DB for a mute, if they don't the role they aren't muted

            # Check for timeout
            timeout: bool = False
            if member:
                if member.is_timed_out():
                    timeout = True

            # Check for voice mute role in member roles
            if member:
                mute_role_id: str = self.bot.db['voice_mutes'].get(
                    str(ctx.guild.id), {}).get('role', 0)
                mute_role: discord.Role = ctx.guild.get_role(int(mute_role_id))
                if mute_role in member.roles:
                    voice_muted = True
                else:
                    # even if the user is in the DB, if they don't the role they aren't muted
                    voice_muted = False

            banned = False  # unban_date looks like "2021/06/26 23:24 UTC"
            unban_date = None
            # Check guild ban logs for ban entry
            try:
                await ctx.guild.fetch_ban(user)
                banned = True

                # check if timed ban
                if unban_date_str := self.bot.db['bans'] \
                        .get(str(ctx.guild.id), {}) \
                        .get('timed_bans', {}) \
                        .get(user_id, None):
                    unban_date = hf.convert_to_datetime(unban_date_str)
                else:
                    unban_date = None  # indefinite ban
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                banned = False  # user is not banned

            #
            #
            # ############ Author / Title ############
            #
            #

            emb = utils.green_embed("")

            if getattr(user, "nick", None):
                name = f"{str(user)} ({user.nick})\n{user_id}"
            else:
                name = f"{str(user)}\n{user_id}"

            emb.set_author(name=name, icon_url=user.display_avatar.replace(
                static_format="png").url)

            if banned:
                emb.color = 0x141414  # very dark black, but not completely black
                if unban_date:
                    emb.description += (f"**`Current Status`** Temporarily Banned "
                                        f"(unban <t:{int(unban_date.timestamp())}:R>)")
                else:
                    emb.description += f"**`Current Status`** Indefinitely Banned"

            elif voice_muted:
                emb.color = utils.red_embed("").color
                if voice_unmute_date:
                    emb.description += (f"**`Current Status`** "
                                        f"Voice Muted (unmuted <t:{int(voice_unmute_date.timestamp())}:R>)")
                else:
                    emb.description += f"**`Current Status`** Indefinitely Voice Muted"

            elif muted:
                emb.color = utils.red_embed("").color
                if unmute_date:
                    emb.description += (f"**`Current Status`** "
                                        f"Muted (unmute <t:{int(unmute_date.timestamp())}:R>)")
                else:
                    emb.description += f"**`Current Status`** Indefinitely Muted"

            elif timeout:
                emb.color = utils.red_embed("").color
                if member.timed_out_until:
                    emb.description += (f"**`Current Status`** "
                                        f"Timed out (expires <t:{int(member.timed_out_until.timestamp())}:R>)")
                else:
                    pass

            elif not member:
                emb.color = utils.grey_embed("").color
                if muted and not banned:
                    emb.description += " (user has left the server)"
                elif not muted and not banned:
                    emb.description += f"**`Current Status`** : User is not in server"
            else:
                emb.description += f"**`Current Status`** : No active incidents"

        #
        #
        # ############ Number of messages / voice hours ############
        #
        #

        if member:
            total_msgs_month = 0
            total_msgs_week = 0
            # ### Calculate number of messages ###
            message_count = {}
            if str(ctx.guild.id) in self.bot.stats:
                stats_config = self.bot.stats[str(ctx.guild.id)]['messages']
                for day in stats_config:
                    if str(member.id) in stats_config[day]:
                        user_stats = stats_config[day][str(member.id)]
                        if 'channels' not in user_stats:
                            continue
                        for channel in user_stats['channels']:
                            message_count[channel] = message_count.get(
                                channel, 0) + user_stats['channels'][channel]
                            days_ago = (discord.utils.utcnow() - datetime.strptime(day, "%Y%m%d")
                                        .replace(tzinfo=timezone.utc)).days
                            if days_ago <= 7:
                                total_msgs_week += user_stats['channels'][channel]
                            total_msgs_month += user_stats['channels'][channel]

            # ### Calculate voice time ###
            voice_time_str = "0h"
            if 'voice' in self.bot.stats.get(str(ctx.guild.id), {}):
                voice_config = self.bot.stats[str(
                    ctx.guild.id)]['voice']['total_time']
                voice_time = 0
                for day in voice_config:
                    if str(member.id) in voice_config[day]:
                        time = voice_config[day][str(member.id)]
                        voice_time += time
                voice_time_str = format_interval(voice_time * 60)

            emb.description += f"\n**`Number of messages M | W`** : {total_msgs_month} | {total_msgs_week}"
            emb.description += f"\n**`Time in voice`** : {voice_time_str}"

            # ### Add sentiment information ###
            if str(ctx.guild.id) in self.bot.db.get('sentiments', []):
                user_sentiment = self.bot.db['sentiments'][str(
                    ctx.guild.id)].get(str(member.id), [])
                num_sentiment_msg = len(user_sentiment)
                if user_sentiment:
                    if num_sentiment_msg == 1000:
                        user_sentiment_total = round(sum(user_sentiment), 2)
                        emb.description += f"\n**`Recent sentiment ({num_sentiment_msg} msgs)`** : " \
                            f"{user_sentiment_total}"
                    else:
                        user_sentiment_total = round(
                            sum(user_sentiment) * 1000 / num_sentiment_msg, 2)
                        emb.description += f"\n**`Recent sentiment (scale {num_sentiment_msg}→1000 msgs)`** : " \
                            f"{user_sentiment_total}"

        join_history = self.bot.db['joins'].get(str(ctx.guild.id), {}).get(
            'join_history', {}).get(user_id, None)

        # most invites recorded between june 26, 2021 and july 23, 2022 had a bug that caused them to default to
        # the same invite. For those invites, I jump to the jump_url in the join_history object and check in that embed
        # what the correct invite was
        if member:
            if datetime(2021, 6, 25, tzinfo=timezone.utc) <= member.joined_at <= datetime(2022, 7, 24,
                                                                                          tzinfo=timezone.utc):
                join_history = await fix_join_history_invite(ctx, user_id, join_history)
        else:
            join_history = await fix_join_history_invite(ctx, user_id, join_history)

        if join_history:
            invite: Optional[str]
            invite_creator_id: Optional[int]
            if invite := join_history.get('invite'):
                if invite not in ['Through server discovery', ctx.guild.vanity_url_code]:
                    # all old join entries don't have this field
                    invite_creator_id = join_history.get('invite_creator')
                    if not invite_creator_id:
                        invite_obj: Optional[discord.Invite] = discord.utils.find(lambda i: i.code == invite,
                                                                                  await ctx.guild.invites())
                        if not invite_obj:
                            if invite == ctx.guild.vanity_url_code:
                                invite_obj = await ctx.guild.vanity_invite()

                        invite_creator_id = getattr(
                            getattr(invite_obj, "inviter", None), "id", None)

                    invite_creator_user = None
                    if invite_creator_id:
                        try:
                            invite_creator_user = await ctx.bot.fetch_user(invite_creator_id)
                        except (discord.NotFound, discord.HTTPException):
                            pass

                    if invite_creator_user:
                        invite_author_str = \
                            f"by {str(invite_creator_user)} " \
                            f"([ID](https://rai/inviter-id-is-I{invite_creator_id}))"
                    else:
                        invite_author_str = "by unknown user"
                else:
                    invite_author_str = ""

                emb.description += f"\n[**`Used Invite`**]({join_history['jump_url']}) : " \
                    f"{invite} {invite_author_str}"

        #
        #
        # ############ Current Language Roles ############
        #
        #
        if member:
            # go down user roles starting from top and get highest language role
            eng_role_id = 243853718758359040
            sp_role_id = 243854128424550401
            ol_role_id = 247020385730691073
            roles = [eng_role_id, sp_role_id, ol_role_id]
            found_roles = []
            for role in member.roles:
                if role.id in roles:
                    found_roles.append(role)
            if found_roles:
                emb.description += "\n**`Current Language Roles`** : " + \
                    ", ".join([r.mention for r in found_roles])

        if member:
            emb.description += f"\n{member.mention}\n"

            #
            #
            # ############ Check for excessive DMs / suspected spam activity user flags ############
            #
            #
            excessive_dms_flag = await hf.excessive_dm_activity(ctx.guild.id, user_id)
            suspected_spam_flag = await hf.suspected_spam_activity_flag(ctx.guild.id, user_id)
            if excessive_dms_flag or suspected_spam_flag:
                emb.description += "\n⚠️ **__User Flags__** ⚠️\n"
            if excessive_dms_flag:
                emb.description += "**`Excessive DMs`** : User has been flagged for excessive DMs\n"
            if suspected_spam_flag:
                emb.description += "**`Suspected Spam`** : User has been flagged for suspected spam activity\n"

        #
        #
        # ############ Footer / Timestamp ############
        #
        #

        if member:
            emb.set_footer(text="Join Date")
            emb.timestamp = member.joined_at
        else:
            emb.set_footer(text="User not in server")

        #
        #
        # ############ Modlog entries into fields ############
        #
        #

        if member or user:
            if user_id in config:  # Modlog entries
                config = config[user_id]
            else:  # No entries
                config = []
            if len(config) == 0:
                emb.color = utils.grey_embed("").color
                emb.description += "\n***>> NO MODLOG ENTRIES << ***"
        else:  # Non-existent user
            config = []

        # only to be used if the first embed goes over 6000 characters
        first_embed: Optional[discord.Embed] = None
        valid_logs = []
        for entry in config:
            if entry['silent']:
                if entry['type'] == "AutoMod":
                    continue
            valid_logs.append(entry)

        for entry in valid_logs[-25:]:
            name = f"{config.index(entry) + 1}) "
            if entry['silent']:
                if entry['type'] == "Warning":
                    name += f"Silent Log"
                else:
                    name += f"{entry['type']} (silent)"
            else:
                name += entry['type']

            incident_time = hf.convert_to_datetime(entry['date'])
            value = f"<t:{int(incident_time.timestamp())}:f>\n"
            if entry['length']:
                value += f"*For {entry['length']}*\n"
            if entry['reason']:
                value += f"__Reason__: {entry['reason']}\n"
            if entry['jump_url']:
                value += f"[Jump URL]({entry['jump_url']})\n"

            # if a modlog entry content has an attachment, try to regenerate the URL so it doesn't expire
            if re_result := re.findall(r"https://cdn\.discordapp\.com/attachments/(\d+)/(\d+)/[\w.&=?]*", value):
                # capture group 1 is the channel ID, group 2 is the *attachment ID*, not the message ID
                # the attachment ID will be registered slightly before the message ID it gets put onto, so
                # search for the message in the channel *after* the attachment ID snowflake
                # re_result looks like [('channel_id', 'attachment_id'), ('channel_id', 'attachment_id')]
                for attachment in re_result:
                    channel_id = int(attachment[0])
                    channel = ctx.guild.get_channel(channel_id)
                    if not channel:
                        # try searching for a thread (including archived threads)
                        try:
                            channel = await ctx.guild.fetch_channel(channel_id)
                        except discord.Forbidden:
                            continue
                        if not channel:
                            continue
                    attachment_id = (int(attachment[1]))

                    async def find_attachment(message_id):
                        async for m in channel.history(limit=5, around=discord.Object(id=message_id)):
                            for new_attachment in m.attachments:
                                if new_attachment.id == attachment_id:
                                    return new_attachment.url

                    try:
                        new_url = await find_attachment(attachment_id)
                        if new_url:
                            value = re.sub(
                                rf"https://cdn\.discordapp\.com/attachments/\d+/{attachment_id}/[\w.&=?]*",
                                new_url, value)
                    except (discord.Forbidden, discord.HTTPException, IndexError) as e:
                        continue

            if (len(emb) + len(name) + len(value[:1024])) > 6000:
                first_embed = deepcopy(emb)
                emb.clear_fields()

            if len(value) <= 1024:
                emb.add_field(name=name, value=value[:1024], inline=False)
            else:
                emb.add_field(
                    name=name, value=value[:1021] + "...", inline=False)
                to_add_value = value[1021:]
                if len(to_add_value) > 1021:
                    over_amount = len(to_add_value) - 1014
                    to_add_value = to_add_value[:500] + \
                        " [...] " + to_add_value[500 + over_amount:]
                emb.add_field(name=name + "(cont.)",
                              value="..." + to_add_value, inline=False)

            # if there are more than 25 fields (the max), remove extra
            extra_fields = len(emb.fields) - 25
            if extra_fields > 0:
                for i in range(extra_fields):
                    emb.remove_field(i)

        #
        #
        # ############ !! SEND !! ############
        #
        #

        if post_embed:
            if first_embed:  # will only be True if there are two embeds to send
                try:
                    await utils.safe_send(ctx, user_id, embed=first_embed, delete_after=delete_parameter)
                except discord.Forbidden:
                    await utils.safe_send(ctx.author, "I lack some permission to send the result of this command")
                    return

            try:
                # if there's a first embed, this will be the second embed
                await utils.safe_send(ctx, user_id, embed=emb, delete_after=delete_parameter)
            except discord.Forbidden:
                if not ctx.author.bot:
                    await utils.safe_send(ctx.author, "I lack some permission to send the result of this command")
                    return

        if first_embed:
            return first_embed
        else:
            return emb

    @modlog.command(name='delete', aliases=['del'])
    @hf.is_admin()
    async def modlog_delete(self, ctx, user, *, indices=""):
        """Delete modlog entries.  Do `;modlog delete user -all` to clear all warnings from a user.
        Alias: `;ml del`"""
        if not indices:  # If no index is given:
            await utils.safe_send(ctx, "Please write numeric indices equal to or greater than 1 or "
                                       "`-all` to clear the user's modlog.")
            return

        # Creates a list from the prompted argument of the command.
        indices = indices.split()
        indices = list(set(indices))  # Removing duplicates from the list.

        if str(ctx.guild.id) not in ctx.bot.db['modlog']:
            return
        config = ctx.bot.db['modlog'][str(ctx.guild.id)]
        member = await utils.member_converter(ctx, user)
        if member:
            user_id = str(member.id)
        else:
            user_id = user
        if user_id not in config:
            await utils.safe_send(ctx, "That user was not found in the modlog")
            return

        config: dict = config[user_id]

        # Performs the deletions:
        # If any of these flags is found in the list:
        if '-a' in indices or '-all' in indices:
            # clear the modlog...
            del ctx.bot.db['modlog'][str(ctx.guild.id)][user_id]
            await utils.safe_send(ctx,
                                  # send emb.
                                  embed=utils.red_embed(f"Deleted all modlog entries for <@{user_id}>."))

        elif len(indices) == 1:  # If there is a single argument given, then:
            try:
                del config[int(indices[0]) - 1]  # delete it from modlog...
            except IndexError:  # except if the index given is not found in config...
                await utils.safe_send(ctx,
                                      f"I couldn't find the log #**{indices[0]}**, try doing `;modlog` on the user.")
                return
            except ValueError:  # or if the index given is not an integer...
                await utils.safe_send(ctx, "The given index is invalid.\n"
                                           "Please write numeric indices equal to or greater than 1 or "
                                           "`-all` to clear the user's modlog.")
                return
            await ctx.message.add_reaction('✅')

        else:  # -all was not called, and so there are specific indices to delete:
            def invalid_indices_check(check_index: str):
                """For indices that are strings or not greater than 0"""
                if not check_index.isdigit():  # is not a digit
                    return True
                else:  # now is a digit
                    if int(check_index) < 1:  # if index is 0 or negative
                        return True

            def not_found_check(check_index: str, _config: dict):
                """For indices not in config"""
                if check_index.isdigit():
                    if int(check_index) > len(_config):
                        return True  # called index is out of range of list

            def indices_check(check_index, not_found):
                if check_index.isdigit() and check_index not in not_found:
                    if int(check_index) >= 1:
                        return True

            invalid_indices: list = [i for i in indices
                                     # list of non-digit arguments
                                     if invalid_indices_check(i)]
            not_found_indices: list = [i for i in indices
                                       # list of indices not found in modlog
                                       if not_found_check(i, config)]
            valid_indices: list = [i for i in indices
                                   # list of valid arguments
                                   if indices_check(i, not_found_indices)]
            removed_indices: list = []  # eventual list of modlog entries successfully removed
            valid_indices.sort(key=int)  # Sort it numerically
            assert len(valid_indices) + len(invalid_indices) + len(not_found_indices) == len(indices), \
                (f"Indices don't add up: {len(valid_indices)=} + {len(invalid_indices)=} + {len(not_found_indices)=} "
                 f"!= {len(indices)=}")

            n = 1
            for index in valid_indices:  # For every index in the list...
                # delete them from the user's modlog.
                del config[int(index) - n]
                n += 1  # For every deleted log, the next ones will be shifted by -1. Therefore,
                # add 1 every time a log gets deleted to counter that.
                # for every successfully deleted log, append
                removed_indices.append(index)
                # the index to the corresponding 'removed_indexes' list.
            await ctx.message.add_reaction('✅')

            # Prepare emb to send:
            summary_text = "Task completed."

            if removed_indices:  # If it removed logs in config:
                # format it...
                removed_indices = ["#**" + i + "**" for i in removed_indices]
                # change it to string...
                rmv_indx_str = f"\n**-** Removed entries: {', '.join(removed_indices)}."
                # add it to the text.
                summary_text = summary_text + rmv_indx_str

            if not_found_indices:  # If there were indices with no match in the config modlog:
                # format for first ten indices
                not_found_indices = ["#**" + i +
                                     "**" for i in not_found_indices[:10]]
                # change it to string...
                n_fnd_indx_str = ', '.join(not_found_indices)
                # add it to the text.
                summary_text = summary_text + \
                    f"\n**-** Not found entries: {n_fnd_indx_str}."
                # If there are more than ten...
                if len(not_found_indices) > 10:
                    # add to the text.
                    summary_text = summary_text[:-1] + \
                        f"and {len(not_found_indices) - 10} more..."

            # If invalid indices were found (TypeError or <= 0):
            if invalid_indices:
                # first 10 indices only
                invalid_indices = [str(i)[0].lower()
                                   for i in invalid_indices[:10]]
                invalid_indices = ["**" + i + "**" for i in invalid_indices]
                # remove duplicates...
                invalid_indices = list(set(invalid_indices))
                # sort them numerically (aesthetics)...
                invalid_indices = sorted(invalid_indices, key=str)
                inv_indx_str = f"\n**-** Invalid indices: {', '.join(invalid_indices)}."
                summary_text = summary_text + inv_indx_str
                if len(invalid_indices) > 10:
                    summary_text = summary_text[:-1] + \
                        f" and {len(invalid_indices) - 10} more..."

            # Make the embed with the summary text previously built.
            emb = utils.green_embed(summary_text)
            await utils.safe_send(ctx, embed=emb)  # Send the embed.

    @modlog.command(name="edit", aliases=['reason'])
    async def modlog_edit(self, ctx, user, index: int, *, reason):
        """Edit the reason for a selected modlog.  Example: `;ml edit ryry 2 trolling in voice channels`."""
        if str(ctx.guild.id) not in ctx.bot.db['modlog']:
            return
        if re.search(r"\d{1,3}", user):
            if re.search(r"\d{17,22}", str(index)):
                user, index = str(index), int(user)  # swap the variables
        config = ctx.bot.db['modlog'][str(ctx.guild.id)]
        member = await utils.member_converter(ctx, user)
        if member:
            user_id = str(member.id)
        else:
            user_id = user
        if user_id not in config:
            await utils.safe_send(ctx, "That user was not found in the modlog")
            return
        config = config[user_id]
        log = config[index - 1]
        jump_url = log.get('jump_url', None)

        if not hf.admin_check(ctx):
            if jump_url:
                channel_id = int(jump_url.split('/')[-2])
                message_id = int(jump_url.split('/')[-1])
                try:
                    message = await ctx.bot.get_channel(channel_id).fetch_message(message_id)
                except discord.NotFound:
                    await utils.safe_send(ctx, f"Only admins can edit the reason for this entry.")
                    return
                else:
                    if message.author != ctx.author:
                        await utils.safe_send(ctx, f"Only admins (or the creator of the log) can edit the "
                                              f"reason for this entry.")
                        return
            else:
                await utils.safe_send(ctx, f"Only admins can edit the reason for this entry.")
                return

        try:
            old_reason = log['reason']
        except IndexError:
            await utils.safe_send(ctx, f"I couldn't find the mod log with the index {index - 1}. Please check it "
                                  f"and try again.")
            return

        config[index - 1]['reason'] = reason
        await utils.safe_send(ctx, embed=utils.green_embed(f"Changed the reason for entry #{index} from "
                                                           f"```{old_reason}```to```{reason}```"))

    @commands.command()
    @hf.is_admin()
    async def reason(self, ctx: commands.Context,
                     user, index: int, *, reason):
        """Shortcut for `;modlog reason`"""
        await ctx.invoke(self.modlog_edit.invoke, user, index, reason=reason)

    @commands.command()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    @commands.max_concurrency(1, commands.BucketType.member)
    async def mute(self, ctx: commands.Context, *, args):
        """Mutes a user.  Syntax: `;mute <time> <member> [reason]`.  Example: `;mute 1d2h Abelian`."""
        # Pull all args out of args variable using hf function
        args = hf.args_discriminator(args=args)
        time_string = args.time_string
        time_obj = args.time_obj
        timedelta_obj = args.timedelta_obj
        time_arg = args.time_arg
        length = args.length
        reason = args.reason
        target_ids = args.user_ids

        if timedelta_obj.days > 28:
            await utils.safe_reply(ctx, "You can not mute for longer than 28 days. "
                                        "Please consider a temporary ban.")
            return

        if not target_ids:
            await utils.safe_send(ctx, "I couldn't understand your command properly. Please mention a user to mute, "
                                       "and if you write a time, format it like `2d`, `3h`, `5d6h`, etc.")
            return

        def change_mute_duration(days: int):
            _time_arg = f"{days}d"
            _time_string, _length = hf.parse_time(_time_arg)
            _time_obj = datetime.strptime(
                _time_string, "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
            _timedelta_obj = _time_obj - discord.utils.utcnow()
            return _time_arg, _time_string, _length, _time_obj, _timedelta_obj

        if not length:
            time_arg, time_string, length, time_obj, timedelta_obj = change_mute_duration(
                1)
            await utils.safe_reply(ctx, "Indefinitite mutes are not possilbe; changing duration to 1d.")

        # time_string should always be *something* now
        assert bool(time_string)

        # for channel helpers, limit mute time to three hours
        if not hf.submod_check(ctx):
            if time_string:  # if the channel helper specified a time for the mute
                total_hours = timedelta_obj.total_seconds() * 60 * 60
                if total_hours > 24:
                    time_arg, time_string, length, time_obj, timedelta_obj = change_mute_duration(
                        1)
                    await utils.safe_send(ctx.author, "Channel helpers can only mute for a maximum of 24 "
                                                      "hours, so I set the duration of the mute to 24h.")

        silent = False
        if reason:
            if '-s' in reason or '-n' in reason:
                if ctx.guild.id == JP_SERV:
                    await utils.safe_send(ctx, "Maybe you meant to use Ciri?")
                reason = reason.replace(
                    ' -s', '').replace('-s ', '').replace('-s', '')
                silent = True

        for target_id in target_ids:
            target = ctx.guild.get_member(target_id)

            # Stop function if user not found
            if not target:
                try:
                    await utils.safe_send(ctx,
                                          "I could not find the user.  For warns and mutes, please use either an ID "
                                          "or a mention to the user (this is to prevent mistaking people).")
                except discord.HTTPException:  # Possible if Rai is sending a message to itself for automatic mutes
                    pass
                continue

            try:
                await target.timeout(time_obj, reason=reason)
            except discord.Forbidden:
                await utils.safe_send(ctx, f"I failed to timeout {str(target)} ({target.id}). "
                                      f"Please check my permissions "
                                      f"(I can't timeout people higher than me on the rolelist)")
                return
            except discord.HTTPException:
                await utils.safe_send(ctx,
                                      f"There was some kind of HTTP error that prevented me from timing out {target.id}"
                                      " user. Please try again.")
                return

            description = f"You have been muted on {ctx.guild.name}"
            emb = utils.red_embed("")
            emb.title = description
            emb.color = discord.Color(int('ff8800', 16))  # embed
            if time_arg:
                timestamp = int(time_obj.timestamp())
                emb.add_field(name="Length",
                              value=f"{time_arg} (will be unmuted on <t:{timestamp}> - <t:{timestamp}:R> )",
                              inline=False)
            else:
                timestamp = 0
                emb.add_field(name="Length", value="Indefinite", inline=False)
            if reason:
                if len(reason) <= 1024:
                    emb.add_field(name="Reason", value=reason)
                elif 1024 < len(reason) <= 2048:
                    emb.add_field(name="Reason", value=reason[:1024])
                    emb.add_field(name="Reason (cont.)", value=reason[1024:])
                else:
                    await utils.safe_send(ctx, "Your reason for the mute was too long. Please use less than 2048 "
                                               "characters.")
                    return

            # Add default prompt to go to modbot for questions about the warning
            modbot = ctx.guild.get_member(713245294657273856)
            if modbot:
                emb.add_field(name="Questions about this mute?",
                              value=f"Please send a message to {modbot.mention}.",
                              inline=False)
                content = f"Questions → {modbot.mention}"
            else:
                content = ""

            if not silent:
                try:
                    await utils.safe_send(target, content, embed=emb)
                except discord.Forbidden:
                    await utils.safe_send(ctx, "This user has DMs disabled so I couldn't send the notification. I'll "
                                               "keep them muted but they won't receive the notification for it.")
                    pass

            # Prepare confirmation message to be sent to ctx channel of mute command
            notif_text = f"**{str(target)}** ({target.id}) has been **muted** from text and voice chats."
            if time_string:
                interval_str = format_interval(
                    timedelta(days=length[0], hours=length[1], minutes=length[2]))
                notif_text = f"{notif_text[:-1]} for {interval_str} (until <t:{int(time_obj.timestamp())}:f>)."
            if reason:
                notif_text += f"\nReason: {reason}"

            # Make embed
            emb = utils.red_embed('')
            emb.title = "Mute"

            emb.add_field(name="User", value=f"{str(target)} ({target.id})",
                          inline=False)

            if time_string:
                emb.title = "Temporary " + emb.title
                if length[2]:
                    dhm_str = f"{length[0]}d{length[1]}h{length[2]}m"
                else:
                    dhm_str = f"{length[0]}d{length[1]}h"
                emb.add_field(name="Mute duration",
                              value=f"For {dhm_str} (unmute on <t:{int(timestamp)}:f> - <t:{int(timestamp)}:R>)",
                              inline=False)
            else:
                emb.title = "Permanent " + emb.title

            if reason:
                reason_field = reason
            else:
                reason_field = "(No given reason)"
            if len(reason_field) <= 1024:
                emb.add_field(name="Reason", value=reason_field,
                              inline=False)
            else:
                emb.add_field(name="Reason", value=reason_field[:1021] + "...",
                              inline=False)
                emb.add_field(name="Reason (cont.)", value="..." + reason_field[1021:],
                              inline=False)

            if ctx.message:
                emb.add_field(name="Jump URL", value=ctx.message.jump_url,
                              inline=False)

            emb.set_footer(
                text=f"Muted by {ctx.author.name} ({ctx.author.id})")

            if silent:
                emb.title += " (The user was not notified of this)"
            if ctx.author == ctx.guild.me:
                additonal_text = str(target.id)
            else:
                additonal_text = ""
            if ctx.author != self.bot.user and "Nitro" not in reason:
                await utils.safe_send(ctx, additonal_text, embed=emb)

            # Add mute info to modlog
            modlog_config = hf.add_to_modlog(
                ctx, target, 'Mute', reason, silent, time_arg)

            # Add info about mute to modlog channel
            modlog_channel = self.bot.get_channel(modlog_config['channel'])

            try:
                if modlog_channel:
                    if modlog_channel != ctx.channel:
                        await utils.safe_send(modlog_channel, target.id, embed=emb)
            except AttributeError:
                await utils.safe_send(ctx, embed=emb)

    @commands.command()
    @hf.is_admin()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    async def unmute(self, ctx, target_in, guild=None):
        """Unmutes a user

        Usage: `;unmute <user>`"""
        if isinstance(guild, str):
            guild = None
        if not guild:
            guild = ctx.guild
            target: discord.Member = await utils.member_converter(ctx, target_in)
        else:
            guild = self.bot.get_guild(int(guild))
            target: discord.Member = guild.get_member(int(target_in))
        config = self.bot.db['mutes'].get(str(guild.id))
        if not config:
            await utils.safe_send(ctx, "I could not find any information about mutes in your guild.")
            return
        role = guild.get_role(config['role'])
        if not role:
            await utils.safe_send(ctx, f"I could not find the mute role "
                                  f"(guild_id: {guild.id}, role_id: {config['role']}). "
                                  f"Maybe it has been deleted?")
            # delete the role from the database
            del self.bot.db['mutes'][str(guild.id)]
            return

        voice_role = None
        if str(ctx.guild.id) in self.bot.db['voice_mutes']:
            voice_role = guild.get_role(
                self.bot.db['voice_mutes'][str(ctx.guild.id)]['role'])

        failed = False
        if target:
            target_id = target.id
            try:
                await target.remove_roles(role)
                failed = False
            except discord.HTTPException:
                pass

            if voice_role:
                try:
                    await target.remove_roles(voice_role)
                except discord.HTTPException:
                    pass

        else:
            if ctx.author == ctx.bot.user:
                target_id = target_in
            else:
                return

        if str(target_id) in config['timed_mutes']:
            del config['timed_mutes'][str(target_id)]

        if target:
            if target.is_timed_out():
                try:
                    await target.edit(timed_out_until=None)
                except (discord.Forbidden, discord.HTTPException):
                    await utils.safe_send(ctx, "I failed to remove the timeout from the user.")

        if ctx.author != ctx.bot.user:
            emb = discord.Embed(description=f"**{str(target)}** has been unmuted.",
                                color=discord.Color(int('00ffaa', 16)))
            await utils.safe_send(ctx, embed=emb)

        if not failed:
            return True

    compare = app_commands.Group(
        name="compare", description="Compare two things", guild_ids=[SP_SERV])

    @compare.command()
    @app_commands.default_permissions()
    async def users(self, interaction: discord.Interaction,
                    user_id_1: str,
                    user_id_2: str = None,
                    user_id_3: str = None):
        """Compares the join/leave dates, creation dates, and used invite of two users"""
        guild = interaction.guild
        join_history = self.bot.db['joins'].get(
            str(guild.id), {}).get('join_history', {})
        if not join_history:
            await interaction.response.send_message("This guild is not set up properly to use this command",
                                                    ephemeral=True)
            return

        users = []
        joins = []
        modlogs = []
        creates = []
        invites = []

        try:
            user_ids = list(
                map(int, [user_id_1, user_id_2 or 0, user_id_3 or 0]))
        except (ValueError, TypeError):
            await interaction.response.send_message("Please only input IDs as arguments.", ephemeral=True)
            return

        for user_id in user_ids:
            if not user_id:
                continue
            user = guild.get_member(user_id)
            if user:
                joins.append(user.joined_at)
            else:
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.NotFound:
                    await interaction.response.send_message(f"Could not find user {user_id}.", ephemeral=True)
                    return
                else:
                    joins.append(None)
            users.append(user)
            modlogs.append(self.bot.db['modlog'].get(
                str(guild.id), {}).get(str(user_id), []))
            creates.append(user.created_at)
            invites.append(join_history.get(
                (str(user.id)), {}).get("invite", None))

        emb = discord.Embed()
        for num, user in enumerate(users):
            emb_name = f"{str(user)} ({user.id})"
            emb_value = ""
            if create := creates[num]:
                emb_value += f"Creation date: <t:{int(create.timestamp())}>\n"

            if join := joins[num]:
                emb_value += f"Join date: <t:{int(join.timestamp())}>\n"

            if modlog := modlogs[num]:
                for modlog_entry in modlog[::-1]:
                    if modlog_entry['type'] == "Warning" and modlog_entry.get("silent", False):
                        continue
                    last_modlog_date = hf.convert_to_datetime(
                        modlog_entry['date'])
                    emb_value += f"Last modlog date ({modlog_entry['type']}): <t:{int(last_modlog_date.timestamp())}>\n"
                    break

            if invite := invites[num]:
                emb_value += f"Invite used: {invite}\n"

            emb.add_field(name=emb_name, value=emb_value, inline=False)

        await interaction.response.send_message(embed=emb)


async def setup(bot):
    await bot.add_cog(ChannelMods(bot))
