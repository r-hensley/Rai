from typing import Optional, Union, List
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from .utils import helper_functions as hf
from .utils.timeutil import format_interval
import re

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SP_SERV = 243838819743432704
JP_SERV = 189571157446492161


def any_channel_mod_check(ctx):
    if ctx.command.name == 'staffping':
        if ctx.guild.id == JP_SERV:
            return hf.submod_check(ctx)
    if ctx.guild.id != SP_SERV:
        return
    if hf.submod_check(ctx):
        return True
    chmd_config = ctx.bot.db['channel_mods'][str(SP_SERV)]
    helper_role = ctx.guild.get_role(591745589054668817)
    for ch_id in chmd_config:
        if ctx.author.id in chmd_config[ch_id]:
            if helper_role:
                if helper_role in ctx.author.roles:
                    return True
            else:
                return True


async def fix_join_history_invite(ctx: commands.Context, user_id: int, join_history: dict) -> dict:
    """Fix the invite used in join_history database for the year period of bugged logging"""
    if not join_history:
        return join_history
    notification_message_url = join_history['jump_url']
    # example: https://discord.com/channels/266695661670367232/321837027295363073/858265556297187328
    guild_id, channel_id, message_id = map(int, notification_message_url.split('/')[-3:])
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


async def make_mute_role(ctx, dest, voice_mute):
    """For use in mute command"""
    if voice_mute:
        name = 'rai-voice-mute'
    else:
        name = 'rai-mute'
    _role = discord.utils.find(lambda r: r.name.casefold() == name, ctx.guild.roles)
    if _role:
        first = False
        await hf.safe_send(dest, "Reusing previously existing Rai mute role")
    else:
        first = True
        _role = await ctx.guild.create_role(name=name, reason="For use with bot mute command")
    return _role, first


