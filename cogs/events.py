import asyncio
import logging
import os
import re
import string
import urllib
from datetime import timedelta, datetime
from typing import Optional
from urllib.error import HTTPError

import discord
from discord.ext import commands
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from emoji import is_emoji

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
        self.ignored_characters = []
        self.sid = SentimentIntensityAnalyzer()

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

        async def check_untagged_JHO_users():
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

        # await check_untagged_JHO_users()
        # add above function to asyncio event loop as a task
        # noinspection PyAsyncCall
        # asyncio.create_task(check_untagged_JHO_users())
        utils.asyncio_task(check_untagged_JHO_users)

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

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        ctx = await self.bot.get_context(msg)
        
        async def log_bot_messages():
            if not getattr(self.bot, "bot_message_queue", None):
                self.bot.bot_message_queue = hf.MessageQueue(maxlen=100)
            if msg.author.bot:
                self.bot.bot_message_queue.add_message(msg)
        
        await log_bot_messages()
        
        # log unique Rai tracebacks
        async def log_rai_tracebacks():
            traceback_channel_id = int(os.getenv("TRACEBACK_LOGGING_CHANNEL"))
            if msg.channel.id != traceback_channel_id:
                return
            if not msg.author == self.bot.user:
                return
            traceback = msg.content.split("```py")
            if not traceback:
                return
            traceback = traceback[1][:-3]  # last three characters are final ```, take those off too
            if 'rai_tracebacks' not in self.bot.db:
                self.bot.db['rai_tracebacks'] = []
            if traceback in self.bot.db['rai_tracebacks']:
                return
            self.bot.db['rai_tracebacks'].append(traceback)
            new_tracebacks_channel = self.bot.get_channel(1322798523279867935)
            try:
                await new_tracebacks_channel.send(msg.content, embeds=msg.embeds)
            except (discord.HTTPException, discord.Forbidden):
                return
        
        try:
            await log_rai_tracebacks()
        except Exception as e:
            print("Exception in log_rai_tracebacks:", e)
            # don't propagate error because it could lead to an infinite loop of Rai trying to log the error created
            # by the above function itself

        if msg.author.bot:
            # for BurdBot to post questions to AOTW
            if msg.author.id == 720900750724825138:  # BurdBot
                pass
            elif msg.author.id == MODBOT_ID:  # modbot
                pass
            else:
                return

        # if you want something to happen everytime you say something for debugging, put it here
        if msg.author.id == self.bot.owner_id:
            pass
        
        if not self.bot.is_ready:
            return

        ##########################################

        if not msg.guild:  # all code after this has msg.guild requirement
            return
        
        # bots are still allowed below, go one more section down to find no bots + guilds only section

        ##########################################

        # ### Call modlog when people in reports mention IDs or usernames
        async def post_modlog_in_reports():
            if not isinstance(msg.channel, discord.Thread):
                await asyncio.sleep(1)
                try:
                    thread = msg.channel.get_thread(msg.id)
                except AttributeError:
                    return

                if thread:
                    msg.channel = thread
                    content = msg.content
                else:
                    return
            else:
                content = msg.content

            if getattr(msg.channel.owner, "id", 0) != MODBOT_ID:  # modbot
                return
            if msg.author.id != MODBOT_ID:
                return

            # if it's the first message of the thread, ignore all the text past "Recent reports:"
            if msg.id == msg.channel.id:
                content = content.split("**__Recent reports:__**")[0]

            # if it's NOT the first message, then ignore the >>> <@ID>: portion of the message
            else:
                content = re.sub(r">>> <@!?\d{17,22}>: ", "", content)

            # content = msg.content[25:]

            modlog: commands.Command = self.bot.get_command("modlog")

            # Search for direct mentions of IDs
            user_ids = re.findall(r"<?@?!?(\d{17,22})>?", content)
            user_ids = set(user_ids)  # eliminate duplicate IDs
            for user_id in user_ids:
                try:
                    user_id = int(user_id)
                except ValueError:
                    continue
                user: discord.Member = msg.guild.get_member(user_id)
                if not user:
                    try:
                        user: discord.User = await self.bot.fetch_user(user_id)
                    except discord.NotFound:
                        continue
                await ctx.invoke(modlog, id_in=str(user_id))

            # Search for usernamse like Ryry013#1234
            usernames = re.findall(r"(\S+)#(\d{4})", content)
            usernames = set(usernames)  # eliminate duplicate usernames
            for username in usernames:
                user: discord.Member = discord.utils.get(msg.guild.members, name=username[0], discriminator=username[1])
                if user:
                    if user.id in user_ids:
                        continue
                    await ctx.invoke(modlog, id_in=str(user.id))

        await post_modlog_in_reports()

        # ### Replace tatsumaki/nadeko serverinfo posts
        async def replace_tatsumaki_posts():
            if msg.content in ['t!serverinfo', 't!server', 't!sinfo', '.serverinfo', '.sinfo']:
                if msg.guild.id in [JP_SERVER_ID, SP_SERVER_ID, RY_SERVER_ID]:
                    serverinfo: commands.Command = self.bot.get_command("serverinfo")
                    await ctx.invoke(serverinfo)

        await replace_tatsumaki_posts()

        async def log_ciri_warnings():
            if msg.guild.id != JP_SERVER_ID:
                return
            
            if not msg.content.startswith(","):
                return  # only look at ciri commands

            try:
                first_word = msg.content.split()[0][1:]  # minus first character for potential command prefix
                args_list = msg.content.split()[1:]
                args_str = ' '.join(args_list)
            except IndexError:
                return
            
            if first_word not in ['warn', 'log', 'ban']:
                return
            
            args = hf.args_discriminator(args_str)

            if first_word in ['warn', 'log']:
                if first_word == 'warn':
                    incident_type = "Warning"
                    silent = False
                else:
                    incident_type = "Log"
                    silent = True

            elif first_word == 'ban':
                ciri_id = 299335689558949888

                def ciri_check(_m: discord.Message) -> bool:
                    if _m.embeds:
                        e = _m.embeds[0]
                        if not e.description:
                            return False  # or else error in next line
                        if 'Banned' in e.description or "Cancelled" in e.description:
                            return _m.author.id == ciri_id and _m.channel == msg.channel and not e.title

                # Wait for final confirmation message after user has made a choice
                try:
                    m2 = await self.bot.wait_for("message", timeout=30.0, check=ciri_check)
                except asyncio.TimeoutError:
                    return
                else:
                    if 'Banned' not in m2.embeds[0].description:
                        return  # user canceled ban

                    incident_type = 'Ban'
                    silent = False

            else:
                return

            for user_id in args.user_ids:
                user = msg.guild.get_member(int(user_id))
                if not user:
                    try:
                        user = await self.bot.fetch_user(int(user_id))
                    except discord.NotFound:
                        continue
                modlog_entry = hf.ModlogEntry(event=incident_type,
                                              user=user,
                                              guild=ctx.guild,
                                              ctx=ctx,
                                              silent=silent,
                                              reason=args.reason
                                              )
                modlog_entry.add_to_modlog()

        await log_ciri_warnings()
        
        
        

        if msg.author.bot:
            return

        # ###############################################
        #
        # No more bots
        #
        # # ###############################################
        
        # ### Add to MessageQueue
        async def add_to_message_queue():
            if not getattr(self.bot, "message_queue", None):
                self.bot.message_queue = hf.MessageQueue(maxlen=50000)
                
            # only add messages to queue for servers that have edited messages or deleted messages logging enabled
            if not any([self.bot.db['deletes'].get(str(msg.guild.id), {}).get('enable', False),
                        self.bot.db['edits'].get(str(msg.guild.id), {}).get('enable', False)]):
                return
            self.bot.message_queue.add_message(msg)
        
        await add_to_message_queue()
        
        # ### ban users from sensitive_topics on spanish server
        async def ban_from_sens_top():
            banned_role_id = 1163181663459749978
            sensitive_topics_id = 1030545378577219705
            role = msg.guild.get_role(banned_role_id)
            if msg.channel.id != sensitive_topics_id:
                return
            if role not in msg.author.roles:
                return
            
            try:
                await msg.delete()
                await msg.author.send(
                    "You are not allowed to use that channel. Here is the message you tried to send:")
                await msg.author.send(msg.content)
            except (discord.Forbidden, discord.HTTPException):
                pass
        
        await ban_from_sens_top()

        async def wordsnake_channel():
            if msg.channel.id != 1089515759593603173:
                return

            if not hasattr(self.bot, 'last_wordsnake_word'):
                self.bot.last_wordsnake_word = None

            if not msg.content:
                return

            def add_word_to_database(word_to_add):
                if 'wordsnake' not in self.bot.db:
                    self.bot.db['wordsnake'] = {word_to_add: 1}
                else:
                    self.bot.db['wordsnake'][word_to_add] = self.bot.db['wordsnake'].setdefault(word_to_add, 0) + 1

                return self.bot.db['wordsnake'][word_to_add]

            new_word = msg.content.split('\n')[0].casefold()
            new_word = new_word.translate(str.maketrans('', '', string.punctuation))  # remove punctuation
            new_word = new_word.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o") \
                .replace("ú", "u")
            new_word = utils.rem_emoji_url(new_word)

            if not new_word:
                return

            while new_word.endswith(" "):
                new_word = new_word[:-1]

            while new_word.startswith(" "):
                new_word = new_word[1:]

            if self.bot.last_wordsnake_word:
                last_word = self.bot.last_wordsnake_word
                if new_word[0] == last_word[-1]:
                    number_of_times_used = add_word_to_database(new_word)
                    if number_of_times_used == 1:
                        emoji = '🌟'
                    # elif number_of_times_used == 2:
                    #     emoji = '⭐'
                    else:
                        emoji = None

                    if emoji:
                        try:
                            await msg.add_reaction(emoji)
                        except (discord.Forbidden, discord.HTTPException):
                            pass
                else:
                    try:
                        await msg.delete()
                        await msg.channel.send(f"Please send a word starting with the letter `{last_word[-1]}`.")
                        instructions = ("You have to create a word starting with the last letter of the previous word."
                                        "\n→ e.g.: dat**a**, **a**moun**t**, **t**omat**o**, **o**wn ..."
                                        "\n・You can use either English or Spanish words"
                                        "\n\nTienes que crear una palabra que empiece con la última letra de la "
                                        "palabra anterior"
                                        "\n→ p.ej: dad**o**, **o**le**r**, **r**atón, **n**ariz ..."
                                        "\n・Participa usando palabras en inglés, o en español")
                        await msg.author.send(instructions)
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                    return

            self.bot.last_wordsnake_word = new_word

        await wordsnake_channel()

        # ### guild stats
        def guild_stats():
            config: dict = self.bot.db['guildstats']
            if str(msg.guild.id) not in config:
                config[str(msg.guild.id)] = {'messages': {}, 'commands': {}}
            config = config[str(msg.guild.id)]['messages']
            date_str = discord.utils.utcnow().strftime("%Y%m%d")
            config[date_str] = config.setdefault(date_str, 0) + 1

        guild_stats()

        # automatic word filter
        async def wordfilter():
            """
            This catches new users based on admin-set commands in the ;wordfilter command.
            """
            if not msg.guild.me.guild_permissions.ban_members:
                return
            if str(msg.guild.id) not in self.bot.db['wordfilter']:
                return
            config = self.bot.db['wordfilter'][str(msg.guild.id)]
            if not config:
                return

            try:
                time_ago = discord.utils.utcnow() - msg.author.joined_at
            except AttributeError:  # 'User' object has no attribute 'joined_at'
                return

            for filter_word in config:
                if msg.content:
                    if re.search(filter_word, msg.content, flags=re.I):
                        if time_ago < timedelta(minutes=int(config[filter_word])):
                            reason = f"Rai automatic word filter ban:\n{msg.content}"[:512]
                            if len(reason) > 509:
                                reason = reason[:509] + "..."
                            try:
                                await asyncio.sleep(1)
                                await msg.delete()
                            except (discord.Forbidden, discord.NotFound):
                                pass
                            try:
                                await asyncio.sleep(3)
                                await msg.author.ban(reason=reason)
                            except (discord.Forbidden, discord.HTTPException):
                                pass

        await wordfilter()

        """Ping me if someone says my name"""

        async def mention_ping():
            cont = str(msg.content).casefold()

            if msg.author.bot or msg.author.id == 202995638860906496:
                return

            to_check_words = ['ryry', 'ryan', 'らいらい', 'ライライ', '来雷', '雷来']

            if msg.guild.id in [254463427949494292,  # french server
                                970703212107661402,  # english server
                                116379774825267202]:  # nihongo to eigo server
                to_check_words.remove('ryan')  # There's a popular user named "Ryan" in these two servers

            try:
                ryry = msg.guild.get_member(202995638860906496)
                if not ryry:
                    return
                try:
                    if not msg.channel.permissions_for(msg.guild.get_member(202995638860906496)).read_messages:
                        return  # I ain't trying to spy on people
                except discord.ClientException:
                    # probably a message in a forum channel thread without a parent channel
                    # breaks since pycord doesn't support forums yet
                    return

            except AttributeError:
                pass

            found_word = False
            ignored_words = ['ryan gosling', 'ryan reynold']
            for ignored_word in ignored_words:
                if ignored_word in cont.casefold():  # why do people say these so often...
                    cont = re.sub(ignored_word, '', cont, flags=re.IGNORECASE)
                # if msg.guild:
                #     if msg.guild.id == SP_SERVER_ID:
                #         cont = re.sub(r'ryan', '', cont, flags=re.IGNORECASE)

            for to_check_word in to_check_words:
                # if word in cont.casefold():
                if re.search(fr"(^| |\.){to_check_word}($|\W)", cont.casefold()):
                    found_word = True

            if found_word:
                spam_chan = self.bot.get_channel(RYRY_SPAM_CHAN)
                await spam_chan.send(
                    f'**By {msg.author.name} in {msg.channel.mention}** ({msg.channel.name}): '
                    f'\n{msg.content}'
                    f'\n{msg.jump_url}'[:2000])
        await mention_ping()

        async def ori_mention_ping():
            cont = str(msg.content).casefold()
            ori_id = 581324505331400733

            if msg.author.bot or msg.author.id == ori_id:
                return

            to_check_words = ['ori', 'fireside', 'oriana']

            try:
                ori = msg.guild.get_member(ori_id)
                if not ori:
                    return
                try:
                    if not msg.channel.permissions_for(msg.guild.get_member(ori_id)).read_messages:
                        return  # I ain't trying to spy on people
                except discord.ClientException:
                    # probably a message in a forum channel thread without a parent channel
                    # breaks since pycord doesn't support forums yet
                    return

            except AttributeError:
                pass

            found_word = False
            ignored_words = []
            for ignored_word in ignored_words:
                if ignored_word in cont.casefold():  # why do people say these so often...
                    cont = re.sub(ignored_word, '', cont, flags=re.IGNORECASE)

            for to_check_word in to_check_words:
                if re.search(fr"(^| |\.){to_check_word}($|\W)", cont.casefold()):
                    found_word = True

            if found_word:
                spam_chan = self.bot.get_channel(1046904828015677460)
                await spam_chan.send(
                    f'<@{ori_id}>\n**By {msg.author.name} in {msg.channel.mention}** ({msg.channel.name}): '
                    f'\n{msg.content}'
                    f'\n{msg.jump_url}'[:2000])
        await ori_mention_ping()

        """Self mute"""
        try:
            if self.bot.db['selfmute'][str(msg.guild.id)][str(msg.author.id)]['enable']:
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
        except KeyError:
            pass

        """Owner self mute"""
        try:
            if self.bot.selfMute and msg.author.id == self.bot.owner_id:
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
        except AttributeError:
            pass

        """check for mutual servers of banned users"""

        async def check_guilds():
            if msg.guild.id == MODCHAT_SERVER_ID:
                async def check_user(content):
                    bans_channel = msg.channel
                    re_result = re.findall(r'(?:^| |\n)(\d{17,22})', content)
                    users = []
                    if re_result:
                        for user_id in [int(user_id) for user_id in re_result]:
                            if user_id == 270366726737231884:
                                continue
                            user = self.bot.get_user(user_id)
                            if user:
                                users.append(user)
                    for user in users:
                        await hf.ban_check_servers(self.bot, bans_channel, user, ping=False, embed=None)

                await check_user(msg.content)
                for embed in msg.embeds:
                    if embed.description:
                        await check_user(embed.description)

        await check_guilds()

        """chinese server banned words"""

        async def chinese_server_banned_words():
            words = ['动态网自由门', '天安門', '天安门', '法輪功', '李洪志', 'Free Tibet', 'Tiananmen Square',
                     '反右派鬥爭', 'The Anti-Rightist Struggle', '大躍進政策', 'The Great Leap Forward', '文化大革命',
                     '人權', 'Human Rights', '民運', 'Democratization', '自由', 'Freedom', '獨立', 'Independence']
            if msg.guild.id not in [CH_SERVER_ID, 494502230385491978, CL_SERVER_ID, RY_SERVER_ID]:
                return
            word_count = 0
            for word in words:
                if word in msg.content:
                    word_count += 1
                if word_count == 5:
                    mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][str(msg.guild.id)])
                    log_channel = self.bot.get_channel(self.bot.db['bans'][str(msg.guild.id)]['channel'])
                    if discord.utils.utcnow() - msg.author.joined_at > timedelta(minutes=60):
                        await utils.safe_send(mod_channel,
                                           f"Warning: {msg.author.name} may have said the banned words spam message"
                                           f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                           f"\n```{msg.content}"[:1995] + '```')
                        return
                    try:
                        await msg.delete()
                    except discord.Forbidden:
                        await utils.safe_send(mod_channel,
                                           "Rai is lacking the permission to delete messages for the Chinese "
                                           "spam message.")
                    except discord.NotFound:
                        pass

                    try:
                        await asyncio.sleep(3)
                        await msg.author.ban(reason=f"Automatic ban: Chinese banned words spam\n"
                                                    f"{msg.content[:100]}", delete_message_seconds=1*60*60*24)
                    except discord.Forbidden:
                        await utils.safe_send(mod_channel,
                                           "I tried to ban someone for the Chinese spam message, but I lack "
                                           "the permission to ban users.")

                    await utils.safe_send(log_channel, f"Banned {msg.author} for the banned words spam message."
                                                    f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                                    f"\n```{msg.content}"[:1850] + '```')

                    return

        await chinese_server_banned_words()

        # """spanish server welcome channel module"""
        #
        # async def smart_welcome(msg):
        #     if msg.channel.id != SP_SERVER_ID:
        #         return
        #     content = re.sub('> .*\n', '', msg.content.casefold())  # remove quotes in case the user quotes bot
        #     content = content.translate(str.maketrans('', '', string.punctuation))  # remove punctuation
        #     for word in ['hello', 'hi', 'hola', 'thanks', 'gracias']:
        #         if content == word:
        #             return  # ignore messages that are just these single words
        #     if msg.content == '<@270366726737231884>':  # ping to Rai
        #         return  # ignore pings to Rai
        #     english_role = msg.guild.get_role(243853718758359040)
        #     spanish_role = msg.guild.get_role(243854128424550401)
        #     other_role = msg.guild.get_role(247020385730691073)
        #     for role in [english_role, spanish_role, other_role]:
        #         if role in msg.author.roles:
        #             return  # ignore messages by users with tags already
        #     if discord.utils.utcnow() - msg.author.joined_at < timedelta(seconds=3):
        #         return
        #
        #     english = ['english', 'inglés', 'anglohablante', 'angloparlante']
        #     spanish = ['spanish', 'español', 'hispanohablante', 'hispanoparlante', 'castellano']
        #     other = ['other', 'neither', 'otro', 'otra', 'arabic', 'french', 'árabe', 'francés', 'portuguese',
        #              'brazil', 'portuguesa', 'brazilian']
        #     both = ['both', 'ambos', 'los dos']
        #     txt1 = ''
        #     language_score = {'english': 0, 'spanish': 0, 'other': 0, 'both': 0}  # eng, sp, other, both
        #     split = content.split()
        #
        #     def check_language(language, index):
        #         skip_next_word = False  # just defining the variable
        #         for language_word in language:  # language = one of the four word lists above
        #             for content_word in split:  # content_word = the words in their message
        #                 if len(content_word) <= 3:
        #                     continue  # skip words three letters or less
        #                 if content_word in ['there']:
        #                     continue  # this triggers the word "other" so I skip it
        #                 if skip_next_word:  # if i marked this true from a previous loop...
        #                     skip_next_word = False  # ...first, reset it to false...
        #                     continue  # then skip this word
        #                 if content_word.startswith("learn") or content_word.startswith('aprend') \
        #                         or content_word.startswith('estud') or content_word.startswith('stud') or \
        #                         content_word.startswith('fluent'):
        #                     skip_next_word = True  # if they say any of these words, skip the *next* word
        #                     continue  # example: "I'm learning English, but native Spanish", skip "English"
        #                 if LDist(language_word, content_word) < 3:
        #                     language_score[language[0]] += 1
        #
        #     check_language(english, 0)  # run the function I just defined four times, once for each of these lists
        #     check_language(spanish, 1)
        #     check_language(other, 2)
        #     check_language(both, 3)
        #
        #     num_of_hits = 0
        #     for lang in language_score:
        #         if language_score[lang]:  # will add 1 if there's any value in that dictionary entry
        #             num_of_hits += 1  # so "english spanish" gives 2, but "english english" gives 1
        #
        #     if num_of_hits != 1:  # the bot found more than one language statement in their message, so ask again
        #         await msg.channel.send(f"{msg.author.mention}\n"
        #                                f"Hello! Welcome to the server!          Is your **native language**: "
        #                                f"__English__, __Spanish__, __both__, or __neither__?\n"
        #                                f"¡Hola! ¡Bienvenido(a) al servidor!    ¿Tu **idioma materno** es: "
        #                                f"__el inglés__, __el español__, __ambos__ u __otro__?")
        #         return
        #
        #     if msg.content.startswith(';') or msg.content.startswith('.'):
        #         return
        #
        #     if language_score['english']:
        #         txt1 = " I've given you the `English Native` role! ¡Te he asignado el rol de `English Native`!\n\n"
        #         try:
        #             await msg.author.add_roles(english_role, *category_roles)
        #         except discord.NotFound:
        #             return
        #     if language_score['spanish']:
        #         txt1 = " I've given you the `Spanish Native` role! ¡Te he asignado el rol de `Spanish Native!`\n\n"
        #         try:
        #             await msg.author.add_roles(spanish_role, *category_roles)
        #         except discord.NotFound:
        #             return
        #     if language_score['other']:
        #         txt1 = " I've given you the `Other Native` role! ¡Te he asignado el rol de `Other Native!`\n\n"
        #         try:
        #             await msg.author.add_roles(other_role, *category_roles)
        #         except discord.NotFound:
        #             return
        #     if language_score['both']:
        #         txt1 = " I've given you both roles! ¡Te he asignado ambos roles! "
        #         try:
        #             await msg.author.add_roles(english_role, spanish_role, *category_roles)
        #         except discord.NotFound:
        #             return
        #
        #             #  "You can add more roles in <#703075065016877066>:\n" \
        #         #  "Puedes añadirte más en <#703075065016877066>:\n\n" \
        #     txt2 = "Before using the server, please read the rules in <#243859172268048385>.\n" \
        #            "Antes de usar el servidor, por favor lee las reglas en <#243859172268048385>."
        #     await utils.safe_send(msg.channel, msg.author.mention + txt1 + txt2)
        #
        # await smart_welcome(msg)

        async def mods_ping(message_in):
            """mods ping on spanish server"""
            if str(msg.guild.id) not in self.bot.db['staff_ping']:
                return

            if 'channel' not in self.bot.db['staff_ping'][str(msg.guild.id)]:
                return

            config = self.bot.db['staff_ping'][str(msg.guild.id)]
            staff_role_id = config.get("role")  # try to get role id from staff_ping db
            if not staff_role_id:  # no entry in staff_ping db
                staff_role_id = self.bot.db['mod_role'].get(str(msg.guild.id), {}).get("id")
                if isinstance(staff_role_id, list):
                    staff_role_id = staff_role_id[0]
            if not staff_role_id:
                return  # This guild doesn't have a mod role or staff ping role set
            staff_role = msg.guild.get_role(staff_role_id)
            if not staff_role:
                return

            if f"<@&{staff_role_id}>" in message_in.content:
                edited_msg = re.sub(rf'<?@?&?{str(staff_role_id)}>? ?', '', message_in.content)
            else:
                return
            user_id_regex = r"<?@?!?(\d{17,22})>? ?"
            users = re.findall(user_id_regex, edited_msg)
            users = ' '.join(users)
            edited_msg = re.sub(user_id_regex, "", edited_msg)

            interactions = self.bot.get_cog("Interactions")  # get cog, then the function inside the cog
            notif = await interactions.staffping_code(ctx=ctx, users=users, reason=edited_msg)

            if hasattr(self.bot, 'synced_reactions'):
                self.bot.synced_reactions.append((notif, message_in))
            else:
                self.bot.synced_reactions = [(notif, message_in)]

            return

        await mods_ping(msg)

        async def ping_sesion_mod():
            """When the staff role is pinged on the Spanish server,
            this module will ping the Sesion Mod role as well"""
            SESION_CATEGORY_ID = 362398483174522885
            STAFF_ROLE_ID = 642782671109488641
            SESION_MOD_ROLE_ID = 830821949382983751
            if getattr(msg.channel.category, "id", 0) == SESION_CATEGORY_ID:
                if str(STAFF_ROLE_ID) in msg.content:
                    ping = f"<@&{SESION_MOD_ROLE_ID}>"
                elif str(SESION_MOD_ROLE_ID) in msg.content:
                    ping = f"<@&{STAFF_ROLE_ID}>"
                else:
                    return
            else:
                return

            if msg.reference:
                if type(msg.reference.resolved) == discord.Message:
                    await msg.reference.resolved.reply(ping)
                else:
                    await msg.reply(ping)
            else:
                await msg.reply(ping)

            if str(SESION_MOD_ROLE_ID) in msg.content:
                await mods_ping(msg)

        await ping_sesion_mod()

        # ### super_watch
        async def super_watch():
            try:
                config = self.bot.db['super_watch'][str(msg.guild.id)]
            except KeyError:
                return

            if not hasattr(msg.author, "guild"):
                return  # idk why this should be an issue but it returned an error once

            mentioned: Optional[discord.Member] = None
            for user_id in config['users']:
                if user_id in msg.content:
                    user = msg.guild.get_member(int(user_id))
                    if user:
                        mentioned = user

            if str(msg.author.id) in config['users'] or mentioned:
                desc = "❗ "
                which = 'sw'
            elif hf.count_messages(msg.author.id, msg.guild) < 10 and config.get('enable', None):
                minutes_ago_created = int(((discord.utils.utcnow() - msg.author.created_at).total_seconds()) // 60)
                if minutes_ago_created > 60 or msg.channel.id == SP_SERVER_ID:
                    return
                desc = '🆕 '
                which = 'new'
            else:
                return

            if mentioned:
                desc += f"**{str(mentioned)}** ({mentioned.id}) mentioned by {str(msg.author)} ({msg.author.id})"
            else:
                desc += f"**{str(msg.author)}** ({msg.author.id})"
            emb = discord.Embed(description=desc, color=0x00FFFF, timestamp=discord.utils.utcnow())
            emb.set_footer(text=f"#{msg.channel.name}")

            link = f"\n([Jump URL]({msg.jump_url})"
            if which == 'sw':
                if config['users'].get(str(msg.author.id), None):
                    link += f" － [Entry Reason]({config['users'][str(msg.author.id)]})"
            link += ')'
            emb.add_field(name="Message:", value=msg.content[:1024 - len(link)] + link)

            await utils.safe_send(self.bot.get_channel(config['channel']), embed=emb)

        await super_watch()

        # ### Lang check: will check if above 3 characters + hardcore, or if above 15 characters + stats
        async def lang_check() -> (Optional[str], bool):
            detected_lang = None
            is_hardcore = False
            if str(msg.guild.id) not in self.bot.stats:
                return None, False
            stripped_msg = utils.rem_emoji_url(msg)
            check_lang = False

            if msg.guild.id == SP_SERVER_ID and '*' not in msg.content and len(stripped_msg):
                if stripped_msg[0] not in '=;>' and len(stripped_msg) > 3:
                    if isinstance(msg.channel, discord.Thread):
                        channel_id = msg.channel.parent.id
                    elif isinstance(msg.channel, (discord.TextChannel, discord.VoiceChannel)):
                        channel_id = msg.channel.id
                    else:
                        return None, False
                    if channel_id not in self.bot.db['hardcore'][str(SP_SERVER_ID)]['ignore']:
                        hardcore_role = msg.guild.get_role(self.bot.db['hardcore'][str(SP_SERVER_ID)]['role'])
                        if hardcore_role in msg.author.roles:
                            check_lang = True
                            is_hardcore = True

            if str(msg.guild.id) in self.bot.stats:
                if len(stripped_msg) > 15 and self.bot.stats[str(msg.guild.id)].get('enable', None):
                    check_lang = True

            if check_lang:
                try:
                    if msg.guild.id in [SP_SERVER_ID, 1112421189739090101] and msg.channel.id != 817074401680818186:
                        if hasattr(self.bot, 'langdetect'):
                            detected_lang: Optional[str] = hf.detect_language(stripped_msg)
                        else:
                            return None, False
                    else:
                        return None, False
                except (HTTPError, TimeoutError, urllib.error.URLError):
                    pass
            return detected_lang, is_hardcore

        lang, hardcore = await lang_check()
        lang: Optional[str]  # en, sp, None
        hardcore: bool

        # ### Vader Sentiment Analysis
        async def vader_sentiment_analysis():
            if not msg.content:
                return

            if not self.bot.stats.get(str(msg.guild.id), {'enable': False})['enable']:
                return

            if lang != 'en' and msg.guild.id != RY_SERVER_ID:
                return

            to_calculate = msg.content
            show_result = False
            if msg.content.startswith(";sentiment "):
                if not re.search(r"(?:;sentiment @)|(?:;sentiment <?@?!?\d{17,22}>?)", msg.content):
                    to_calculate = msg.content.replace(";sentiment ", "")
                    show_result = True

            sentiment = self.sid.polarity_scores(to_calculate)
            # above returns a dict like {'neg': 0.0, 'neu': 1.0, 'pos': 0.0, 'compound': 0.0}

            if show_result:
                pos = sentiment['pos']
                neu = sentiment['neu']
                neg = sentiment['neg']
                await utils.safe_send(ctx, f"Your sentiment score for the above message:"
                                        f"\n- Positive / Neutral / Negative: +{pos} / n{neu} / -{neg}"
                                        f"\n- Overall: {sentiment['compound']}"
                                        f"\nNote this program is often wrong, and can only check English. If using "
                                        f"this command returned nothing, it means the program couldn't judge "
                                        f"your message.")

            sentiment = sentiment['compound']

            if 'sentiments' not in self.bot.db:
                self.bot.db['sentiments'] = {}

            if str(msg.guild.id) not in self.bot.db['sentiments']:
                self.bot.db['sentiments'][str(msg.guild.id)] = {}
            config = self.bot.db['sentiments'][str(msg.guild.id)]

            if str(msg.author.id) not in config:
                config[str(msg.author.id)] = [sentiment]
            else:
                config[str(msg.author.id)] = config[str(msg.author.id)][-999:]
                config[str(msg.author.id)].append(sentiment)

        await vader_sentiment_analysis()

        """Message counting"""

        # 'stats':
        #     guild id: str:
        #         'enable' = True/False
        #         'messages' (for ,u):
        #             {20200403:
        #                 {user id: str:
        #                   'emoji': {emoji1: 1, emoji2: 3},
        #                   'lang': {'en': 25, 'sp': 30},
        #                   'channels': {
        #                     channel id: str: 30,
        #                     channel id: str: 20}
        #                   'activity': {
        #                     channel id: str: 30,
        #                     channel id: str: 20}
        #                 user_id2:
        #                   emoji: {emoji1: 1, emoji2: 3},
        #                   lang: {'en': 25, 'sp': 30},
        #                   channels: {
        #                     channel1: 40,
        #                     channel2: 10}
        #                 ...}
        #             20200404:
        #                 {user_id1:
        #                   emoji: {emoji1: 1, emoji2: 3},
        #                   lang: {'en': 25, 'sp': 30},
        #                   channels: {
        #                     channel1: 30,
        #                     channel2: 20}
        #                 user_id2:
        #                   emoji: {emoji1: 1, emoji2: 3},
        #                   lang: {'en': 25, 'sp': 30},
        #                   channels: {
        #                     channel1: 40,
        #                     channel2: 10}
        #                 ...}
        #             ...

        async def msg_count():
            if msg.author.bot:
                return
            if str(msg.guild.id) not in self.bot.stats:
                return
            if not self.bot.stats[str(msg.guild.id)]['enable']:
                return

            config = self.bot.stats[str(msg.guild.id)]
            date_str = discord.utils.utcnow().strftime("%Y%m%d")
            if date_str not in config['messages']:
                config['messages'][date_str] = {}
            today = config['messages'][date_str]
            author = str(msg.author.id)
            channel = msg.channel
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                channel = str(msg.channel.id)
            elif isinstance(channel, discord.Thread):
                if msg.channel.parent_id:
                    channel = str(msg.channel.parent_id)
                else:
                    return
            else:
                return

            # message count
            today.setdefault(author, {})
            today[author].setdefault('channels', {})
            today[author]['channels'][channel] = today[author]['channels'].get(channel, 0) + 1

            # activity score
            # if "activity" not in config:
            #     config['activity'] = {date_str: {}}
            #
            # activity: dict = config['activity'].setdefault(date_str, {})
            today[author].setdefault('activity', {})

            if not hasattr(self.bot, "last_message"):
                self.bot.last_message = {}
            if author not in self.bot.last_message:
                self.bot.last_message[author] = {}
            last_message_timestamp = self.bot.last_message[author].setdefault(channel, 0)
            utcnow_timestamp = discord.utils.utcnow().timestamp()
            # if msg.author.id == self.bot.owner_id:
            #     await hf.send_to_test_channel(last_message_timestamp, utcnow_timestamp, author, channel)
            if utcnow_timestamp - last_message_timestamp > 60:
                today[author]['activity'][channel] = today[author]['activity'].get(channel, 0) + 5
                self.bot.last_message[author][channel] = utcnow_timestamp

            # emojis
            emojis = re.findall(r':([A-Za-z0-9_]+):', msg.content)
            for character in msg.content:
                if is_emoji(character):
                    emojis.append(character)
                if utils.is_ignored_emoji(character) and character not in self.ignored_characters:
                    self.ignored_characters.append(character)

            if emojis:
                today[author].setdefault('emoji', {})
                for emoji in emojis:
                    if emoji in ['、']:
                        continue
                    today[author]['emoji'][emoji] = today[author]['emoji'].get(emoji, 0) + 1
            if lang:  # language is detected in separate lang_check function
                today[author].setdefault('lang', {})
                today[author]['lang'][lang] = today[author]['lang'].get(lang, 0) + 1

        await msg_count()

        """Database message counting"""

        """Ultra Hardcore"""
        await hf.uhc_check(msg)

        """Chinese server hardcore mode"""

        async def cn_lang_check(check_hardcore_role=True):
            content = re.sub("^(>>>|>) .*$\n?", "", msg.content, flags=re.M)  # removes lines that start with a quote
            if len(content) > 3:
                if check_hardcore_role:
                    try:
                        role = msg.guild.get_role(self.bot.db['hardcore'][str(msg.guild.id)]['role'])
                    except (KeyError, AttributeError):
                        return

                    if not hasattr(msg.author, 'roles'):
                        return
                    if role not in msg.author.roles:
                        return

                learning_eng = msg.guild.get_role(ENG_ROLE[msg.guild.id])  # this function is only called for two guilds

                ratio = utils.jpenratio(content)
                if ratio is not None:  # it might be "0" so I can't do "if ratio"
                    if learning_eng in msg.author.roles:
                        if ratio < .55:
                            try:
                                await msg.delete()
                            except discord.NotFound:
                                pass
                            if len(content) > 30:
                                await hf.long_deleted_msg_notification(msg)
                    else:
                        if ratio > .45:
                            try:
                                await msg.delete()
                            except discord.NotFound:
                                pass
                            if len(content) > 60:
                                await hf.long_deleted_msg_notification(msg)

        if msg.guild.id in [CH_SERVER_ID, CL_SERVER_ID]:
            try:
                if msg.channel.id in self.bot.db['forcehardcore']:
                    await cn_lang_check(check_hardcore_role=False)

                else:
                    if isinstance(msg.channel, discord.Thread):
                        channel_id = msg.channel.parent.id
                    elif isinstance(msg.channel, discord.TextChannel):
                        channel_id = msg.channel.id
                    else:
                        return
                    config = self.bot.db['hardcore'][str(CH_SERVER_ID)]['ignore']
                    if ('*' not in msg.content and channel_id not in config):
                        await cn_lang_check()
            except KeyError:
                self.bot.db['forcehardcore'] = []

        """Spanish server hardcore"""

        async def spanish_server_hardcore():
            if not hardcore:  # this should be set in the lang_check function
                return
            learning_eng = msg.guild.get_role(247021017740869632)
            learning_sp = msg.guild.get_role(297415063302832128)
            if learning_sp in msg.author.roles:
                delete = "english"
            elif learning_eng in msg.author.roles:
                delete = "spanish"
            else:
                eng_native = msg.guild.get_role(243853718758359040)
                oth_native = msg.guild.get_role(247020385730691073)

                if eng_native or oth_native in msg.author.roles:
                    delete = 'english'
                else:
                    delete = 'spanish'

            if delete == 'spanish':  # learning English, delete all Spanish
                if lang == 'es':
                    try:
                        await msg.delete()
                    except discord.NotFound:
                        return
                    if len(msg.content) > 30:
                        await hf.long_deleted_msg_notification(msg)
            else:  # learning Spanish, delete all English
                if 'holi' in msg.content.casefold():
                    return
                if lang == 'en':
                    try:
                        await msg.delete()
                    except discord.NotFound:
                        return
                    if len(msg.content) > 30:
                        await hf.long_deleted_msg_notification(msg)

        await spanish_server_hardcore()

        """no filter hc"""

        async def no_filter_hc():
            if msg.channel.id == 193966083886153729:
                jpRole = msg.guild.get_role(196765998706196480)
                enRole = msg.guild.get_role(197100137665921024)
                if jpRole in msg.author.roles and enRole in msg.author.roles:
                    return
                ratio = utils.jpenratio(msg.content.casefold())
                nf = "<#193966083886153729>"
                if ratio is None:
                    return
                if jpRole in msg.author.roles:
                    if ratio < .55:
                        try:
                            await msg.delete()
                            await msg.author.send(f"I've deleted your message from {nf}. In that channel, Japanese "
                                                  "people must speak English only. Here is the message I deleted:")

                            await msg.author.send(f"```{msg.content[:1993]}```")
                        except (discord.NotFound, discord.Forbidden):
                            pass
                else:
                    if ratio > .45:
                        try:
                            await msg.delete()
                            await msg.author.send(f"I've deleted your message from {nf}. In that channel, you must "
                                                  "speak Japanese only. Here is the message I deleted:")
                            await msg.author.send(f"```{msg.content[:1993]}```")
                        except (discord.NotFound, discord.Forbidden):
                            pass

        await no_filter_hc()

        """spanish server language switch"""

        async def spanish_server_language_switch():
            if not lang:
                return

            if "*" in msg.content or msg.content.startswith(">"):
                return  # exempt messages with "*" and quotes

            ch = self.bot.get_channel(739127911650557993)
            if msg.channel != ch:
                return

            sp_nat_role = msg.guild.get_role(243854128424550401)
            if sp_nat_role in msg.author.roles:
                if lang == 'es':
                    try:
                        await msg.delete()
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            else:
                if lang == 'en':
                    try:
                        await msg.delete()
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        await spanish_server_language_switch()

        async def delete_messages_in_pinned_posts():
            if not msg.channel.category:
                return

            if msg.channel.category.id != 926269985846866010:
                return

            if not isinstance(msg.channel, discord.Thread):
                return

            if not isinstance(msg.channel.parent, discord.ForumChannel):
                return

            if not msg.channel.flags.pinned:
                return

            if not hf.submod_check(ctx):
                await msg.delete()
                try:
                    await msg.author.send(msg.content)
                    await msg.author.send("Please try to resend the above message in a new post. You can "
                                          "not send messages in the top post.")
                except (discord.Forbidden, discord.HTTPException):
                    return
        await delete_messages_in_pinned_posts()

        async def spanish_server_staff_ping_info_request():
            """This module will watch for users who ping Spanish server staff role (642782671109488641) and
            if they didn't include any text with their ping explaining the issue, it will ask them to do so in
            the future."""
            if msg.guild.id != SP_SERVER_ID:
                return  # only watch for pings in the Spanish server
            if "<@&642782671109488641>" not in msg.content:
                return  # only watch for pings to the staff role
            if msg.channel.category.name == "STAFF TEAM":
                return  # exempt staff channels
            if msg.author.bot:
                return

            # remove the staff ping from the message for the next part
            new_content = msg.content.replace(f"<@&642782671109488641>", "")

            # if the message without the ping is less than 4 characters, it's likely just a ping with no text
            if len(new_content) < 4:
                await ctx.reply("- Thank you for pinging staff. In the future, please also include a description of "
                                "the issue when pinging Staff so moderators who "
                                "arrive into the channel can more quickly understand what is happening.\n"
                                "- Gracias por enviar un ping al staff. En el futuro, por favor, incluye también una "
                                "descripción del problema cuando envíes un ping al "
                                "Staff para que los moderadores que lleguen al canal puedan entender más rápidamente "
                                "lo que está pasando.")

        await spanish_server_staff_ping_info_request()

        async def spanish_server_ban_for_adobe_spam_message():
            """This command will ban users who say the word 'Adobe' in the Spanish server if they have less
            than five messages in the last month."""
            if msg.guild.id != SP_SERVER_ID:
                return
            if not msg.embeds:
                return
            content = msg.embeds[0].description or ''
            if "Adobe Full Espanol GRATiS 2024" not in content or "@everyone" not in content:
                return
            if msg.author.bot:
                return
            recent_messages_count = hf.count_messages(msg.author.id, msg.guild)
            if recent_messages_count > 3:
                return
            try:
                await msg.author.ban(reason="Automatic ban: Inactive user sending the free Adobe scam.")
                incidents_channel = msg.guild.get_channel(808077477703712788)
                await utils.safe_send(incidents_channel, "<@202995638860906496>\n"
                                                      "Above user banned for the Adobe scam message.\n"
                                                      f"(Messages in last month: {recent_messages_count})")
            except (discord.Forbidden, discord.HTTPException):
                pass

        await spanish_server_ban_for_adobe_spam_message()

        # ### antispam
        # ### WARNING: Has a 10 second code-stopping wait sequence inside, keep this as last in on_message
        async def antispam_check():
            if str(msg.guild.id) in self.bot.db['antispam']:
                config = self.bot.db['antispam'][str(msg.guild.id)]
            else:
                return
            if not config['enable']:
                return
            if msg.channel.id in config['ignored']:
                return
            spam_count = 1

            def check(m):
                return m.guild == msg.guild and m.author == msg.author and m.content == msg.content

            while spam_count < config['message_threshhold']:
                try:
                    await self.bot.wait_for('message', timeout=config['time_threshhold'], check=check)
                except asyncio.TimeoutError:
                    return
                else:
                    spam_count += 1

            reason = f"Antispam: \nSent the message `{msg.content[:400]}` {config['message_threshhold']} " \
                     f"times in {config['time_threshhold']} seconds."

            action: str = config['action']

            time_ago: timedelta = discord.utils.utcnow() - msg.author.joined_at
            if ban_threshhold := config.get('ban_override', 0):
                if time_ago < timedelta(minutes=ban_threshhold):
                    action = 'ban'
                    mins_ago = int(time_ago.total_seconds())
                    reason = reason[:-1] + f" (joined {mins_ago} minutes ago)."

            if action == 'ban':
                try:
                    await msg.author.ban(reason=reason)
                except (discord.Forbidden, discord.HTTPException):
                    pass
            elif action == 'kick':
                try:
                    await msg.author.kick(reason=reason)
                except (discord.Forbidden, discord.HTTPException):
                    pass
            elif action == 'mute':
                # prevents this code from running multiple times if they're spamming fast
                if not hasattr(self.bot, "spammer_mute"):
                    self.bot.spammer_mute = []  # a temporary list

                if (spammer_mute_entry := (msg.guild.id, msg.author.id)) in self.bot.spammer_mute:
                    try:
                        await msg.delete()
                    except (discord.Forbidden, discord.NotFound):
                        pass
                    return
                else:
                    self.bot.spammer_mute.append(spammer_mute_entry)  # will remove at end of function

                try:
                    # execute the 1h mute command
                    ctx.author = msg.guild.me
                    mute_command: commands.Command = self.bot.get_command('mute')
                    await ctx.invoke(mute_command, args=f"1h {str(msg.author.id)} {reason}")

                    # notify in mod channel if it is set
                    if str(msg.guild.id) in self.bot.db['mod_channel']:
                        mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][str(ctx.guild.id)])
                        if msg.guild.id == SP_SERVER_ID:
                            mod_channel = msg.guild.get_channel_or_thread(297877202538594304)  # incidents channel
                        if mod_channel:
                            await utils.safe_send(mod_channel, msg.author.id,
                                               embed=utils.red_embed(f"Muted for 1h: {str(msg.author)} for {reason}\n"
                                                                  f"[Jump URL]({msg.jump_url})"))

                # skip if something went wrong
                except (discord.Forbidden, discord.HTTPException):
                    pass

                # remove from temporary list after all actions done
                self.bot.spammer_mute.remove(spammer_mute_entry)

            def purge_check(m):
                return m.author == msg.author and m.content == msg.content

            await msg.channel.purge(limit=50, check=purge_check)

        await antispam_check()

        # WARNING: DONT ADD CODE HERE
        # The above function has a ten second wait time, so all new code must go above it

async def setup(bot):
    await bot.add_cog(Events(bot))
