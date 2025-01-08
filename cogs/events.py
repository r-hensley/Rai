import asyncio
import os
import re
from datetime import timedelta, datetime
from typing import Optional

import discord
from discord.ext import commands

from .utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
BLACKLIST_CHANNEL_ID = 533863928263082014
BANS_CHANNEL_ID = 329576845949534208
MODCHAT_SERVER_ID = 257984339025985546
RYRY_SPAM_CHAN = 275879535977955330
JP_SERVER_ID = 189571157446492161
SP_SERVER_ID = 243838819743432704
CH_SERVER_ID = 266695661670367232
CL_SERVER_ID = 320439136236601344
RY_SERVER_ID = 275146036178059265
FEDE_TESTER_SERVER_ID = 941155953682821201
MODBOT_ID = 713245294657273856

ENG_ROLE = {
    266695661670367232: 266778623631949826,  # C-E Learning English Role
    320439136236601344: 474825178204078081  # r/CL Learning English Role
}
RYRY_RAI_BOT_ID = 270366726737231884





class Events(commands.Cog):
    """This module contains event listeners not in logger.py"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # for debugging infinite loops/crashes etc
    #     @self.bot.event
    #     async def on_message(msg: discord.Message):
    #         if msg.content.startswith(";"):
    #             print(f"[{msg.created_at}] - Command {msg.content} by {msg.author} in {msg.channel}")
    #             # sys.stderr.flush()
    #             sys.stdout.flush()
    #
    #         await self.bot.process_commands(msg)
    #
    # @commands.Cog.listener()
    # async def on_socket_event_type(self, event_type):
    #     if event_type not in ["MESSAGE_CREATE", "TYPING_START", "GUILD_MEMBER_UPDATE", "MESSAGE_UPDATE"]:
    #         print(f"[{discord.utils.utcnow()}] - Event: {event_type}")
    #         # sys.stderr.flush()
    #         sys.stdout.flush()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        to_delete = []
        for x in self.bot.db:
            try:
                for key in self.bot.db[x]:
                    if str(guild.id) == key:
                        to_delete.append((x, key))
            except TypeError:
                continue
        for i in to_delete:
            del (self.bot.db[i[0]][i[1]])

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member):
        """removes people from the waiting list for ;report if they react with '🚫' to a certain message"""

        async def check_untagged_jho_users():
            """This will watch for untagged users in JHO.
            1) Watch for reactions with one of the three colored emojis from Ciri
            2) Check if the user is untagged
            3) Wait 60 minutes
            4) Check again if they're still untagged
            5) Ping WP if so
            """
            other_lang_emoji_id = 815698119810875453
            japanese_lang_emoji_id = 439733745390583819
            english_lang_emoji_id = 439733745591779328
            native_english_role_id = 197100137665921024
            native_japanese_role_id = 196765998706196480
            native_other_role_id = 248982130246418433
            cirilla_id = 581691615010226188

            # is this the japanese server
            if getattr(reaction.message.guild, "id", 0) != JP_SERVER_ID:
                return

            # is emoji just a unicode string (not a custom emoji)
            if isinstance(reaction.emoji, str):
                return

            # is the reaction one of the language color reactions
            if reaction.emoji.id not in [other_lang_emoji_id, japanese_lang_emoji_id, english_lang_emoji_id]:
                return

            # was cirilla the one who reacted to the message
            if user.id != cirilla_id:
                return

            # is the user untagged
            user_role_ids = [role.id for role in user.roles]
            if (native_english_role_id in user_role_ids
                    or native_japanese_role_id in user_role_ids
                    or native_other_role_id in user_role_ids):
                return

            # wait 1 hour
            await asyncio.sleep(60 * 60)

            # refresh author roles
            refreshed_author = reaction.message.channel.guild.get_member(reaction.message.author.id)
            if not refreshed_author:
                return
            refreshed_role_ids = [role.id for role in refreshed_author.roles]

            # check if message author is still untagged
            if (native_english_role_id in refreshed_role_ids
                    or native_japanese_role_id in refreshed_role_ids
                    or native_other_role_id in refreshed_role_ids):
                return

            # send notification to NIF channel
            nif_channel = self.bot.get_channel(1227289089015943258)
            msg_content = reaction.message.content.replace("\n", ". ")
            msg_content = utils.rem_emoji_url(msg_content)
            msg = (f"User {refreshed_author.mention} has potentially sent a message with their native language and is "
                   f"still untagged:\n>>> [{msg_content}](<{reaction.message.jump_url}>)")
            sent_msg = await nif_channel.send(msg)
            
            # go through last 50 messages in current channel and search for messages starting with
            # "User has been tagged now" by this bot and delete those messages
            async for msg in nif_channel.history(limit=50):
                if msg.author == self.bot.user and msg.content.startswith("User has been tagged now"):
                    await msg.delete()

            # wait for the user to get tagged
            def on_member_update_check(m_before, m_after):
                if m_after.id != refreshed_author.id:
                    return False
                if m_before.roles != m_after.roles:
                    role_ids = [role.id for role in m_after.roles]
                    if (native_english_role_id in role_ids
                            or native_japanese_role_id in role_ids
                            or native_other_role_id in role_ids):
                        return True

            try:
                await self.bot.wait_for('member_update', check=on_member_update_check, timeout=3 * 60 * 60)
            except asyncio.TimeoutError:
                pass
            else:

                new_msg = (f"User has been tagged now!\n"
                           f"~~User {refreshed_author.mention} has potentially sent a message with their native "
                           f"language and is still untagged~~:\n"
                           f">>> ~~[{msg_content}](<{reaction.message.jump_url}>)~~")
                await sent_msg.edit(content=new_msg)

        utils.asyncio_task(check_untagged_jho_users)

        async def remove_from_waiting_list():
            if reaction.emoji == '🚫':
                if user == self.bot.user:
                    return
                if reaction.message.channel == user.dm_channel:
                    config = self.bot.db['report']
                    for guild_id in config:
                        if user.id in config[guild_id]['waiting_list']:
                            config[guild_id]['waiting_list'].remove(user.id)
                            await user.send("Understood.  You've been removed from the waiting list.  Have a nice day.")

                            mod_channel = self.bot.get_channel(self.bot.db["mod_channel"][guild_id])
                            msg_to_mod_channel = f"The user {user.name} was previously on the wait list for the " \
                                                 f"report room but just removed themselves."
                            await utils.safe_send(mod_channel, msg_to_mod_channel)
                            return
                    await user.send("You aren't on the waiting list.")

        await remove_from_waiting_list()

        "I or people with manage messages permission can delete bot messages by attaching X or trash can"

        async def delete_rai_message():
            if str(reaction.emoji) in '🗑':
                if user == self.bot.user:
                    return  # Don't let Rai delete messages that Rai attaches :x: to
                if reaction.message.author == self.bot.user:
                    if user.id == self.bot.owner_id or reaction.message.channel.permissions_for(user).manage_messages:
                        await reaction.message.delete()

        await delete_rai_message()

        "Count emojis for stats"

        def count_emojis_for_stats():
            if user.bot:
                return  # ignore reactions from bots
            if not hasattr(user, 'guild'):
                return  # if not in a guild
            if str(user.guild.id) not in self.bot.stats:
                return  # if guild not in stats counting module
            if self.bot.stats[str(user.guild.id)]['enable']:
                try:
                    emoji = reaction.emoji.name
                except AttributeError:
                    emoji = reaction.emoji
                config = self.bot.stats[str(user.guild.id)]
                date_str = discord.utils.utcnow().strftime("%Y%m%d")
                if date_str not in config['messages']:
                    config['messages'][date_str] = {}
                today = config['messages'][date_str]
                today.setdefault(str(user.id), {})
                today[str(user.id)].setdefault('emoji', {})
                today[str(user.id)]['emoji'][emoji] = today[str(user.id)]['emoji'].get(emoji, 0) + 1

        count_emojis_for_stats()

        async def remove_selfmute_reactions():
            """Remove reactions for if you're self muted"""
            if not reaction.message.guild:
                return
            try:
                if self.bot.db['selfmute'][str(reaction.message.guild.id)][str(user.id)]['enable']:
                    try:
                        await reaction.remove(user)
                    except (discord.Forbidden, discord.NotFound):
                        pass
            except KeyError:
                pass

        await remove_selfmute_reactions()

        async def synchronize_reactions():
            """Synchronize reactions on specified messages (staff pings)"""
            if hasattr(self.bot, 'synced_reactions'):
                # synced_reactions is a list of tuples of paired messages like
                # [ (message_1, message_2), (message_3, message_4), ... ]
                # it's possible to have one message linked to multiple others
                if user.bot and reaction.emoji == "📨":
                    # let the bot copy its own reactions except for the envelope
                    # ignore reactions by the bot except for the checkmark
                    # the checkmark is for the staff ping command, when a user marks it as done,
                    # the bot will attach a checkmark to the embed signifying it
                    return

                for pair in self.bot.synced_reactions:
                    target: Optional[discord.Message] = None

                    if reaction.message == pair[0]:
                        target = pair[1]
                    elif reaction.message == pair[1]:
                        target = pair[0]

                    if target:

                        # don't react to a message that already has the emoji on it
                        # this is to prevent bouncing of the reactions
                        reactions = [r.emoji for r in target.reactions]
                        if reaction.emoji in reactions:
                            return

                        # attach reaction to all linked messages
                        try:
                            await target.add_reaction(reaction)
                        except (discord.Forbidden, discord.HTTPException):
                            return

                        # Resolve staff ping embed and turn it green etc
                        if target.embeds and str(reaction.emoji) in '✅👍':
                            embed = target.embeds[0]
                            if title := embed.title:
                                if title.startswith("Staff Ping"):
                                    new_embed = target.embeds[0]
                                    new_embed.colour = 0x77B255  # green background color of the checkmark ✅
                                    new_embed.title = "~~Staff Ping~~ RESOLVED ✅"
                                    if not user.bot:
                                        new_embed.set_footer(text=f"Resolved by {str(user)}")
                                    await target.edit(view=None, embed=new_embed)

        await synchronize_reactions()

    def reactionroles_get_role(self, payload, guild):
        guild_id = str(payload.guild_id)
        message_id = str(payload.message_id)
        emoji = payload.emoji
        if guild_id in self.bot.db['reactionroles']:
            if message_id in self.bot.db['reactionroles'][guild_id]:
                if emoji.id:
                    emoji_str = str(emoji.id)
                else:
                    emoji_str = emoji.name

                if emoji_str not in self.bot.db['reactionroles'][guild_id][message_id]:
                    return
                role_id = self.bot.db['reactionroles'][guild_id][message_id][emoji_str]
                role = guild.get_role(role_id)
                if not role:
                    del (self.bot.db['reactionroles'][guild_id][message_id][emoji_str])
                    return
                return role

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        if payload.emoji.name == '⬆':
            if payload.channel_id == BLACKLIST_CHANNEL_ID:  # votes on blacklist
                channel = self.bot.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
                ctx = await self.bot.get_context(message)
                ctx.author = self.bot.get_user(payload.user_id)
                ctx.reacted_user_id = payload.user_id
                user_id = message.embeds[0].title.split(' ')[0]
                config = self.bot.db['global_blacklist']
                if user_id not in config['votes']:
                    return
                if str(payload.user_id) in config['residency']:
                    voting_guild_id = config['residency'][str(payload.user_id)]
                    if voting_guild_id not in config['votes'][user_id]['votes']:
                        if message.embeds[0].color != discord.Color(int('ff0000', 16)):
                            blacklist_add: commands.Command = self.bot.get_command("global_blacklist add")
                            # ignore below error in pycharm "Expected Type"
                            # noinspection PyTypeChecker
                            await ctx.invoke(blacklist_add, args=user_id)
                else:
                    print('not in residency')
                    try:
                        await utils.safe_send(ctx.author, "Please claim residency on a server first with "
                                                       "`;global_blacklist residency`")
                    except discord.Forbidden:
                        await utils.safe_send(ctx, "Please claim residency on a server first with `;global_blacklist "
                                                "residency`.")
                    return

            elif payload.channel_id == BANS_CHANNEL_ID:
                channel = self.bot.get_channel(BANS_CHANNEL_ID)
                message = await channel.fetch_message(payload.message_id)
                ctx = await self.bot.get_context(message)
                ctx.author = self.bot.get_user(payload.user_id)
                ctx.reacted_user_id = payload.user_id
                user_id = re.search(r'^.*\n\((\d{17,22})\)', message.embeds[0].description).group(1)
                try:
                    reason = re.search('__Reason__: (.*)$', message.embeds[0].description, flags=re.S).group(1)
                except AttributeError:
                    await utils.safe_send(channel, "I couldn't find the reason attached to the ban log for addition to "
                                                "the GBL.")
                    return
                config = self.bot.db['global_blacklist']
                if str(payload.user_id) in config['residency']:
                    if user_id not in config['blacklist'] and str(user_id) not in config['votes']:
                        blacklist_add: commands.Command = self.bot.get_command("global_blacklist add")
                        await ctx.invoke(blacklist_add,
                                         args=f"{user_id} {reason}\n[Ban Entry]({message.jump_url})")
                else:
                    await utils.safe_send(ctx.author, "Please claim residency on a server first with `;gbl residency`")
                    return

        if payload.emoji.name == '✅':  # captcha
            if str(payload.guild_id) in self.bot.db['captcha']:
                config = self.bot.db['captcha'][str(payload.guild_id)]
                if config['enable']:
                    guild = self.bot.get_guild(payload.guild_id)
                    role = guild.get_role(config['role'])
                    if 'message' not in config:
                        return
                    if payload.message_id == config['message']:
                        try:
                            await guild.get_member(payload.user_id).add_roles(role)
                            return
                        except discord.Forbidden:
                            await self.bot.get_user(202995638860906496).send(
                                'on_raw_reaction_add: Lacking `Manage Roles` permission'
                                f' <#{payload.guild_id}>')

        roles = None
        if payload.guild_id == CH_SERVER_ID:  # chinese
            if payload.emoji.name in '🔥📝🖋🗣🎙📖':
                roles = {'🔥': 496659040177487872,
                         '📝': 509446402016018454,
                         '🗣': 266713757030285313,
                         '🖋': 344126772138475540,
                         '🎙': 454893059080060930,
                         '📖': 655082146494545924}
                server = 1
            else:
                return
        elif payload.guild_id == SP_SERVER_ID:  # spanish/english
            if payload.emoji.name in '🎨🐱🐶🎮table👪🎥❗👚💻📔✏🔥📆':
                roles = {'🎨': 401930364316024852,
                         '🐱': 254791516659122176,
                         '🐶': 349800774886359040,
                         '🎮': 343617472743604235,
                         '👪': 402148856629821460,
                         '🎥': 354480160986103808,
                         '👚': 376200559063072769,
                         '💻': 401930404908630038,
                         '❗': 243859335892041728,
                         '📔': 286000427512758272,
                         '✏': 382752872095285248,
                         '🔥': 526089127611990046,
                         'table': 396080550802096128,
                         '📆': 555478189363822600}
                server = 2
            else:
                server = None
        else:
            server = None

        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)

        assignable_role = self.reactionroles_get_role(payload, guild)
        if assignable_role:
            try:
                await user.add_roles(assignable_role)
            except discord.Forbidden:
                pass

        if not user:
            return

        if not user.bot and server:
            try:
                config = self.bot.db['roles'][str(payload.guild_id)]
            except KeyError:
                return
            if server == 1:
                if payload.message_id != config['message']:
                    return
            elif server == 2:
                if payload.message_id != config['message1'] and payload.message_id != config['message2']:
                    return
            role = guild.get_role(roles[payload.emoji.name])
            try:
                await user.add_roles(role)
            except discord.Forbidden:
                await self.bot.get_user(202995638860906496).send(
                    'on_raw_reaction_add: Lacking `Manage Roles` permission'
                    f'<#{payload.guild_id}>')
            except AttributeError:
                return

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id:
            return

        roles = None
        if payload.guild_id == CH_SERVER_ID:  # chinese
            if not payload.emoji.name:
                return
            if payload.emoji.name in '🔥📝🖋🗣🎙📖':
                roles = {'🔥': 496659040177487872,
                         '📝': 509446402016018454,
                         '🗣': 266713757030285313,
                         '🖋': 344126772138475540,
                         '🎙': 454893059080060930,
                         '📖': 655082146494545924}
                server = 1
            else:
                server = 0
        elif payload.guild_id == SP_SERVER_ID:  # spanish/english
            if payload.emoji.name in '🎨🐱🐶🎮table👪🎥❗👚💻📔✏🔥📆':
                roles = {'🎨': 401930364316024852,
                         '🐱': 254791516659122176,
                         '🐶': 349800774886359040,
                         '🎮': 343617472743604235,
                         '👪': 402148856629821460,
                         '🎥': 354480160986103808,
                         '👚': 376200559063072769,
                         '💻': 401930404908630038,
                         '❗': 243859335892041728,
                         '📔': 286000427512758272,
                         '✏': 382752872095285248,
                         '🔥': 526089127611990046,
                         'table': 396080550802096128,
                         '📆': 555478189363822600}
                server = 2
            else:
                server = 0
        else:
            server = 0

        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)

        assignable_role = self.reactionroles_get_role(payload, guild)
        if assignable_role:
            try:
                await user.remove_roles(assignable_role)
            except discord.Forbidden:
                pass

        if server:
            if user.bot:
                return
            try:
                config = self.bot.db['roles'][str(payload.guild_id)]
            except KeyError:
                return
            if server == 1:
                if payload.message_id != config['message']:
                    return
            elif server == 2:
                if payload.message_id != config['message1'] and payload.message_id != config['message2']:
                    return
            role = guild.get_role(roles[payload.emoji.name])
            try:
                await user.remove_roles(role)
            except discord.Forbidden:
                await self.bot.get_user(202995638860906496).send(
                    'on_raw_reaction_remove: Lacking `Manage Roles` permission'
                    f'<#{payload.guild_id}>')
            except AttributeError:
                return

    @commands.command(hidden=True)
    async def command_into_voice(self, ctx: commands.Context, member: discord.Member, after: discord.VoiceState):
        if not ctx.author == self.bot.user:  # only Rai can use this
            return
        await self.into_voice(member, after)

    async def into_voice(self, member: discord.Member, after: discord.VoiceState):
        if member.bot:
            return
        if after.afk or after.deaf or after.self_deaf or len(after.channel.members) <= 1:
            return
        guild = str(member.guild.id)
        member_id = str(member.id)
        config = self.bot.stats[guild]['voice']
        if member_id not in config['in_voice']:
            config['in_voice'][member_id] = discord.utils.utcnow().timestamp()

    @commands.command(hidden=True)
    async def command_out_of_voice(self, ctx: commands.Context, member: discord.Member):
        if not ctx.author == self.bot.user:
            return
        await self.out_of_voice(member, date_str=None)

    async def out_of_voice(self, member: discord.Member, date_str=None):
        guild = str(member.guild.id)
        member_id = str(member.id)
        config = self.bot.stats[guild]['voice']
        if member_id not in config['in_voice']:
            return

        # calculate how long they've been in voice
        join_time = config['in_voice'][str(member.id)]
        try:
            join_time = float(join_time)
        except ValueError:
            join_time = datetime.strptime(join_time, "%Y/%m/%d %H:%M UTC").timestamp()
        total_length = discord.utils.utcnow().timestamp() - join_time
        hours = total_length // 3600
        minutes = total_length % 3600 // 60
        del config['in_voice'][member_id]

        # add to their total
        if not date_str:
            date_str = discord.utils.utcnow().strftime("%Y%m%d")
        if date_str not in config['total_time']:
            config['total_time'][date_str] = {}
        today = config['total_time'][date_str]
        if member_id not in today:
            today[member_id] = hours * 60 + minutes
        else:
            if isinstance(today[member_id], list):
                today[member_id] = today[member_id][0] * 60 + today[member_id][1]
            today[member_id] += hours * 60 + minutes

    @commands.Cog.listener()
    async def on_voice_state_update(self,
                                    member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        """voice stats"""

        # voice
        # 	in_voice:
        # 		user1:
        # 			enter_utc
        # 	total_time:
        # 		user1: hours
        async def voice_update():
            guild = str(member.guild.id)
            if guild not in self.bot.stats:
                return
            if not self.bot.stats[guild]['enable']:
                return
            if str(member.id) not in self.bot.stats[guild]['voice']['in_voice']:  # not in DB
                if after.self_deaf or after.deaf or after.afk or not after.channel:
                    await self.out_of_voice(member)
                    return
                # joins voice, undeafens, or leaves afk channel
                if not before.channel and after.channel:
                    if len(after.channel.members) == 2:
                        for user in after.channel.members:
                            await self.into_voice(user, after)
                        return
                    else:
                        await self.into_voice(member, after)
                        return
                if (before.self_deaf or before.afk or before.deaf) and not (after.self_deaf or after.afk or after.deaf):
                    await self.into_voice(member, after)
                    return
            else:  # in the database
                if after.self_deaf or after.deaf or after.afk or not after.channel:
                    await self.out_of_voice(member)
                    return

        await voice_update()

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

        async def turkish_server_30_mins_role():
            if before.channel != after.channel:
                if str(member.guild.id) not in self.bot.db['timed_voice_role']:
                    return
                config = self.bot.db['timed_voice_role'][str(member.guild.id)]
                role = member.guild.get_role(config['role'])
                if not before.channel and after.channel and config['remove_when_leave']:
                    await member.remove_roles(role)  # in case there was some bug and the user has the role already
                if not role:
                    await asyncio.sleep(20)  # in case there's some weird temporary discord outage
                    role = member.guild.get_role(config['role'])
                    if not role:
                        del self.bot.db['timed_voice_role'][str(member.guild.id)]
                        return
                if config['channel']:
                    channel = self.bot.get_channel(config['channel'])
                    if after.channel != channel:
                        return
                else:
                    channel = None
                start = discord.utils.utcnow().timestamp()
                while True:
                    try:
                        _, _, aft = await self.bot.wait_for('voice_state_update', timeout=30.0,
                                                            check=lambda m, b, a:
                                                            b.channel != a.channel and m == member)
                        try:
                            if not aft.channel:  # leaving voice
                                if config['remove_when_leave']:
                                    await member.remove_roles(role)
                                return
                            if channel:
                                if aft.channel != channel:
                                    await member.remove_roles(role)
                                    return
                            if aft.afk and config['remove_when_afk']:  # going to afk channel
                                await member.remove_roles(role)
                                return
                        except (discord.HTTPException, discord.Forbidden):
                            await utils.safe_send(member, "I tried to give you a role for being in a voice channel for "
                                                       "over 30 minutes, but either there was some kind of HTML "
                                                       "error or I lacked permission to assign/remove roles. Please "
                                                       "tell the admins of your server, or use the command "
                                                       "`;timed_voice_role` to disable the module.")
                            return

                    except asyncio.TimeoutError:
                        now = discord.utils.utcnow().timestamp()
                        if now - start > 60 * config['wait_time']:
                            try:
                                await member.add_roles(role)
                            except (discord.HTTPException, discord.Forbidden):
                                await utils.safe_send(member,
                                                   "I tried to give you a role for being in a voice channel for "
                                                   "over 30 minutes, but either there was some kind of HTML "
                                                   "error or I lacked permission to assign/remove roles. Please "
                                                   "tell the admins of your server, or use the command "
                                                   "`;timed_voice_role` to disable the module.")
                                return
                        if not member.voice:
                            try:
                                if config['remove_when_leave']:
                                    await member.remove_roles(role)
                            except (discord.HTTPException, discord.Forbidden):
                                await utils.safe_send(member,
                                                   "I tried to give you a role for being in a voice channel for "
                                                   "over 30 minutes, but either there was some kind of HTML "
                                                   "error or I lacked permission to assign/remove roles. Please "
                                                   "tell the admins of your server, or use the command "
                                                   "`;timed_voice_role` to disable the module.")
                                return
                            return

        await turkish_server_30_mins_role()

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

        async def sp_serv_new_user_voice_lock():
            """
            This command prevents users who are new to the server from joining voice.

            They are required to either be in the server for two hours, or have 100 messages in the server.

            If a user has left and rejoined the server, hopefully the 100 message requirement gets them into voice.

            There will also be a "voice approved" role which can override this.
            """
            # uncomment below for testing
            # if member.id in [202995638860906496, 414873201349361664, 416452861816340497 ]:  # ryry, abelian, hermitian
            # return  # for testing

            # If this event is not for someone joining voice, ignore it
            joined = not before.channel and after.channel  # True if they just joined voice
            if not joined:
                return

            # Only function on Spanish server
            if member.guild.id != SP_SERVER_ID:
                return

            # If guild is not spanish server (currently hardcoded)
            guild = self.bot.get_guild(SP_SERVER_ID)
            if not guild:
                return

            # If voice lock not enabled on current server
            config = self.bot.db['voice_lock'].get(str(member.guild.id), {})
            joined_to = after.channel
            if not config.get('categories', {}).get(str(joined_to.category.id), None):
                return

            # A role which exempts the user from any requirements on joining voice
            role = guild.get_role(978148690873167973)
            if not role:
                return

            # If user has role, let them into voice
            if role in member.roles:
                return

            # If the user is a newly made account
            hours_for_new_users = config.get('hours_for_new_users', 24)
            if (discord.utils.utcnow() - member.created_at).total_seconds() > hours_for_new_users * 60 * 60:
                # If user has been in the server for more than three hours, let them into voice
                hours_for_users = config.get('hours_for_users', 3)
                time = hours_for_users
                if (discord.utils.utcnow() - member.joined_at).total_seconds() > hours_for_users * 60 * 60:
                    return

                # If user has more than 100 messages in the last month, let them into voice
                messages_for_users = config.get('messages_for_users', 50)
                if hf.count_messages(member.id, member.guild) > messages_for_users:
                    return
            else:
                time = hours_for_new_users

            # If the code has reached this point, it's failed all the checks, so Rai disconnects user from voice

            # Disconnect user from voice
            voice_channel_joined = after.channel
            try:
                await member.edit(voice_channel=None)
            except (discord.Forbidden, discord.HTTPException):
                return

            t = "You cannot join the voice channels on this server yet. We require the users to have been on the " \
                f"server for at least {str(time)} hours before they can join a voice channel. " \
                "Until then, please enjoy our other channels. Note, if you are a member that has been " \
                "in our server before and you just rejoined, " \
                f"then you can message <@{MODBOT_ID}> to gain special permission to join the voice channels." \
                "\n\n" \
                "Todavía no puedes unirte a los canales de voz de este servidor. Requerimos que los usuarios " \
                f"lleven al menos {time} horas en el servidor antes de poder unirse a un canal de voz. Mientras tanto, " \
                "por favor, disfruta de nuestros otros canales. No obstante, si eres un miembro que ya ha " \
                "estado en nuestro servidor y acabas de unirte nuevamente, puedes enviar un mensaje a " \
                f"<@{MODBOT_ID}> para obtener un permiso especial para unirte a los canales de voz. "
            try:
                await utils.safe_send(member, t)
            except discord.Forbidden:
                bot_channel = guild.get_channel(247135634265735168)
                t = f"{member.mention} {t}"
                try:
                    await utils.safe_send(bot_channel, t)
                except discord.Forbidden:
                    pass

            async def one_minute_voice_lock():
                try:
                    await voice_channel_joined.set_permissions(member, connect=False)
                except (discord.Forbidden, discord.NotFound):
                    return

                await asyncio.sleep(120)

                try:
                    await voice_channel_joined.set_permissions(member, overwrite=None)
                except (discord.Forbidden, discord.NotFound):
                    pass

            try:
                await one_minute_voice_lock()
            except Exception:
                try:
                    await after.channel.set_permissions(member, overwrite=None)
                except (discord.Forbidden, discord.NotFound):
                    pass
                raise

        await sp_serv_new_user_voice_lock()

        async def sp_serv_canti_voice_entry_hack_check():
            joined = after.channel  # True if they joined voice
            if not joined:
                return

            # only work for users that have actually moved channels (not moving someone else then muting themselves)
            if before.channel == after.channel:
                return

            # Only function on Spanish server
            if member.guild.id != SP_SERVER_ID:
                return
            
            # only work if after channel *has* a user_limit
            if after.channel.user_limit == 0:
                return

            # watch for users joining full voice rooms
            if len(after.channel.members) <= after.channel.user_limit:
                return
            
            # only work if member does not have permission to view staff channel already (exempt mods)
            staff_channel = self.bot.get_channel(913886469809115206)
            if staff_channel.permissions_for(member).view_channel:
                return

            # discord.AuditLogAction.member_move
            async for log in member.guild.audit_logs(limit=5,
                                                     user=member,
                                                     action=discord.AuditLogAction.member_move,
                                                     after=discord.utils.utcnow() - timedelta(seconds=15),
                                                     oldest_first=False):
                if log.extra.channel == after.channel:
                    
                    emb = utils.red_embed(f"The user {member.mention} ({member.id}) has potentially moved themselves "
                                       f"into a full channel ({after.channel.mention}). Please check this.")
                    if before.channel.members:
                        list_of_before_users = '- ' + '\n- '.join([m.mention for m in before.channel.members])
                    else:
                        list_of_before_users = ''

                    if after.channel.members:
                        list_of_after_users = '- ' + '\n- '.join([m.mention for m in after.channel.members])
                    else:
                        list_of_after_users = ''

                    emb.add_field(name="Previous Channel",
                                  value=f"{before.channel.mention} ({len(before.channel.members)}/"
                                        f"{before.channel.user_limit})\n{list_of_before_users}")
                    emb.add_field(name="Final Channel",
                                  value=f"{after.channel.mention} ({len(after.channel.members)}/"
                                        f"{after.channel.user_limit})\n{list_of_after_users}")
                    await staff_channel.send(str(member.id), embed=emb)
                    break
        await sp_serv_canti_voice_entry_hack_check()

    @commands.Cog.listener()
    async def on_command(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['guildstats']:
            self.bot.db['guildstats'][str(ctx.guild.id)] = {'messages': {}, 'commands': {}}
        config: dict = self.bot.db['guildstats'][str(ctx.guild.id)]['commands']

        date_str = discord.utils.utcnow().strftime("%Y%m%d")
        config[date_str] = config.setdefault(date_str, 0) + 1

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        # async def auto_modlog():
        #     if thread.owner == MODBOT_ID:  # modbot
        #         print(1)
        #         opening_msg = await thread.parent.fetch_message(987069662053416980)
        #         print(2, opening_msg)
        #         user_id = re.search(r"<@\d{17,22}>", opening_msg.content)
        #         if user_id:
        #             ctx = await self.bot.get_context(opening_msg)
        #             modlog: commands.Command = self.bot.get_command("modlog")
        #             await ctx.invoke(modlog, id_in=user_id)
        # await auto_modlog()

        async def new_post_info():
            if not thread.parent.category:
                return

            # only work in challenges and questions categories of spanish server
            challenge_cat_id = 926269985846866010
            sp_questions_cat_id = 685445852009201674
            en_questions_cat_id = 685446008129585176
            jpserv_jp_questions_cat_id = 360571119150956544
            jpserv_eng_questions_cat_id = 360570891459100672
            jpserv_correct_me_channel_id = 1090095564374417490
            if thread.parent.category.id not in [challenge_cat_id, sp_questions_cat_id, en_questions_cat_id,
                                                 jpserv_jp_questions_cat_id, jpserv_eng_questions_cat_id]:
                if thread.parent.id not in [jpserv_correct_me_channel_id]:
                    return

            if not isinstance(thread.parent, discord.ForumChannel):
                return

            instructions = ("Hello, you've created a question! Once you're satisfied with the responses you've "
                            "received, please close your question by typing `;done`.")

            addition = ("\n\nIf more than three days have passed and no one has responded to your post, you may "
                        "ping either `@Spanish Helper`, `@English Helper`, or a country role like `@AskUSA` or "
                        "`@AskMexico`.")
            if thread.guild.id == SP_SERVER_ID:
                instructions += addition

            await asyncio.sleep(2)  # give time for discord to process thread starter message
            if thread.starter_message:
                await thread.starter_message.reply(instructions)
            else:
                await utils.safe_send(thread, instructions)

        await new_post_info()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if config := self.bot.db['deletes'].get(str(channel.guild.id), {}):
            enable = config['enable']
            log_channel_id = config['channel']
            if not enable or not log_channel_id:
                return
        else:
            return

        log_channel = channel.guild.get_channel(int(log_channel_id))
        cached_messages_in_channel: list[discord.Message] = []
        authors_in_channel = set()
        for m in self.bot.cached_messages:
            if m.channel.id == channel.id:
                cached_messages_in_channel.append(m)
                authors_in_channel.add(m.author)

        if not cached_messages_in_channel:
            return

        text = hf.message_list_to_text(cached_messages_in_channel)
        file = hf.text_to_file(text, f"deleted_channel_{channel.name}_messages.txt")
        embed_text = f"Saving {len(cached_messages_in_channel)} cached messages from deleted channel " \
                     f"__#{channel.name}__.\nThe file contains messages from the following authors:"
        for author in authors_in_channel:
            embed_text += f"\n- M{author.id} ({str(author)})"
            embed_text += f" **x{len([m for m in cached_messages_in_channel if m.author == author])}**"
        emb = utils.red_embed(embed_text)

        await log_channel.send(embed=emb, file=file)

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction):
        # return
        guild = execution.guild
        member = execution.member
        if not guild.me.guild_permissions.manage_guild:
            return

        if str(guild.id) not in self.bot.db['modlog']:
            return

        rule = await execution.fetch_rule()

        if len(rule.actions) > 1:
            if execution.action.type != rule.actions[-1].type:
                return

        # Add main line of text describing what triggered the filter
        if execution.rule_trigger_type == discord.AutoModRuleTriggerType.keyword:
            rule_description = f"Used banned keyword from filter named **{rule.name}**"
        elif execution.rule_trigger_type == discord.AutoModRuleTriggerType.spam:
            rule_description = f"User spammed a message"
        elif execution.rule_trigger_type == discord.AutoModRuleTriggerType.keyword_preset:
            rule_description = f"User triggered one of the default filters: "
            if rule.trigger.presets.profanity:
                rule_description += "Profanity"
            if rule.trigger.presets.sexual_content:
                rule_description += "Sexual Content"
            if rule.trigger.presets.slurs:
                rule_description += "Slurs"
        elif execution.rule_trigger_type == discord.AutoModRuleTriggerType.harmful_link:
            rule_description = f"User sent a potentially harmful link: "
        elif execution.rule_trigger_type == discord.AutoModRuleTriggerType.mention_spam:
            rule_description = f"User spammed mentions: "
        else:
            rule_description = "User triggered some kind of AutoMod rule (unknown type)"

        # Add line if user was muted
        silent = True
        modlog_type = "AutoMod"
        # if discord.AutoModRuleActionType.timeout in rule.actions:
        if execution.action.type == discord.AutoModRuleActionType.timeout:
            silent = False
            modlog_type = "AutoMod Timeout"
            rule_description += "\nUser was **timed out** for this"
        else:
            return  # only log mutes
            # pass  # log everything, including non-mutes

        if execution.matched_content:
            formatted_content = execution.content.replace(execution.matched_content,
                                                          f'**{execution.matched_content}**')
        else:
            formatted_content = execution.content  # if no matched content, just use the content

        reason = (f"{rule_description}\n"
                  f">>> {formatted_content}")

        hf.add_to_modlog(None, [member, guild], modlog_type, reason, silent, execution.action.duration)

    
async def setup(bot):
    await bot.add_cog(Events(bot))