class ChannelMods(commands.Cog):
    """Commands that channel mods can use in their specific channels only. For adding channel \
    mods, see `;help channel_mod`. Submods and admins can also use these commands."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel':
            if not ctx.message.content.endswith("help"):  # ignore if it's the help command
                await hf.safe_send(ctx, "Please set a mod channel using `;set_mod_channel`.")
            return
        if not hf.submod_check(ctx):
            if isinstance(ctx.channel, discord.TextChannel):
                channel_id = ctx.channel.id
            elif isinstance(ctx.channel, discord.Thread):
                channel_id = ctx.channel.parent.id
            else:
                return
            if ctx.author.id in self.bot.db['channel_mods'].get(str(ctx.guild.id), {}).get(str(channel_id), {}):
                return True
            if ctx.channel.id == self.bot.db['submod_channel'].get(str(ctx.guild.id), None):
                return True
            if ctx.command.name == "staffping" and ctx.author.id in self.bot.db['voicemod'].get(ctx.guild.id, []):
                return True
        else:
            return True
        if ctx.command.name == 'role':
            return True

    @commands.command(name="delete", aliases=['del'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_messages=True)
    async def msg_delete(self, ctx, *ids):
        """A command to delete messages for submods.  Usage: `;del <list of IDs>`\n\n
        Example: `;del 589654995956269086 589654963337166886 589654194189893642`"""
        try:
            await ctx.message.delete()
            await hf.safe_send(ctx.author,
                               f"I'm gonna delete your message to potentially keep your privacy, but in case "
                               f"something goes wrong, here was what you sent: \n{ctx.message.content}")
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
                    await hf.safe_send(ctx, "This is a command to delete a certain message by specifying its "
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
            await hf.safe_send(ctx, f"The following IDs were not properly formatted: "
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
            await hf.safe_send(ctx, f"Unable to find ID(s) `{'`, `'.join([str(i) for i in failed_ids])}`.")

        if not msgs:
            return  # no messages found

        emb = discord.Embed(title=f"Deleted messages in #{msg.channel.name}", color=discord.Color(int('ff0000', 16)),
                            description=f"")
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
                    embeds.append(embed)
                    emb.add_field(name=f"Embed deleted", value=f"Content shown below ([Jump URL]({jump_url}))")
            if msg.content:
                emb.add_field(name=f"Message {msg_index} by {str(msg.author)} ({msg.author.id})",
                              value=f"{msg.content}"[:1008 - len(jump_url)] + f" ([Jump URL]({jump_url}))")
            if msg.content[1009:]:
                emb.add_field(name=f"continued", value=f"...{msg.content[1009 - len(jump_url):len(jump_url) + 1024]}")
            if msg.attachments:
                x = [f"{att.filename}: {att.proxy_url}" for att in msg.attachments]
                if not msg.content:
                    name = f"Message attachments by {str(msg.author)} (might expire soon):"
                else:
                    name = "Attachments (might expire soon):"
                emb.add_field(name=name, value='\n'.join(x))
            emb.timestamp = msg.created_at
        emb.set_footer(text=f"Deleted by {str(ctx.author)} - Message sent at:")
        if str(ctx.guild.id) in self.bot.db['submod_channel']:
            channel = self.bot.get_channel(self.bot.db['submod_channel'][str(ctx.guild.id)])
            if not channel:
                await hf.safe_send(ctx, "I couldn't find the channel you had set as your submod channel. Please "
                                        "set it again.")
                del (self.bot.db['submod_channel'][str(ctx.guild.id)])
                return
        elif str(ctx.guild.id) in self.bot.db['mod_channel']:
            channel = self.bot.get_channel(self.bot.db['mod_channel'][str(ctx.guild.id)])
            if not channel:
                await hf.safe_send(ctx, "I couldn't find the channel you had set as your submod channel. Please "
                                        "set it again.")
                del (self.bot.db['submod_channel'][str(ctx.guild.id)])
                return
        else:
            await hf.safe_send(ctx, "Please set either a mod channel or a submod channel with "
                                    "`;set_mod_channel` or `;set_submod_channel`")
            return

        await hf.safe_send(channel, embed=emb)
        if embeds:
            for embed in embeds:
                if not embed:
                    continue
                await hf.safe_send(channel, embed=embed)

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
                    await hf.safe_send(ctx, "I couldn't find the message you were looking for.")
                    return
            elif re.search(r'^\d{17,22}-\d{17,22}$', args[0]):
                channel_id = int(args[0].split('-')[0])
                channel = ctx.guild.get_channel_or_thread(channel_id)
                if not channel:
                    await hf.safe_send(ctx, "I couldn't find the channel you specified!")
                    return
                message_id = int(args[0].split('-')[1])
                to_be_pinned_msg = await channel.fetch_message(message_id)
            else:
                await hf.safe_send(ctx, "Please input a valid ID")
                return
        elif len(args) == 2:
            channel_id = int(args[0])
            channel = ctx.guild.get_channel_or_thread(channel_id)
            if not channel:
                await hf.safe_send(ctx, "I couldn't find the channel you specified!")
                return
            message_id = int(args[1])
            to_be_pinned_msg = await channel.fetch_message(message_id)
        else:
            await hf.safe_send(ctx, "You gave too many arguments!")
            return

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        try:
            await to_be_pinned_msg.pin()
        except discord.Forbidden:
            await hf.safe_send(ctx, "I lack permission to pin messages in this channel")

    @commands.command()
    async def log(self, ctx, *, args="None"):
        """Same as `;warn` but it adds `-s` into the reason which makes it just silently log the warning
        without sending a notification to the user."""
        warn = self.bot.get_command('warn')
        if args:
            args += ' -s'
        else:
            args = ' -s'
        emb = await ctx.invoke(warn, args=args)
        return emb

    @commands.command(aliases=['channel_helper', 'cm', 'ch'])
    @hf.is_admin()
    async def channel_mod(self, ctx, *, user):
        """Assigns a channel mod. You must do this command in the channel you
        where you wish to assign them as a channel helper.

        Usage (in the channel): `;cm <user name>`"""
        config = self.bot.db['channel_mods'].setdefault(str(ctx.guild.id), {})
        user = await hf.member_converter(ctx, user)
        if not user:
            await ctx.invoke(self.list_channel_mods)
            return
        if str(ctx.channel.id) in config:
            if user.id in config[str(ctx.channel.id)]:
                await hf.safe_send(ctx, "That user is already a channel mod in this channel.")
                return
            else:
                config[str(ctx.channel.id)].append(user.id)
        else:
            config[str(ctx.channel.id)] = [user.id]
        await ctx.message.delete()
        await hf.safe_send(ctx, f"Set {user.name} as a channel mod for this channel", delete_after=5.0)

    @commands.command(aliases=['list_channel_helpers', 'lcm', 'lch'])
    async def list_channel_mods(self, ctx):
        """Lists current channel mods"""
        output_msg = '```md\n'
        if str(ctx.guild.id) not in self.bot.db['channel_mods']:
            return
        config = self.bot.db['channel_mods'][str(ctx.guild.id)]
        for channel_id in config.copy():
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                await hf.safe_send(ctx, f"Removing deleted channel {channel_id} from list with helpers "
                                        f"{', '.join([str(i) for i in config[channel_id]])}")
                del config[channel_id]
                continue
            output_msg += f"#{channel.name}\n"
            for user_id in config[channel_id]:
                user = self.bot.get_user(int(user_id))
                if not user:
                    await hf.safe_send(ctx, f"<@{user_id}> was not found.  Removing from list...")
                    config[channel_id].remove(user_id)
                    continue
                output_msg += f"{user.display_name}\n"
            output_msg += '\n'
        output_msg += '```'
        await hf.safe_send(ctx, output_msg)

    @commands.command(aliases=['rcm', 'rch'])
    @hf.is_admin()
    async def remove_channel_mod(self, ctx, user):
        """Removes a channel mod. You must do this in the channel they're a channel mod in.

        Usage: `;rcm <user name>`"""
        config = self.bot.db['channel_mods'].setdefault(str(ctx.guild.id), {})
        user_obj = await hf.member_converter(ctx, user)
        if user_obj:
            user_id = user_obj.id
            user_name = user_obj.name
        else:
            try:
                user_id = int(user)
                user_name = user
            except ValueError:
                await hf.safe_send(ctx, "I couldn't parse the user you listed and couldn't find them in the server. "
                                        "Please check your input.", delete_after=5.0)
                return
            await hf.safe_send(ctx, "Note: I couldn't find that user in the server.", delete_after=5.0)
        if str(ctx.channel.id) in config:
            if user_id not in config[str(ctx.channel.id)]:
                await hf.safe_send(ctx, "That user is not a channel mod in this channel. You must call this command "
                                        "in their channel.")
                return
            else:
                config[str(ctx.channel.id)].remove(user_id)
                if not config[str(ctx.channel.id)]:
                    del config[str(ctx.channel.id)]
        else:
            return
        await ctx.message.delete()
        await hf.safe_send(ctx, f"Removed {user_name} as a channel mod for this channel", delete_after=5.0)

    @commands.command(aliases=['staff'])
    @commands.check(any_channel_mod_check)
    async def staffrole(self, ctx):
        """You can add/remove the staff role from yourself with this"""
        staffrole = ctx.guild.get_role(642782671109488641)
        if staffrole in ctx.author.roles:
            await ctx.author.remove_roles(staffrole)
            await hf.safe_send(ctx, "I've removed the staff role from you")
        else:
            try:
                await ctx.author.add_roles(staffrole)
            except discord.Forbidden:
                await hf.safe_send(ctx,
                                   "I lack the ability to attach the staff role. Please make sure I have the ability "
                                   "to manage roles, and that the staff role isn't above my highest user role.")
                return
            await hf.safe_send(ctx, "I've given you the staff role.")

    @commands.group(invoke_without_command=True)
    async def staffping(self, ctx):
        """Subscribe yourself to staff ping notifications in your DM for when the staff role is pinged on this server"""
        if str(ctx.guild.id) not in self.bot.db['staff_ping']:
            self.bot.db['staff_ping'][str(ctx.guild.id)] = {'users': []}
        subscribed_users = self.bot.db['staff_ping'][str(ctx.guild.id)]['users']
        if ctx.author.id in subscribed_users:
            subscribed_users.remove(ctx.author.id)
            await hf.safe_send(ctx, "You will no longer receive notifications for staff pings.")
        else:
            subscribed_users.append(ctx.author.id)
            await hf.safe_send(ctx, "You will receive notifications for staff pings.")

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
            await hf.safe_send(ctx, f"I've set the notification channel for staff pings as {ctx.channel.mention}.")
            return

        channel = role = None
        if regex := re.search(r"^<?#?@?&?(\d{17,22})>$", input_id):  # a channel or role mention/ID
            object_id = int(regex.group(1))
            channel = self.bot.get_channel(object_id)
            role = ctx.guild.get_role(object_id)
            if channel:
                config['channel'] = channel.id
                await hf.safe_send(ctx, f"I've set the notification channel for staff pings to {channel.mention}.")
            elif role:
                config['role'] = role.id
                await hf.safe_send(ctx, f"I've set the watched staff role to **{role.name}** (`{role.mention}`)")

        if not channel and not role:
            await hf.safe_send(ctx, f"I couldn't figure out what you wanted to do.")
            await hf.safe_send(ctx, ctx.command.help)

    @commands.command(aliases=['r', 't', 'tag'])
    @commands.check(any_channel_mod_check)
    async def role(self, ctx, *, args):
        """Assigns a role to a user. Type `;role <user> <tag codes>`. You can specify\
        multiple languages, fluent languages, or "None" to take away roles. Username must not have spaces or be \
        surrounded with quotation marks.

        If you don't specify a user, then it will find the last user in the channel without a role. *If you do this,\
        you can only specify one role!*

        __Tag codes:__
        - English Native: `english`,  `en`,  `ne`,  `e`
        - Spanish Native: `spanish`,  `sn`,  `ns`,  `s`
        - Other Language: `other`,  `ol`,  `o`
        - Fluency roles: `ee`,  `ae`,  `ie`,  `be`,  `es`,  `as`,  `is`,  `bs`
        (Expert, Advanced, Intermediate, Beginner for English and Spanish)
        - Learning Roles: `le`,  `ls`
        - Heritage Roles: `he`,  `hs`
        - Remove all roles: `none`,  `n`

        __Examples:__
        - `;role @Ryry013 e` → *Gives English to Ryry013*
        - `;role spanish`  → *Gives to the last roleless user in the channel*
        - `;r Abelian e o as` → *Give English, Other, and Advanced Spanish*
        - `;r "Long name" e` → *Give English to "Long name"*
        - `;r Ryry013 none` → *Take away all roles from Ryry013*"""
        if ctx.guild.id != SP_SERV:
            return
        english = ctx.guild.get_role(243853718758359040)
        spanish = ctx.guild.get_role(243854128424550401)
        other = ctx.guild.get_role(247020385730691073)

        expertenglish = ctx.guild.get_role(709499333266899115)
        advancedenglish = ctx.guild.get_role(708704078540046346)
        intermediateenglish = ctx.guild.get_role(708704480161431602)
        beginnerenglish = ctx.guild.get_role(708704491180130326)

        expertspanish = ctx.guild.get_role(709497363810746510)
        advancedspanish = ctx.guild.get_role(708704473358532698)
        intermediatespanish = ctx.guild.get_role(708704486994215002)
        beginnerspanish = ctx.guild.get_role(708704495302869003)

        learningenglish = ctx.guild.get_role(247021017740869632)
        learningspanish = ctx.guild.get_role(297415063302832128)

        heritageenglish = ctx.guild.get_role(846112293422497793)
        heritagespanish = ctx.guild.get_role(402148856629821460)

        language_roles = [english, spanish, other]
        all_roles = [english, spanish, other,
                     expertenglish, advancedenglish, intermediateenglish, beginnerenglish,
                     expertspanish, advancedspanish, intermediatespanish, beginnerspanish,
                     learningenglish, learningspanish, heritageenglish, heritagespanish]
        langs_dict = {'english': english, 'e': english, 'en': english, 'ne': english,
                      's': spanish, 'spanish': spanish, 'sn': spanish, 'ns': spanish,
                      'other': other, 'ol': other, 'o': other,
                      'ee': expertenglish, 'ae': advancedenglish, 'ie': intermediateenglish, 'be': beginnerenglish,
                      'es': expertspanish, 'as': advancedspanish, 'is': intermediatespanish, 'bs': beginnerspanish,
                      'le': learningenglish, 'ls': learningspanish, 'he': heritageenglish, 'hs': heritagespanish,
                      'none': None, 'n': None}

        args = args.split()
        if len(args) > 1:  # ;r ryry013 english
            user = await hf.member_converter(ctx, args[0])
            if not user:
                return
            langs = [lang.casefold() for lang in args[1:]]

        elif len(args) == 1:  # something like ;r english
            if args[0].casefold() in ['none', 'n']:
                await hf.safe_send(ctx, "You can't use `none` and not specify a name.")
                return
            langs = [args[0].casefold()]

            user = None  # if it goes through 10 messages and finds no users without a role, it'll default here
            async for message in ctx.channel.history(limit=10):
                found = None
                for role in language_roles:  # check if they already have a role
                    if role in message.author.roles:
                        found = True
                if not found:
                    user = message.author
            if not user:
                await hf.safe_send(ctx, "I couldn't find any users in the last ten messages without a native role.")
                return

        else:  # no args
            await hf.safe_send(ctx, "Gimme something at least! Run `;help role`")
            return

        langs = [lang.casefold() for lang in langs]
        if 'none' in langs or 'n' in langs:
            none = True
            if len(langs) > 1:
                await hf.safe_send(ctx, "If you specify `none`, please don't specify other languages too. "
                                        "That's confusing!")
                return
        else:
            none = False

        for lang in langs:
            if lang not in langs_dict:
                await hf.safe_send(ctx, "I couldn't tell which language you're trying to assign. Type `;help r`")
                return
        if not user:
            await hf.safe_send(ctx, "I couldn't tell who you wanted to assign the role to. `;r <name> <lang>`")
            return

        # right now, user=a member object, lansg=a list of strings the user typed o/e/s/other/english/spanish/etc
        langs = [langs_dict[lang] for lang in langs]  # now langs is a list of role objects
        removed = []
        for role in all_roles:
            if role in user.roles:
                removed.append(role)
        if removed:
            await user.remove_roles(*removed)
        if not none:
            try:
                await user.add_roles(*langs)
            except discord.Forbidden:
                await hf.safe_send(ctx,
                                   "I lack the ability to attach the roles. Please make sure I have the ability "
                                   "to manage roles, and that the role isn't above my highest user role.")
                return

        if none and not removed:
            await hf.safe_send(ctx, "There were no roles to remove!")
        elif none and removed:
            await hf.safe_send(ctx, f"I've removed the roles of {', '.join([r.mention for r in removed])} from "
                                    f"{user.display_name}.")
        elif removed:
            await hf.safe_send(ctx, f"I assigned {', '.join([r.mention for r in langs])} instead of "
                                    f"{', '.join([r.mention for r in removed])} to {user.display_name}.")
        else:
            await hf.safe_send(ctx, f"I assigned {', '.join([r.mention for r in langs])} to {user.display_name}.")

    @commands.group(aliases=['warnlog', 'ml', 'wl'], invoke_without_command=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def modlog(self, ctx: commands.Context, id_in, delete_parameter: Optional[int] = None, post_embed=True):
        """View modlog of a user"""
        if str(ctx.guild.id) not in ctx.bot.db['modlog']:
            return
        config = ctx.bot.db['modlog'][str(ctx.guild.id)]
        member: discord.Member = await hf.member_converter(ctx, id_in)
        if member:
            user: Optional[Union[discord.User, discord.Member]] = member
            username = f"{member.name}#{member.discriminator} ({member.id})"
            user_id = str(member.id)
        else:
            try:
                user = await self.bot.fetch_user(int(id_in))
                username = f"{user.name}#{user.discriminator} ({user.id})"
                user_id = id_in
            except discord.NotFound:
                user = None
                username = user_id = "UNKNOWN USER"
            except discord.HTTPException:
                await hf.safe_send(ctx, "Your ID was not properly formatted. Try again.")
                return
            except ValueError:
                await hf.safe_send(ctx, "I couldn't find the user you were looking for. If they left the server, "
                                        "use an ID")
                return

        #
        #
        # ######### Start building embed #########
        #
        #

        if not member and not user:  # Can't find user at all
            emb = hf.red_embed("")
            emb.set_author(name="COULD NOT FIND USER")

        else:

            #
            #
            # ######### Check whether the user is muted or banned #########
            #
            #

            # Check DB for mute entry
            muted = False
            unmute_date_str: str  # unmute_date looks like "2021/06/26 23:24 UTC"
            if unmute_date_str := self.bot.db['mutes'] \
                    .get(str(ctx.guild.id), {}) \
                    .get('timed_mutes', {}) \
                    .get(user_id, None):
                muted = True
                unmute_date = datetime.strptime(unmute_date_str, "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
                unmute_time_left_str = format_interval(unmute_date - discord.utils.utcnow())
            else:
                unmute_time_left_str = None

            # Check DB for voice mute entry
            voice_muted = False
            voice_unmute_time_left_str: Optional[str]  # unmute_date looks like "2021/06/26 23:24 UTC"
            if voice_unmute_time_left_str := self.bot.db['voice_mutes'] \
                    .get(str(ctx.guild.id), {}) \
                    .get('timed_mutes', {}) \
                    .get(user_id, None):
                voice_muted = True
                unmute_date = datetime.strptime(voice_unmute_time_left_str, "%Y/%m/%d %H:%M UTC").replace(
                    tzinfo=timezone.utc)
                voice_unmute_time_left_str = format_interval(unmute_date - discord.utils.utcnow())

            else:
                voice_unmute_time_left_str = None

            # Check for mute role in member roles
            if member:
                mute_role_id: str = self.bot.db['mutes'].get(str(ctx.guild.id), {}).get('role', 0)
                mute_role: discord.Role = ctx.guild.get_role(int(mute_role_id))
                if mute_role in member.roles:
                    muted = True
                else:
                    muted = False  # even if the user is in the DB for a mute, if they don't the role they aren't muted

            # Check for timeout
            timeout: bool = False
            timeout_time_left_str: Optional[str] = None
            if member:
                if member.is_timed_out():
                    timeout = True
                    timeout_time_left_str = format_interval(member.timed_out_until - discord.utils.utcnow())

            # Check for voice mute role in member roles
            if member:
                mute_role_id: str = self.bot.db['voice_mutes'].get(str(ctx.guild.id), {}).get('role', 0)
                mute_role: discord.Role = ctx.guild.get_role(int(mute_role_id))
                if mute_role in member.roles:
                    voice_muted = True
                else:
                    voice_muted = False  # even if the user is in the DB, if they don't the role they aren't muted

            # Check DB for ban entry
            banned = False  # unban_date looks like "2021/06/26 23:24 UTC"
            if unban_date_str := self.bot.db['bans'] \
                    .get(str(ctx.guild.id), {}) \
                    .get('timed_bans', {}) \
                    .get(user_id, None):
                banned = True
                unban_date = datetime.strptime(unban_date_str, "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
                unban_time_left_str = format_interval(unban_date - discord.utils.utcnow())
            else:
                unban_time_left_str = None  # indefinite ban

            # Check guild ban logs for ban entry
            try:
                ban_entry = await ctx.guild.fetch_ban(user)
                banned = True
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                ban_entry = None
                banned = False  # manual unbans are possible, leaving the ban entry in the DB

            #
            #
            # ############ Author / Title ############
            #
            #

            emb = hf.green_embed("")

            if getattr(user, "nick", None):
                name = f"{str(user)} ({user.nick})\n{user_id}"
            else:
                name = f"{str(user)}\n{user_id}"

            emb.set_author(name=name, icon_url=user.display_avatar.replace(static_format="png").url)

            rai_emoji = str(self.bot.get_emoji(858486763802853387))
            if banned:
                if unban_time_left_str:
                    emb.description = f"{rai_emoji} **`Current Status`** Banned for {unban_time_left_str}"
                else:
                    emb.description = f"{rai_emoji} **`Current Status`** Indefinitely Banned"

            elif voice_muted:
                if voice_unmute_time_left_str:
                    emb.description = f"{rai_emoji} **`Current Status`** Voice Muted for {voice_unmute_time_left_str}"
                else:
                    emb.description = f"{rai_emoji} **`Current Status`** Indefinitely Voice Muted"

            elif muted:
                if unmute_time_left_str:
                    emb.description = f"{rai_emoji} **`Current Status`** Muted for {unmute_time_left_str}"
                else:
                    emb.description = f"{rai_emoji} **`Current Status`** Indefinitely Muted"

            elif timeout:
                if timeout_time_left_str:
                    emb.description = f"{rai_emoji} **`Current Status`** Timeout for {timeout_time_left_str}"
                else:
                    pass

            elif not member:
                if muted and not banned:
                    emb.description += " (user has left the server)"
                elif not muted and not banned:
                    emb.description = f"{rai_emoji} **`Current Status`** : User is not in server"
            else:
                emb.description = f"{rai_emoji} **`Current Status`** : No active incidents"

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
                            message_count[channel] = message_count.get(channel, 0) + user_stats['channels'][channel]
                            days_ago = (discord.utils.utcnow() -
                                        datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)).days
                            if days_ago <= 7:
                                total_msgs_week += user_stats['channels'][channel]
                            total_msgs_month += user_stats['channels'][channel]

            # ### Calculate voice time ###
            voice_time_str = "0h"
            if 'voice' in self.bot.stats.get(str(ctx.guild.id), {}):
                voice_config = self.bot.stats[str(ctx.guild.id)]['voice']['total_time']
                voice_time = 0
                for day in voice_config:
                    if str(member.id) in voice_config[day]:
                        time = voice_config[day][str(member.id)]
                        voice_time += time
                voice_time_str = format_interval(voice_time * 60)

            emb.description += f"\n**`Number of messages M | W`** : {total_msgs_month} | {total_msgs_week}"
            emb.description += f"\n**`Time in voice`** : {voice_time_str}"

        join_history = self.bot.db['joins'].get(str(ctx.guild.id), {}).get('join_history', {}).get(user_id, None)

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
                    invite_creator_id = join_history.get('invite_creator')  # all old join entries don't have this field
                    if not invite_creator_id:
                        invite_obj: Optional[discord.Invite] = discord.utils.find(lambda i: i.code == invite,
                                                                                  await ctx.guild.invites())
                        if not invite_obj:
                            if invite == ctx.guild.vanity_url_code:
                                invite_obj = await ctx.guild.vanity_invite()

                        invite_creator_id = getattr(getattr(invite_obj, "inviter", None), "id", None)

                    invite_creator_user = None
                    if invite_creator_id:
                        try:
                            invite_creator_user = await ctx.bot.fetch_user(invite_creator_id)
                        except (discord.NotFound, discord.HTTPException):
                            pass

                    if invite_creator_user:
                        invite_author_str = \
                            f"by {invite_creator_user.name}#{invite_creator_user.discriminator} " \
                            f"([ID](https://rai/inviter-id-is-I{invite_creator_id}))"
                    else:
                        invite_author_str = f"by unknown user"
                else:
                    invite_author_str = ""

                emb.description += f"\n[**`Used Invite`**]({join_history['jump_url']}) : " \
                                   f"{invite} {invite_author_str}"

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
                emb.color = hf.red_embed("").color
                emb.description += "\n\n***>> NO MODLOG ENTRIES << ***"
                config = []
        else:  # Non-existant user
            config = []

        first_embed = None  # only to be used if the first embed goes over 6000 characters
        for entry in config[-25:]:
            name = f"{config.index(entry) + 1}) {entry['type']}"
            if entry['silent']:
                name += " (silent)"
            incident_time = datetime.strptime(entry['date'], "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
            value = f"<t:{int(incident_time.timestamp())}:f>\n"
            if entry['length']:
                value += f"*For {entry['length']}*\n"
            if entry['reason']:
                value += f"__Reason__: {entry['reason']}\n"
            if entry['jump_url']:
                value += f"[Jump URL]({entry['jump_url']})\n"

            first_embed = None
            if (len(emb) + len(name) + len(value[:1024])) > 6000:
                first_embed = emb.copy()
                emb.clear_fields()

            emb.add_field(name=name, value=value[:1024], inline=False)

        #
        #
        # ############ !! SEND !! ############
        #
        #

        if post_embed:
            if first_embed:  # will only be True if there are two embeds to send
                await hf.safe_send(ctx, user_id, embed=first_embed, delete_after=delete_parameter)

            try:
                # if there's a first embed, this will be the second embed
                await hf.safe_send(ctx, user_id, embed=emb, delete_after=delete_parameter)

            except discord.Forbidden:
                await hf.safe_send(ctx.author, "I lack some permission to send the result of this command")
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
            await hf.safe_send(ctx, "Please write numeric indices equal to or greater than 1 or "
                                    "`-all` to clear the user's modlog.")
            return

        indices = indices.split()  # Creates a list from the prompted argument of the command.
        indices = list(set(indices))  # Removing duplicates from the list.

        if str(ctx.guild.id) not in ctx.bot.db['modlog']:
            return
        config = ctx.bot.db['modlog'][str(ctx.guild.id)]
        member = await hf.member_converter(ctx, user)
        if member:
            user_id = str(member.id)
        else:
            user_id = user
        if user_id not in config:
            await hf.safe_send(ctx, "That user was not found in the modlog")
            return

        config: dict = config[user_id]

        # Performs the deletions:
        if '-a' in indices or '-all' in indices:  # If any of these flags is found in the list:
            del ctx.bot.db['modlog'][str(ctx.guild.id)][user_id]  # clear the modlog...
            await hf.safe_send(ctx, embed=hf.red_embed(f"Deleted all modlog entries for <@{user_id}>."))  # send emb.

        elif len(indices) == 1:  # If there is a single argument given, then:
            try:
                del config[int(indices[0]) - 1]  # delete it from modlog...
            except IndexError:  # except if the index given is not found in config...
                await hf.safe_send(ctx, f"I couldn't find the log #**{indices[0]}**, try doing `;modlog` on the user.")
                return
            except ValueError:  # or if the index given is not an integer...
                await hf.safe_send(ctx, f"The given index is invalid.\n"
                                        f"Please write numeric indices equal to or greater than 1 or "
                                        f"`-all` to clear the user's modlog.")
                return
            await ctx.message.add_reaction('✅')

        else:  # -all was not called, and so there are specific indices to delete:
            def invalid_indices_check(check_index):
                """For indices that are strings or not greater than 0"""
                if not check_index.isdigit():  # is not a digit
                    return True
                else:  # now is a digit
                    if int(check_index) < 1:  # if index is 0 or negative
                        return True

            def not_found_check(check_index, config):
                """For indices not in config"""
                if check_index.isdigit():
                    if int(check_index) >= len(config):
                        return True  # called index is out of range of list

            def indices_check(check_index, not_found):
                if check_index.isdigit() and check_index not in not_found:
                    if int(check_index) >= 1:
                        return True

            invalid_indices: list = [i for i in indices
                                     if invalid_indices_check(i)]  # list of non-digit arguments
            not_found_indices: list = [i for i in indices
                                       if not_found_check(i, config)]  # list of indices not found in modlog
            indices: list = [i for i in indices
                             if indices_check(i, not_found_indices)]  # list of valid arguments
            removed_indices: list = []  # eventual list of modlog entries successfully removed
            indices.sort(key=int)  # Sort it numerically

            n = 1
            for index in indices:  # For every index in the list...
                del config[int(index) - n]  # delete them from the user's modlog.
                n += 1  # For every deleted log, the next ones will be shifted by -1. Therefore,
                # add 1 every time a log gets deleted to counter that.
                removed_indices.append(index)  # for every successfully deleted log, append
                # the index to the corresponding 'removed_indexes' list.
            await ctx.message.add_reaction('✅')

            # Prepare emb to send:
            summary_text = f"Task completed."

            if removed_indices:  # If it removed logs in config:
                removed_indices = ["#**" + i + "**" for i in removed_indices]  # format it...
                rmv_indx_str = f"\n**-** Removed entries: {', '.join(removed_indices)}."  # change it to string...
                summary_text = summary_text + rmv_indx_str  # add it to the text.

            if not_found_indices:  # If there were indices with no match in the config modlog:
                not_found_indices = ["#**" + i + "**" for i in not_found_indices[:10]]  # format for first ten indices
                n_fnd_indx_str = ', '.join(not_found_indices)  # change it to string...
                summary_text = summary_text + f"\n**-** Not found entries: {n_fnd_indx_str}."  # add it to the text.
                if len(not_found_indices) > 10:  # If there are more than ten...
                    summary_text = summary_text[:-1] + f"and {len(not_found_indices) - 10} more..."  # add to the text.

            if invalid_indices:  # If invalid indices were found (TypeError or <= 0):
                invalid_indices = [str(i)[0].lower() for i in invalid_indices[:10]]  # first 10 indices only
                invalid_indices = ["**" + i + "**" for i in invalid_indices]
                invalid_indices = list(set(invalid_indices))  # remove duplicates...
                invalid_indices = sorted(invalid_indices, key=str)  # sort them numerically (aesthetics)...
                inv_indx_str = f"\n**-** Invalid indices: {', '.join(invalid_indices)}."
                summary_text = summary_text + inv_indx_str
                if len(invalid_indices) > 10:
                    summary_text = summary_text[:-1] + f" and {len(invalid_indices) - 10} more..."

            emb = hf.green_embed(summary_text)  # Make the embed with the summary text previously built.
            await hf.safe_send(ctx, embed=emb)  # Send the embed.

    @modlog.command(name="edit", aliases=['reason'])
    @hf.is_admin()
    async def modlog_edit(self, ctx, user, index: int, *, reason):
        """Edit the reason for a selected modlog.  Example: `;ml edit ryry 2 trolling in voice channels`."""
        if str(ctx.guild.id) not in ctx.bot.db['modlog']:
            return
        if re.search(r"\d{1,3}", user):
            if re.search(r"\d{17,22}", str(index)):
                user, index = str(index), int(user)  # swap the variables
        config = ctx.bot.db['modlog'][str(ctx.guild.id)]
        member = await hf.member_converter(ctx, user)
        if member:
            user_id = str(member.id)
        else:
            user_id = user
        if user_id not in config:
            await hf.safe_send(ctx, "That user was not found in the modlog")
            return
        config = config[user_id]
        try:
            old_reason = config[index - 1]['reason']
        except IndexError:
            await hf.safe_send(ctx, f"I couldn't find the mod log with the index {index - 1}. Please check it "
                                    f"and try again.")
            return
        config[index - 1]['reason'] = reason
        await hf.safe_send(ctx, embed=hf.green_embed(f"Changed the reason for entry #{index} from "
                                                     f"```{old_reason}```to```{reason}```"))

    @commands.command()
    @hf.is_admin()
    async def reason(self, ctx: commands.Context,
                     user, index: int, *, reason):
        """Shortcut for `;modlog reason`"""
        await ctx.invoke(self.modlog_edit.invoke, user, index, reason=reason)

    async def apply_mute_role(self,
                              ctx: commands.Context,
                              target: discord.Member,
                              voice_mute: bool) -> dict:
        """For mutes longer than 28 days, apply a mute role"""

        # this function sets the permissions for the Rai_mute role in all the channels
        # returns a list of channel name strings
        async def set_channel_overrides(role):
            failed_channels = []
            for channel in ctx.guild.channels:
                if channel.permissions_synced:
                    continue  # don't break the channel sync, edit the category permission

                # Rai can't edit permissions of these channels
                rai_perms = channel.permissions_for(ctx.guild.me)
                if not rai_perms.manage_permissions:
                    failed_channels.append((channel.name, "manage_permissions"))
                    continue

                role_overwrites = channel.overwrites_for(role)  # if the role already has some perms set, keep those

                # only recheck permissions once per running of Rai
                if voice_mute:
                    if hasattr(self.bot, "checked_voice_mute_role"):
                        if ctx.guild.id in self.bot.checked_voice_mute_role:
                            if role in channel.overwrites:
                                continue
                else:
                    if hasattr(self.bot, "checked_mute_role"):
                        if ctx.guild.id in self.bot.checked_mute_role:
                            if role in channel.overwrites:
                                continue

                if channel.category:
                    # For some reason, if a permission is denied on a category, even if the channel doesn't have
                    # permissions synced, trying to deny the permission in the channel fails, so we need to check
                    category_perms = channel.category.permissions_for(ctx.guild.me)
                else:
                    category_perms = discord.Permissions().all()  # if there's no category then there will be no limits

                send_messages = None
                send_messages_in_threads = None
                attach_files = None
                create_public_threads = None
                add_reactions = None
                connect = None

                # For anything other than a voice channel, set the following text permissions
                if not isinstance(channel, discord.VoiceChannel) and not voice_mute:
                    # if Rai is able to apply the permission
                    # and if the permission isn't already applied
                    if rai_perms.send_messages and category_perms.send_messages \
                            and role_overwrites.send_messages is not False:
                        send_messages = False
                    else:
                        failed_channels.append((channel, 'send_messages'))

                    if rai_perms.add_reactions and category_perms.add_reactions \
                            and role_overwrites.add_reactions is not False:
                        add_reactions = False
                    else:
                        failed_channels.append((channel, 'add_reactions'))

                    if rai_perms.attach_files and category_perms.attach_files \
                            and role_overwrites.attach_files is not False:
                        attach_files = False
                    else:
                        failed_channels.append((channel, 'attach_files'))

                    if rai_perms.send_messages_in_threads and category_perms.send_messages_in_threads \
                            and role_overwrites.send_messages_in_threads is not False:
                        send_messages_in_threads = False
                    else:
                        failed_channels.append((channel, 'send_messages_in_threads'))

                    if rai_perms.create_public_threads and category_perms.create_public_threads \
                            and role_overwrites.create_public_threads is not False:
                        create_public_threads = False
                    else:
                        failed_channels.append((channel, 'create_public_threads'))

                # For voice channels and categories as well, set speaking perms
                if isinstance(channel, discord.VoiceChannel) or isinstance(channel, discord.CategoryChannel):
                    if rai_perms.connect and category_perms.connect \
                            and role_overwrites.connect is not False:
                        connect = False
                    else:
                        failed_channels.append((channel, 'connect'))

                # Once all permissions are set, apply to the channel
                role_overwrites.update(send_messages=send_messages,
                                       send_messages_in_threads=send_messages_in_threads,
                                       attach_files=attach_files,
                                       create_public_threads=create_public_threads,
                                       add_reactions=add_reactions,
                                       connect=connect)
                try:
                    await channel.set_permissions(role, overwrite=role_overwrites)
                except (discord.HTTPException, discord.Forbidden):
                    failed_channels.append((channel, "unknown"))

            # used above, this makes sure this function only fully runs once per server per running of Rai
            if voice_mute:
                if hasattr(self.bot, "checked_voice_mute_role"):
                    if ctx.guild.id not in self.bot.checked_voice_mute_role:
                        self.bot.checked_voice_mute_role.append(ctx.guild.id)
                else:
                    self.bot.checked_voice_mute_role = [ctx.guild.id]
            else:
                if hasattr(self.bot, "checked_mute_role"):
                    if ctx.guild.id not in self.bot.checked_mute_role:
                        self.bot.checked_mute_role.append(ctx.guild.id)
                else:
                    self.bot.checked_mute_role = [ctx.guild.id]

            return failed_channels

        async def first_time_setup():
            if ctx.author == self.bot.user:
                dest = self.bot.get_channel(self.bot.db['mod_channel'][str(ctx.guild.id)])
            else:
                dest = ctx.channel

            role, first = await make_mute_role(ctx, dest, voice_mute)
            if first:  # if the role was newly made
                await hf.safe_send(dest, f"Doing first-time setup of mute module.  I have a `{role.name}` role, "
                                         "add I will add a permission override for it to every channel to prevent "
                                         "communication")

                failed_channels = await set_channel_overrides(role)
                if failed_channels:
                    msg = f"Couldn't add the role permission to the following channels for missing the " \
                          f"listed permissions.  If a muted " \
                          f"member joins this (these) channel(s), they'll be able to type/speak. If you " \
                          f"want to edit the permissions and have Rai reapply all the permissions, please " \
                          f"delete the `rai-mute` role and then try to mute someone again."
                    for channel in failed_channels:
                        msg += f"\n{channel[0]}: {channel[1]}"
                    try:
                        if len(msg) <= 2000:
                            await hf.safe_send(ctx.author, msg)
                        else:
                            await hf.safe_send(ctx.author, msg[:2000])
                            await hf.safe_send(ctx.author, msg[1980:])
                    except discord.HTTPException:
                        pass

            return role

        # Create role, add permissions to channels, and get/create config in database
        if voice_mute:
            db_name = 'voice_mutes'
        else:
            db_name = 'mutes'
        if str(ctx.guild.id) not in self.bot.db[db_name]:
            role = await first_time_setup()
            config = self.bot.db[db_name][str(ctx.guild.id)] = {'role': role.id, 'timed_mutes': {}}

        else:
            config = self.bot.db[db_name][str(ctx.guild.id)]
            role = ctx.guild.get_role(config['role'])
            if not role:  # rai mute role got deleted
                role = await first_time_setup()
                config['role'] = role.id
            await set_channel_overrides(role)

        # ####### Prevent multiple mutes/modlog entries for spamming #######

        try:
            # get last item in user's modlog
            last_modlog = self.bot.db['modlog'][str(ctx.guild.id)][str(target.id)][-1]
            # time of last item in user's modlog
            event_time = datetime.strptime(last_modlog['date'], "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
            # if last modlog was a mute and was less than 70 seconds ago
            if (discord.utils.utcnow() - event_time).total_seconds() < 70 \
                    and last_modlog['type'] in ["Mute", "Voice Mute"]:
                # and if that last modlog's reason started with "Antispam"
                if last_modlog['reason'].startswith("Antispam"):
                    return {}  # Prevents multiple mute calls for spammed text
        except (KeyError, IndexError):
            pass

        if role in target.roles:
            await hf.safe_send(ctx, "This user is already muted (already has the mute role)")
            return {}
        try:
            await target.add_roles(role, reason=f"Muted by {ctx.author.name} in {ctx.channel.name}")
        except discord.Forbidden:
            await hf.safe_send(ctx,
                               "I lack the ability to attach the mute role. Please make sure I have the ability "
                               "to manage roles, and that the mute role isn't above my highest user role.")
            return {}

        if target.voice:  # if they're in a channel, move them out then in to trigger the mute
            try:
                await target.move_to(None, reason="Remove from voice due to Rai mute")
            except (discord.Forbidden, discord.HTTPException):
                await hf.safe_send(ctx, "This user is in voice, but Rai lacks the permission to move users. If you "
                                        "give Rai this permission, then it'll move the user to the AFK channel and "
                                        "back to force the mute into effect. Otherwise, Discord's implementation of "
                                        "the mute won't take effect until the next time the user connects to a "
                                        "new voice channel.")
                pass

        return config

    async def timeout_user(self,
                           ctx: commands.Context,
                           target: discord.Member,
                           reason: str,
                           time_obj: datetime) -> dict:
        """For mutes shorter than 28 days, use the Discord timeout feature"""
        if str(ctx.guild.id) not in self.bot.db['mutes']:
            role, first = await make_mute_role(ctx, ctx.channel, False)
            config = self.bot.db['mutes'][str(ctx.guild.id)] = {'role': role.id, 'timed_mutes': {}}

        else:
            config = self.bot.db['mutes'][str(ctx.guild.id)]

        try:
            await target.timeout(time_obj, reason=reason)
        except discord.Forbidden:
            await hf.safe_send(ctx, f"I failed to timeout {str(target)} ({target.id}). "
                                    f"Please check my permissions "
                                    f"(I can't timeout people higher than me on the rolelist)")
            return {}
        except discord.HTTPException:
            await hf.safe_send(ctx, f"There was some kind of HTTP error that prevented me from timing out {target.id}"
                                    " user. Please try again.")
            return {}

        return config

    @commands.command()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    @commands.max_concurrency(1, commands.BucketType.member)
    async def mute(self, ctx: commands.Context, *, args):
        """Mutes a user.  Syntax: `;mute <time> <member> [reason]`.  Example: `;mute 1d2h Abelian`."""
        # Check for tag from voice mute command
        # if it is there, the code should proceed as if it were a voice mute
        invisible_character = "⠀"
        voice_mute_tag = f"{invisible_character}voice_mute_tag{invisible_character}"
        if args.startswith(voice_mute_tag):
            voice_mute = True
            args = args.replace(voice_mute_tag, '')  # remove tag from args after it's taken
        else:
            voice_mute = False

        # Pull all args out of args variable using hf function
        args = hf.args_discriminator(args=args)
        time_string = args.time_string
        time_obj = args.time_obj
        time_arg = args.time_arg
        length = args.length
        reason = args.reason
        target_ids = args.user_ids

        if not target_ids:
            await hf.safe_send(ctx, "I couldn't understand your command properly. Please mention a user to mute, "
                               "and if you write a time, format it like `2d`, `3h`, `5d6h`, etc.")
            return

        # for channel helpers, limit mute time to three hours
        if not hf.submod_check(ctx):
            if time_string:  # if the channel helper specified a time for the mute
                days = int(length[0])
                hours = int(length[1])
                minutes = int(length[2])
                total_hours = minutes / 60 + hours + days * 24
                if total_hours > 3:
                    time_string = None  # temporarily set to indefinite mute (triggers next line of code)

            # do NOT change this to else, it may have been set to False in the above lines of code
            if not time_string:  # if the channel helper did NOT specify a time for the mute
                time_arg = '3h'
                time_string, length = hf.parse_time(time_arg)  # time_string: str
                time_obj = datetime.strptime(time_string, "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
                await hf.safe_send(ctx.author, "Channel helpers can only mute for a maximum of three "
                                               "hours, so I set the duration of the mute to 3h.")

        silent = False
        if reason:
            if '-s' in reason or '-n' in reason:
                if ctx.guild.id == JP_SERV:
                    await hf.safe_send(ctx, "Maybe you meant to use Ciri?")
                reason = reason.replace(' -s', '').replace('-s ', '').replace('-s', '')
                silent = True

        for target_id in target_ids:
            target = ctx.guild.get_member(target_id)

            # Stop function if user not found
            if not target:
                try:
                    await hf.safe_send(ctx, "I could not find the user.  For warns and mutes, please use either an ID "
                                            "or a mention to the user (this is to prevent mistaking people).")
                except discord.HTTPException:  # Possible if Rai is trying to send a message to itself for automatic mutes
                    pass
                continue

            # If length is 28 days or less, timeout the user using Discord timeout feature
            timeout = False
            if time_obj and not voice_mute:
                if (time_obj - discord.utils.utcnow()).total_seconds() < 28 * 24 * 60 * 60:
                    timeout = True

            if timeout:
                config = await self.timeout_user(ctx, target, reason, time_obj)
                if not config:
                    config = await self.apply_mute_role(ctx, target, voice_mute)
            else:
                config = await self.apply_mute_role(ctx, target, voice_mute)

            if not config:
                return  # Errors should have been already sent in apply_mute_role() function

            if voice_mute:
                description = f"You have been voice muted on {ctx.guild.name} server"
            else:
                description = f"You have been muted on {ctx.guild.name} server"
            emb = hf.red_embed(description)
            emb.color = discord.Color(int('ff8800', 16))  # embed
            if time_arg:
                timestamp = int(time_obj.timestamp())
                emb.add_field(name="Length",
                              value=f"{time_arg} (will be unmuted on <t:{timestamp}> - <t:{timestamp}:R> )",
                              inline=False)
            else:
                emb.add_field(name="Length", value="Indefinite", inline=False)
            if reason:
                if len(reason) <= 1024:
                    emb.add_field(name="Reason", value=reason)
                elif 1024 < len(reason) <= 2048:
                    emb.add_field(name="Reason", value=reason[:1024])
                    emb.add_field(name="Reason (cont.)", value=reason[1024:])
                else:
                    await hf.safe_send(ctx, "Your reason for the mute was too long. Please use less than 2048 "
                                            "characters.")
                    return
            if not silent:
                try:
                    await hf.safe_send(target, embed=emb)
                except discord.Forbidden:
                    await hf.safe_send(ctx, "This user has DMs disabled so I couldn't send the notification. I'll "
                                            "keep them muted but they won't receive the notification for it.")
                    pass

            # Add info about timed mute to database so user can be unmuted later
            if time_string:
                config['timed_mutes'][str(target.id)] = time_string

            # Prepare confirmation message to be sent to ctx channel of mute command
            notif_text = f"**{str(target)}** ({target.id}) has been **muted** from text and voice chats."
            if voice_mute:
                notif_text = notif_text.replace("muted", "voice muted").replace("text and voice", "voice")
            if time_string:
                interval_str = format_interval(timedelta(days=length[0], hours=length[1], minutes=length[2]))
                notif_text = f"{notif_text[:-1]} for {interval_str} (until <t:{int(time_obj.timestamp())}:f>)."
            if reason:
                notif_text += f"\nReason: {reason}"
            emb = hf.red_embed(notif_text)
            if silent:
                emb.description += " (The user was not notified of this)"
            if ctx.author == ctx.guild.me:
                additonal_text = str(target.id)
            else:
                additonal_text = ""
            if ctx.author != self.bot.user and "Nitro" not in reason:
                await hf.safe_send(ctx, additonal_text, embed=emb)

            # Add mute info to modlog
            if voice_mute:
                modlog_config = hf.add_to_modlog(ctx, target, 'Voice Mute', reason, silent, time_arg)
            else:
                modlog_config = hf.add_to_modlog(ctx, target, 'Mute', reason, silent, time_arg)

            # Add info about mute to modlog channel
            modlog_channel = self.bot.get_channel(modlog_config['channel'])
            emb.insert_field_at(0, name="User", value=f"{target.name} ({target.id})", inline=False)
            if ctx.message:
                emb.add_field(name="Jump URL", value=ctx.message.jump_url, inline=False)
            emb.set_footer(text=f"Muted by {ctx.author.name} ({ctx.author.id})")
            try:
                if modlog_channel:
                    if modlog_channel != ctx.channel:
                        await hf.safe_send(modlog_channel, target.id, embed=emb)
            except AttributeError:
                await hf.safe_send(ctx, embed=emb)

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
            target: discord.Member = await hf.member_converter(ctx, target_in)
        else:
            guild = self.bot.get_guild(int(guild))
            target: discord.Member = guild.get_member(int(target_in))
        config = self.bot.db['mutes'][str(guild.id)]
        role = guild.get_role(config['role'])

        voice_role = None
        if str(ctx.guild.id) in self.bot.db['voice_mutes']:
            voice_role = guild.get_role(self.bot.db['voice_mutes'][str(ctx.guild.id)]['role'])

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
                    await hf.safe_send(ctx, "I failed to remove the timeout from the user.")

        if ctx.author != ctx.bot.user:
            emb = discord.Embed(description=f"**{target.name}#{target.discriminator}** has been unmuted.",
                                color=discord.Color(int('00ffaa', 16)))
            await hf.safe_send(ctx, embed=emb)

        if not failed:
            return True


async def setup(bot):
    await bot.add_cog(ChannelMods(bot))
