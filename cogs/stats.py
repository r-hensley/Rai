import os
import io
import re
import random
import sqlite3
import sys
from typing import Union

from datetime import datetime, timedelta, timezone
import asqlite
import discord
from discord.ext import commands
from discord.utils import escape_markdown

import matplotlib.pyplot as plt

from cogs.utils.BotUtils import bot_utils as utils
from .utils import helper_functions as hf
from .utils.helper_functions import format_interval


dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SPAM_CHAN = 275879535977955330


async def add_message_to_database(msg):
    """Record message data in the sqlite database"""
    if not msg.guild:
        return

    # if msg.guild.id not in [266695661670367232, 243838819743432704, 275146036178059265]:
    #     return

    lang = 'en'

    # guild = await db.execute(f"SELECT (rai_id, guild_id) FROM guilds WHERE guild_id = {msg.guild.id}")
    async with asqlite.connect(rf'{dir_path}/database.db') as c:
        async with c.transaction():
            await c.execute(f"INSERT OR IGNORE INTO guilds (guild_id) VALUES ({msg.guild.id})")
            await c.execute(f"INSERT OR IGNORE INTO channels (channel_id) VALUES ({msg.channel.id})")
            await c.execute(f"INSERT OR IGNORE INTO users (user_id) VALUES ({msg.author.id})")

            query = "INSERT INTO messages (message_id, user_id, guild_id, channel_id, language) " \
                "VALUES (?, ?, ?, ?, ?)"
            parameters = (msg.id, msg.author.id,
                          msg.guild.id, msg.channel.id, lang)
            await c.execute(query, parameters)
    print('\n\n', msg.author, msg.content, msg.guild.name, query, parameters)
    sys.stdout.flush()


class Stats(commands.Cog):
    """A module for tracking stats of messages on servers for users to view. Enable/disable the module with `"""

    def __init__(self, bot):
        self.bot = bot
        if not hasattr(self.bot, 'message_pool'):
            self.bot.message_pool = []

    async def cog_check(self, ctx):
        try:
            category_id = ctx.channel.category.id
        except AttributeError:
            return False
        if category_id in [685446008129585176, 685445852009201674]:
            try:
                if ctx.message.content != ";help":
                    await ctx.reply("Please use that command in <#247135634265735168>.")
                return False
            except (discord.Forbidden, discord.HTTPException):
                return False
        if ctx.guild:
            return True
        else:
            raise commands.NoPrivateMessage

    lang_codes_dict = {'af': 'Afrikaans', 'ga': 'Irish', 'sq': 'Albanian', 'it': 'Italian', 'ar': 'Arabic',
                       'ja': 'Japanese', 'az': 'Azerbaijani', 'kn': 'Kannada', 'eu': 'Basque', 'ko': 'Korean',
                       'bn': 'Bengali', 'la': 'Latin', 'be': 'Belarusian', 'lv': 'Latvian', 'bg': 'Bulgarian',
                       'lt': 'Lithuanian', 'ca': 'Catalan', 'mk': 'Macedonian', 'zh-CN': 'Chinese Simplified',
                       'ms': 'Malay', 'zh-TW': 'Chinese Traditional', 'mt': 'Maltese', 'hr': 'Croatian',
                       'no': 'Norwegian', 'cs': 'Czech', 'fa': 'Persian', 'da': 'Danish', 'pl': 'Polish',
                       'nl': 'Dutch', 'pt': 'Portuguese', 'en': 'English', 'ro': 'Romanian', 'eo': 'Esperanto',
                       'ru': 'Russian', 'et': 'Estonian', 'sr': 'Serbian', 'tl': 'Filipino', 'sk': 'Slovak',
                       'fi': 'Finnish', 'sl': 'Slovenian', 'fr': 'French', 'es': 'Spanish', 'gl': 'Galician',
                       'sw': 'Swahili', 'ka': 'Georgian', 'sv': 'Swedish', 'de': 'German', 'ta': 'Tamil',
                       'el': 'Greek', 'te': 'Telugu', 'gu': 'Gujarati', 'th': 'Thai', 'ht': 'Haitian Creole',
                       'tr': 'Turkish', 'iw': 'Hebrew', 'uk': 'Ukrainian', 'hi': 'Hindi', 'ur': 'Urdu',
                       'hu': 'Hungarian', 'vi': 'Vietnamese', 'is': 'Icelandic', 'cy': 'Welsh', 'id': 'Indonesian',
                       'yi': 'Yiddish'}

    @commands.command(aliases=['uc'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def uchannels(self, ctx: commands.Context, *, member_str: str = None):
        if not member_str:
            member = ctx.author
            joined = ctx.author.joined_at
        else:
            member = await utils.member_converter(ctx, member_str)
            if not member:
                joined = None
                member = await utils.user_converter(ctx, member_str)
                if not member:
                    pass
            else:
                joined = member.joined_at

        if isinstance(member, discord.Member):
            member_id = member.id
            if member.nick:
                name_str = f"{escape_markdown(member.name)} ({escape_markdown(member.nick)})"
            else:
                name_str = f"{escape_markdown(member.name)}"
        elif isinstance(member, discord.User):
            member_id = member.id
            name_str = f"{escape_markdown(member.name)} (user left server)"
        else:
            try:
                member_id = int(member_str)
            except ValueError:
                await utils.safe_reply(ctx, "I couldn't find the user.")
                return
            name_str = member_str

        try:
            config = self.bot.stats[str(ctx.guild.id)]['messages']
        except KeyError:
            return

        message_count = {}
        for day in config:
            if str(member_id) in config[day]:
                if 'channels' not in config[day][str(member_id)]:
                    continue
                user = config[day][str(member_id)]
                for channel in user.get('channels', []):
                    message_count[channel] = message_count.get(
                        channel, 0) + user['channels'][channel]
        sorted_msgs = sorted(message_count.items(),
                             key=lambda x: x[1], reverse=True)
        emb = discord.Embed(title=f'Usage stats for {name_str}',
                            description="Last 30 days",
                            color=discord.Color(int('00ccFF', 16)),
                            timestamp=joined)
        lb = ''
        index = 1
        total = 0
        for channel_tuple in sorted_msgs:
            total += channel_tuple[1]
        for channel_tuple in sorted_msgs:
            if ctx.channel.id != 277511392972636161 and channel_tuple[0] == '277511392972636161':
                continue
            if str(ctx.channel.id) not in self.bot.stats[str(ctx.guild.id)]['hidden']:
                if channel_tuple[0] in self.bot.stats[str(ctx.guild.id)]['hidden']:
                    continue
            try:
                channel = ctx.guild.get_channel_or_thread(
                    int(channel_tuple[0]))
                if not channel:
                    continue
                lb += (f"**{index}) {escape_markdown(channel.name)}**: "
                       f"{round((channel_tuple[1] / total) * 100, 2)}% ({channel_tuple[1]})\n")
                index += 1
            except discord.NotFound:
                pass
            if index == 26:
                break
        if not lb:
            await utils.safe_send(ctx, "This user has not said anything in the past 30 days.")
            return
        emb.add_field(name="Top channels", value=lb[:1024])
        await utils.safe_send(ctx, embed=emb)

    @commands.command(aliases=['u'])
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def user(self, ctx, *, member_in: str = None, post_embed=True):
        """Gives info about a user.  Leave the member field blank to get info about yourself."""
        if not member_in:
            member = ctx.author
            user_id = ctx.author.id
            user_name = escape_markdown(ctx.author.name)
        else:
            # remove prefix from IDs like J414873201349361664 or M202995638860906496
            if re.findall(r"[JIMVN]\d{17,22}", member_in):
                member_in = re.sub('[JIMVN]', '', member_in)

            # try to convert the ID to a user or member
            member = await utils.member_converter(ctx, member_in)
            if member:
                user = member
            else:
                user = await utils.user_converter(ctx, member_in)

            if user:
                user_name = escape_markdown(user.name)
                user_id = user.id
            else:
                await utils.safe_send(ctx, "I couldn't find the user.")
                return None

        try:
            _config = self.bot.stats[str(ctx.guild.id)]['messages']
        except KeyError:
            return None

        # If user in bot.db['joindates'], override their join date for users who have left and rejoined server
        if member:
            if str(member.id) in self.bot.db.setdefault('joindates', {}):
                actual_joined_timestamp = self.bot.db['joindates'][str(
                    member.id)]
                member.joined_at = datetime.fromtimestamp(
                    actual_joined_timestamp, tz=timezone.utc)

        # ### Collect all the data from the database ###
        total_activity = hf.count_activity(user_id, ctx.guild)
        total_msgs_month, total_msgs_week, message_count, emoji_count, lang_count = \
            hf.get_stats_per_channel(user_id, ctx.guild)

        # ### Sort the data ###
        sorted_msgs = sorted(message_count.items(),
                             key=lambda x: x[1], reverse=True)
        # looks like [('284045742652260352', 15), ('296491080881537024', 3), ('296013414755598346', 1)]
        sorted_emojis = sorted(emoji_count.items(),
                               key=lambda x: x[1], reverse=True)
        sorted_langs = sorted(lang_count.items(),
                              key=lambda x: x[1], reverse=True)

        # ### Make embed ###
        if member:
            title = f'Usage stats for {str(member)}'
            if member.nick:
                title += f" ({escape_markdown(member.nick)})"
        else:
            title = f'Usage stats for {user_id} ({escape_markdown(user_name)}) (user left server)'
        emb = discord.Embed(title=title,
                            description="Last 30 days",
                            color=discord.Color(int('00ccFF', 16)))
        if member:
            emb.timestamp = member.joined_at
        emb.add_field(name="Messages sent M | W",
                      value=f"{total_msgs_month} | {total_msgs_week}")
        emb.add_field(name="Activity score",
                      value=f"{total_activity} ([?](https://pastebin.com/raw/07xKpDpy))")

        # ### Find top 3 most active channels ###
        good_channels = 0
        hidden = self.bot.stats[str(ctx.guild.id)]['hidden']
        if ctx.channel.id != 277511392972636161 and ctx.guild.id == 243838819743432704:
            for channel in sorted_msgs:
                if channel[0] == '277511392972636161':
                    sorted_msgs.remove(channel)
                    break
        for channel in sorted_msgs.copy():
            if str(ctx.channel.id) in hidden:  # you're in a hidden channel, keep all
                break
            if channel[0] in hidden:  # one of the top channels is a hidden channel, remove
                sorted_msgs.remove(channel)
            else:  # it's not a hidden channel, keep
                good_channels += 1
            if good_channels == 3:  # you have three kept channels
                break

        # ### Format top 3 channels text field / Add field to embed ###
        def format_channel(number):
            channel_id = sorted_msgs[number][0]
            message_percentage = round(
                100 * sorted_msgs[number][1] / total_msgs_month, 2)
            if channel_id == '0':  # category for all deleted channels
                text = f"**#Deleted Channels**: {message_percentage}%⠀\n"
            else:
                _channel = ctx.guild.get_channel_or_thread(int(channel_id))
                text = f"**#{escape_markdown(_channel.name)}**: {message_percentage}%⠀\n"
            return text

        channeltext = ''
        try:
            channeltext += format_channel(0)
            channeltext += format_channel(1)
            channeltext += format_channel(2)
        except IndexError:  # will stop automatically if there's not three channels in the list
            pass

        if channeltext:
            emb.add_field(name="Top Channels:",
                          value=f"{channeltext}")

        # ### Calculate voice time / Add field to embed ###
        voice_time: int = hf.calculate_voice_time(
            user_id, ctx.guild.id)  # number of minutes
        if voice_time:
            emb.add_field(name="Time in voice chats",
                          value=format_interval(voice_time))

        # ### If no messages or voice in last 30 days ###
        if (not total_msgs_month or not sorted_msgs) and not voice_time:
            emb = discord.Embed(title='',
                                description="This user hasn't said anything in the past 30 days",
                                color=discord.Color(int('00ccFF', 16)))
            if member:
                emb.title = f"Usage stats for {escape_markdown(member.name)}"
                if member.nick:
                    emb.title += f" ({escape_markdown(member.nick)})"
                emb.timestamp = member.joined_at
            else:
                emb.title += f"Usage stats for {user_id} {user_name} (this user was not found)"

        # ### Add emojis field ###
        if sorted_emojis:
            value = ''
            counter = 0
            for emoji_tuple in sorted_emojis:
                value += f"{str(emoji_tuple[0])} {str(emoji_tuple[1])} times\n"
                counter += 1
                if counter == 3:
                    break
            if value:
                emb.add_field(name='Most used emojis', value=value)

        # ### Add top langauges field ###
        if sorted_langs:
            value = ''
            counter = 0
            for lang_tuple in sorted_langs:
                if lang_tuple[0] not in self.lang_codes_dict:
                    continue
                percentage = hf.get_language_percentage(user_id, ctx.guild, lang_tuple[0])
                if percentage is None:
                    continue
                if (counter in [0, 1] and percentage > 2.5) or (percentage > 5):
                    value += f"**{self.lang_codes_dict[lang_tuple[0]]}**: {percentage}%\n"
                if counter == 5:
                    break
            if value:
                emb.add_field(name='Most used languages', value=value)

        # ### Calculate join position ###
        if member:
            member_list = ctx.guild.members
            for member_in_list in list(member_list).copy():
                if not member_in_list.joined_at:
                    member_list.remove(member_in_list)
            sorted_members_by_join = sorted([(member, member.joined_at) for member in member_list],
                                            key=lambda x: x[1],
                                            reverse=False)
            join_order = 0
            for i in sorted_members_by_join:
                if i[0].id == member.id:
                    join_order = sorted_members_by_join.index(i)
                    break
            if join_order + 1:
                emb.set_footer(
                    text=f"(#{join_order + 1} to join this server) Joined on:")

        # ### Send ###
        if post_embed:
            try:
                await utils.safe_send(ctx, embed=emb)
            except discord.Forbidden:
                try:
                    await utils.safe_send(ctx, "I lack the permissions to send embeds in this channel")
                    await utils.safe_send(ctx.author, embed=emb)
                except discord.Forbidden:
                    await utils.safe_send(ctx.author, "I lack the permission to send messages in that channel")
        return emb

    @staticmethod
    def make_leaderboard_embed(ctx,
                               channel_in: list[discord.abc.GuildChannel],
                               dict_in: dict[str: int],
                               title: str):
        """
        Dict should look like
        {str(user_id): int(number_of_messages)}
        """
        sorted_dict_list: list[tuple[str, int]] = sorted(dict_in.items(),
                                                         reverse=True, key=lambda x: x[1])
        # sorted_dict_list looks like:
        # [ ('1234', 10), ('4567', 15), ... ]
        emb = discord.Embed(title=title,
                            description="Last 30 days",
                            color=discord.Color(int('00ccFF', 16)),
                            timestamp=discord.utils.utcnow())

        if "Activity Score" in title:
            emb.set_footer(
                text="Try `;lb` or `;chlb` for the message count leaderboard")
        else:
            emb.set_footer(
                text="Try `;alb` or `;achlb` for the activity score leaderboard")

        if channel_in:
            channel_names = [f"#{c.name}" for c in channel_in]
            channel_name_list_string = ', '.join(channel_names)  # looks: "#channel, #channel, ..."
            emb.title += " for " + channel_name_list_string
        number_of_users_found = 0
        found_yourself = False
        for user_id, value in sorted_dict_list:
            # "value" is either a number of messages (text leaderboard),
            # or a number of minutes (voice leaderboard)
            member = ctx.guild.get_member(int(user_id))
            if not member:
                continue
            if number_of_users_found < 24 or \
                    (number_of_users_found == 24 and (found_yourself or member == ctx.author)) \
                    or number_of_users_found > 24 and member == ctx.author:
                if title.startswith("Voice"):
                    # value is counted in minutes
                    value = format_interval(value * 60)
                emb.add_field(name=f"{number_of_users_found + 1}) {escape_markdown(member.name)}",
                              value=value)
            number_of_users_found += 1
            if member == ctx.author:
                found_yourself = True
            if number_of_users_found >= 25 and found_yourself:
                break
        return emb

    async def make_lb(self, ctx, channels_in, db_target='channels'):
        try:
            config = self.bot.stats[str(ctx.guild.id)]['messages']
        except KeyError:
            return
        msg_count = {}

        # if channels_in is passed, calculate the proper list of channels:
        # if it comes from ;lb, it will be "False"
        # if it comes from ;chlb, it will be a (possibly empty) tuple of channel link strings
        if channels_in is False:
            # came from ;lb, take all channels
            channel_obs = []
        elif not channels_in:
            # came from ;chlb but no channel specification, take ctx as specified channel
            if isinstance(ctx.channel, discord.Thread):
                channel_obs = [ctx.channel.parent]
            else:
                channel_obs = [ctx.channel]
        else:  # came from ;chlb with channel specification, take specified channels
            channel_ids = []
            channel_obs = []
            for channel in channels_in:
                channel_ids.append(channel[2:-1])
            for channel_id in channel_ids:
                try:
                    c = ctx.guild.get_channel_or_thread(int(channel_id))
                    if c:
                        if isinstance(c, discord.Thread):
                            c = c.parent
                        channel_obs.append(c)
                    else:
                        await utils.safe_send(ctx,
                                              f"I couldn't find the channel `{channel_id}`.")
                        continue
                except ValueError:
                    await utils.safe_send(ctx,
                                          "Please provide a link to a channel, "
                                          "not just the channel name "
                                          "(e.g. `;chlb #general`), or if you just type `;chlb` "
                                          "it will show the leaderboard for the current channel.")
                    return
            if not channel_obs:
                await utils.safe_send(ctx, "I couldn't find any valid channels.")
                return

        if channel_obs:
            channel_ids = [c.id for c in channel_obs]
        else:
            channel_ids = []
        for day in config:
            for user in config[day]:
                if db_target not in config[day][user]:
                    continue
                for channel in config[day][user][db_target]:
                    if channel_obs:
                        if int(channel) not in channel_ids:
                            continue
                    try:
                        msg_count[user] += config[day][user][db_target][channel]
                    except KeyError:
                        msg_count[user] = config[day][user][db_target][channel]
        try:
            if db_target == 'channels':
                title = "Messages Leaderboard"
            else:
                title = "Activity Score Leaderboard"
            await utils.safe_send(ctx,
                                  embed=self.make_leaderboard_embed(ctx, channel_obs,
                                                                    msg_count, title))
        except discord.Forbidden:
            try:
                await utils.safe_send(ctx,
                                      "I lack the permissions to send embeds in this channel")
            except discord.Forbidden:
                pass

    @commands.command()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def lb(self, ctx, *channels):
        """Shows a leaderboard of the top 25 most active users this month"""
        if channels:
            await self.make_lb(ctx, channels)
        else:
            await self.make_lb(ctx, False)

    @commands.command()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def alb(self, ctx, *channels):
        """Shows a leaderboard of the users with the top 25 highest activity scores"""
        if channels:
            await self.make_lb(ctx, channels, "activity")
        else:
            await self.make_lb(ctx, False, "activity")

    @commands.command()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def chlb(self, ctx, *channels):
        await self.make_lb(ctx, channels)

    @commands.command()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def achlb(self, ctx, *channels):
        await self.make_lb(ctx, channels, "activity")

    @commands.command(aliases=['vclb', 'vlb', 'voicechat'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def vc(self, ctx):
        """Prints a leaderboard of who has the most time in voice"""
        try:
            config = self.bot.stats[str(ctx.guild.id)]['voice']['total_time']
        except KeyError:
            return
        lb_dict = {}
        for day in config:
            for user in config[day]:
                if user in lb_dict:
                    lb_dict[user] += config[day][user]
                else:
                    lb_dict[user] = config[day][user]
        await utils.safe_send(ctx, embed=self.make_leaderboard_embed(ctx, [],
                                                                     lb_dict, "Voice Leaderboard"))
    
    @commands.command(aliases=['emojis', 'emoji'])
    @commands.bot_has_permissions(embed_links=True)
    @commands.cooldown(3, 5, commands.BucketType.user)
    async def emotes(self, ctx: commands.Context, args=None):
        """Shows top emojis usage of the server.
        `;emojis` - Displays the top 25
        `;emojis -a` - Shows usage stats on all emojis
        `;emojis -l` - Shows the least used emojis.
        `;emojis -s` - Same as `-a` but it scales the usage of emojis created in the last 30 days
        `;emojis -me` - Shows only your emoji stats"""
        if str(ctx.guild.id) not in self.bot.stats:
            return
        config = self.bot.stats[str(ctx.guild.id)]['messages']
        emoji_count_dict: dict[str, int] = {}  # {emoji_name[str] : count[int]}

        if args == '-me':
            me = True
        else:
            me = False

        for date in config:
            for user_id in config[date]:
                if me:
                    if int(user_id) != ctx.author.id:
                        continue
                if 'emoji' not in config[date][user_id]:
                    continue
                for emoji_name in config[date][user_id]['emoji']:
                    if emoji_name in emoji_count_dict:
                        emoji_count_dict[emoji_name] += config[date][user_id]['emoji'][emoji_name]
                    else:
                        emoji_count_dict[emoji_name] = config[date][user_id]['emoji'][emoji_name]

        emoji_dict: dict[str, discord.Emoji] = {e.name: e for e in ctx.guild.emojis}
        msg = 'Top Emojis:\n'

        if args == '-s':
            for emoji_name in emoji_count_dict:
                if emoji_name not in emoji_dict:
                    continue
                emoji_obj = emoji_dict[emoji_name]
                x = discord.utils.utcnow() - emoji_obj.created_at
                if x < timedelta(days=30):
                    emoji_count = int(emoji_count_dict[emoji_name] * 30 / (x.days + 1))
                    emoji_count_dict[emoji_name] = emoji_count
            args = '-a'
            msg = 'Scaled Emoji Counts (last 30 days, emojis created in the last 30 days have ' \
                  'numbers scaled to 30 days):\n'
        top_emojis = sorted(list(emoji_count_dict.items()),
                            key=lambda e: e[1], reverse=True)
        # top_emojis: sorted list of [ (name: count) ... ]

        saved_msgs = []

        if args == '-a':
            for emoji_name, count in top_emojis:
                count: int
                if emoji_name in emoji_dict:
                    emoji_obj = emoji_dict[emoji_name]
                    addition = f"{str(emoji_obj)}: {count}\n"
                    if len(msg + addition) < 2000:
                        msg += addition
                    else:
                        saved_msgs.append(msg)
                        msg = addition
            if saved_msgs:
                if saved_msgs[-1] != msg:
                    saved_msgs.append(msg)
                for msg in saved_msgs:
                    await utils.safe_send(ctx, msg)
            else:
                await utils.safe_send(ctx, msg)

        elif args == '-l':
            emb = utils.red_embed("Least Used Emojis (last 30 days)")

            zero_use_emoji_list = [
                e for e in ctx.guild.emojis if not e.animated and '_kana_' not in e.name]
            uses_to_emoji_list_dict = {}
            for emoji_name, count in top_emojis:
                try:
                    emoji_obj = emoji_dict[emoji_name]
                except KeyError:
                    continue
                if emoji_obj.animated or '_kana_' in emoji_obj.name:
                    continue

                if emoji_obj in zero_use_emoji_list:
                    # now a list of emojis with zero uses
                    zero_use_emoji_list.remove(emoji_obj)

                # {4: [emoji_obj, emoji_obj], 5: [...], ...}
                uses_to_emoji_list_dict.setdefault(count, []).append(emoji_obj)

            if zero_use_emoji_list:
                uses_to_emoji_list_dict[0] = zero_use_emoji_list

            total_emojis = 0
            field_counter = 0
            while field_counter <= len(uses_to_emoji_list_dict) and (field_counter < 6 or total_emojis < 50):
                if field_counter in uses_to_emoji_list_dict:
                    if field_counter == 1:
                        field_name = f"{field_counter} use"
                    else:
                        field_name = f"{field_counter} uses"
                    field_value = ''
                    for emoji_obj in uses_to_emoji_list_dict[field_counter]:
                        if emoji_obj.animated:
                            continue
                        new_addition = f"{str(emoji_obj)} "
                        if len(field_value + new_addition) < 1024:
                            field_value += new_addition
                        else:
                            emb.add_field(name=field_name,
                                          value=field_value, inline=True)

                            if field_counter == 1:
                                field_name = f"{field_counter} use (cont.)"
                            else:
                                field_name = f"{field_counter} uses (cont.)"

                            field_value = new_addition
                        total_emojis += 1

                    if 'cont' in field_name:
                        emb.add_field(name=field_name,
                                      value=field_value, inline=True)
                    else:
                        emb.add_field(name=field_name,
                                      value=field_value, inline=False)

                field_counter += 1

            await utils.safe_send(ctx, embed=emb)

        else:
            emb = utils.green_embed("Most Used Emojis (last 30 days)")
            field_counter = 0
            for emoji_name, count in top_emojis:
                if field_counter < 25:
                    if emoji_name in emoji_dict:
                        emoji_obj = emoji_dict[emoji_name]
                        emb.add_field(
                            name=f"{field_counter + 1}) {str(emoji_obj)}", value=count)
                        field_counter += 1
                else:
                    break
            await utils.safe_send(ctx, embed=emb)

    @commands.group(invoke_without_command=True)
    @hf.is_admin()
    async def stats(self, ctx):
        """Enable/disable keeping of statistics for users (`;u`)"""
        guild = str(ctx.guild.id)
        if guild in self.bot.stats:
            self.bot.stats[guild]['enable'] = not self.bot.stats[guild]['enable']
        else:
            self.bot.stats[guild] = {'enable': True,
                                     'messages': {},
                                     'hidden': [],
                                     'voice':
                                         {'in_voice': {},
                                          'total_time': {}}
                                     }
        await utils.safe_send(ctx, f"Logging of stats is now set to {self.bot.stats[guild]['enable']}.")

    @stats.command()
    @hf.is_admin()
    async def hide(self, ctx, flag=None):
        """Hides the current channel from being shown in user stat pages.  Type `;stats hide view/list` to view a
        list of the current channels being hidden."""
        try:
            config = self.bot.stats[str(ctx.guild.id)]['hidden']
        except KeyError:
            return

        # hide/unhide current channel
        if not flag:
            channel_id: str = str(ctx.channel.id)
            if channel_id in config:
                config.remove(channel_id)
                await utils.safe_send(ctx,
                                      f"Removed {ctx.channel.mention} from the list of hidden channels.  It will now "
                                      f"be shown when someone calls their stats page.")
            else:
                config.append(channel_id)
                await utils.safe_send(ctx, f"Hid {ctx.channel.mention}.  "
                                      f"When someone calls their stats page, it will not be shown.")

        # view list of channels
        elif flag in ['list', 'view'] and config:
            msg = 'List of channels currently hidden:\n'
            c_id: str
            for c_id in config:
                channel: discord.TextChannel = self.bot.get_channel(int(c_id))
                if not channel:
                    config.remove(c_id)
                    continue
                msg += f"{channel.mention} ({channel.id})\n"
            await utils.safe_send(ctx, msg)

        # hide a specified channel
        else:
            if re.findall(r"^<#\d{17,22}>$", flag):
                flag = flag[2:-1]
            channel = self.bot.get_channel(int(flag))
            if channel:
                if str(channel.id) in config:
                    config.remove(str(channel.id))
                    await utils.safe_send(ctx,
                                          f"Removed {channel.mention} from the list of hidden channels. It will now "
                                          f"be shown when someone calls their stats page.")
                else:
                    config.append(str(channel.id))
                    await utils.safe_send(ctx,
                                          f"Hid {channel.mention}. When someone calls their stats page, "
                                          f"it will not be shown.")

    @commands.command()
    async def sentiment(self, ctx: commands.Context, user_id: str = None):
        """Check your sentiment score in the server.

        For info about sentiment scores, see \
        [this page](https://medium.com/@piocalderon/vader-sentiment-analysis-explained-f1c4f9101cd9).

        For a tool to test your own messages, try [this](https://monkeylearn.com/sentiment-analysis-online/)."""
        if ctx.message.content.startswith(";sentiment "):
            if not re.search(r";sentiment @|;sentiment <?@?!?\d{17,22}>?", ctx.message.content):
                return  # in on_message, there is separate code handling this case
                # this is so users can test their sentiment on their messages

        if not user_id:
            user_id = str(ctx.author.id)
            user = ctx.author
        else:
            user = await utils.member_converter(ctx, user_id)
            if not user:
                user = await utils.user_converter(ctx, user_id)
            if user:
                user_id = str(user.id)
            else:
                await utils.safe_reply(ctx.message, "I could not find the user you tried to specify.")
                return

        if str(ctx.guild.id) in self.bot.db.get('sentiments', []):
            user_sentiment = self.bot.db['sentiments'][str(
                ctx.guild.id)].get(user_id, [])
            len_user_sentiment = len(user_sentiment)
            if user_sentiment:
                user_sentiment = round(
                    sum(user_sentiment) * 1000 / len_user_sentiment, 2)
        else:
            return

        if not user_sentiment:
            await utils.safe_send(ctx, "For some reason I couldn't find a sentiment rating for that user.")
        else:
            if len_user_sentiment == 1000:
                reply_text = f"{str(user)}'s current sentiment rating (last 1000 messages) " \
                    f"is **{user_sentiment}**." \
                    f"\n([What is a 'sentiment rating'?]" \
                    f"(https://medium.com/@piocalderon/vader-sentiment-analysis-explained-f1c4f9101cd9))"
            else:
                reply_text = f"{str(user)}'s current sentiment rating ({len_user_sentiment} scaled up " \
                    f"to 1000 messages) is **{user_sentiment}**." \
                    f"\n([What is a 'sentiment rating'?]" \
                    f"(https://medium.com/@piocalderon/vader-sentiment-analysis-explained-f1c4f9101cd9))"
            emb = utils.green_embed(reply_text)
            footer_msg = ["Check the leaderboard with ;slb", "Sentiment is only recorded for English messages",
                          "Users with at least 1000 English messages calculated with sentiment will appear in the "
                          "leaderboard"]
            emb.set_footer(text=random.choice(footer_msg))
            await utils.safe_reply(ctx.message, embed=emb)

    @commands.command(aliases=['slb'])
    async def sentiment_leaderboard(self, ctx, negative=None):
        """Returns a leaderboard of the most positive users in the
         server among those that have at least 1000 messages."""
        # give admins ability to pull most *negative* users
        reverse = True
        if negative in ['negative', 'neg', 'least', '-l']:
            if hf.admin_check(ctx):
                reverse = False

        user_sentiments = []
        sentiments_dict = self.bot.db['sentiments'][str(ctx.guild.id)]
        for user_id in sentiments_dict:
            user_sentiment = sentiments_dict[user_id]
            if len(user_sentiment) == 1000:
                member = await utils.member_converter(ctx, user_id)
                if not member:
                    continue
                user_sentiments.append((member, round(sum(user_sentiment), 2)))

        user_sentiments.sort(key=lambda x: x[1], reverse=reverse)

        if reverse:
            des = "Users with highest sentiment rating (most positive users)"
        else:
            des = "Users with lowest sentiment rating (most negative users)"

        emb = utils.green_embed(des)
        pos = 1
        found_author = False
        for member_tuple in user_sentiments:
            if member_tuple[0] == ctx.author:
                found_author = True
            if pos <= 25:
                emb.add_field(
                    name=f"{pos}) {str(member_tuple[0])}", value=member_tuple[1])
            else:
                if found_author:
                    emb.set_field_at(
                        24, name=f"{pos}) {str(member_tuple[0])}", value=member_tuple[1])
                    break
            pos += 1

        await utils.safe_reply(ctx.message, embed=emb)

    @commands.command(aliases=['ac'])
    async def activity(self, ctx, user_in: str = None):
        if not user_in:
            user = ctx.author
        else:
            user = await utils.member_converter(ctx, user_in)
            if not user:
                user = await utils.user_converter(ctx, user_in)
                if not user:
                    await utils.safe_reply(ctx, "I couldn't find a user corresponding to the one you searched for.")
                    return

        assert user is not None, "Code failed to find user and advanced wrongly to this stage"

        _fig, ax = plt.subplots()

        msgs_per_day: dict[datetime, int] = hf.get_messages_per_day(
            user.id, ctx.guild)
        if not msgs_per_day:
            await utils.safe_reply(ctx, "The user you specified has no activity in the last month.")
            return

        day_objects = sorted(list(msgs_per_day.keys()))
        day_strings = [datetime.strftime(i, "%b %d") for i in msgs_per_day]
        day_numbers = list(msgs_per_day.values())

        ax.barh(day_strings, day_numbers)
        ax.invert_yaxis()  # labels read top-to-bottom
        ax.set_xlabel('Messages per day (red days are weekends)')
        start_year = day_objects[0].year
        end_year = day_objects[-1].year
        title_line_1 = f'Messages per day from {start_year}-{day_strings[0]} to {end_year}-{day_strings[-1]}'
        title_line_2 = f"{str(user)} - Average per day: {round(sum(day_numbers) / len(day_numbers), 1)}"
        ax.set_title(f"{title_line_1}\n{title_line_2}")

        # set colors for y-tick marks based on day of the week
        color_settings = []
        for i, day in enumerate(day_objects):
            if day.weekday() > 4:  # saturday or sunday
                color_settings.append((i, 'red'))
            else:
                color_settings.append((i, 'blue'))

        for i, color in color_settings:
            plt.setp(ax.get_yticklabels()[i], color=color)

        with io.BytesIO() as plotIm:
            plt.savefig(plotIm, format='png')
            plotIm.seek(0)
            await utils.safe_send(ctx, file=discord.File(plotIm, 'plot.png'))

    async def process_message_pool(self, message_pool: list[discord.Message]):
        async with asqlite.connect(rf'{dir_path}/database.db') as c:
            async with c.transaction():
                res_guilds = await c.execute("SELECT guild_id, rai_id FROM guilds")
                res_channels = await c.execute("SELECT channel_id, rai_id FROM channels")
                res_users = await c.execute("SELECT user_id, rai_id FROM users")

                guilds: list[Union[tuple, sqlite3.Row]] = await res_guilds.fetchall()
                channels: list[Union[tuple, sqlite3.Row]] = await res_channels.fetchall()
                users: list[Union[tuple, sqlite3.Row]] = await res_users.fetchall()

        existing_guilds = {g_id[0] for g_id in guilds}
        existing_channels = {c_id[0] for c_id in channels}
        existing_users = {u_id[0] for u_id in users}

        new_guild_ids = {
            msg.guild.id for msg in message_pool if msg.guild.id not in existing_guilds}
        new_channel_ids = {
            msg.channel.id for msg in message_pool if msg.channel.id not in existing_channels}
        new_user_ids = {
            msg.author.id for msg in message_pool if msg.author.id not in existing_users}

        guild_dict = {g_id[0]: g_id[1] for g_id in guilds}  # Create only once
        channel_dict = {c_id[0]: c_id[1] for c_id in channels}
        user_dict = {u_id[0]: u_id[1] for u_id in users}

        async with asqlite.connect(rf'{dir_path}/database.db') as c:
            async with c.transaction():
                # Batch insert new guilds
                if new_guild_ids:
                    await c.executemany("INSERT INTO guilds (guild_id) VALUES (?)",
                                        [(guild_id,) for guild_id in new_guild_ids])
                    # Update guild_dict with new Rai IDs to use below when inserting messages
                    placeholders = ", ".join("?" for _ in new_guild_ids)
                    query = f"SELECT guild_id, rai_id FROM guilds WHERE guild_id IN ({placeholders})"
                    res = await c.execute(query, tuple(new_guild_ids))
                    guild_dict.update({row[0]: row[1] for row in await res.fetchall()})

                if new_channel_ids:
                    await c.executemany("INSERT INTO channels (channel_id) VALUES (?)",
                                        [(channel_id,) for channel_id in new_channel_ids])
                    placeholders = ", ".join("?" for _ in new_channel_ids)
                    query = f"SELECT channel_id, rai_id FROM channels WHERE channel_id IN ({placeholders})"
                    res = await c.execute(query, tuple(new_channel_ids))
                    channel_dict.update({row[0]: row[1] for row in await res.fetchall()})

                if new_user_ids:
                    await c.executemany("INSERT INTO users (user_id) VALUES (?)",
                                        [(user_id,) for user_id in new_user_ids])
                    placeholders = ", ".join("?" for _ in new_user_ids)
                    query = f"SELECT user_id, rai_id FROM users WHERE user_id IN ({placeholders})"
                    res = await c.execute(query, tuple(new_user_ids))
                    user_dict.update({row[0]: row[1] for row in await res.fetchall()})

                param_list = [
                    (msg.id, user_dict[msg.author.id], guild_dict[msg.guild.id],
                     channel_dict[msg.channel.id], 'en')
                    for msg in message_pool]
                query = "INSERT INTO messages (message_id, user_id, guild_id, channel_id, language) " \
                    "VALUES (?, ?, ?, ?, ?)"
                await c.executemany(query, param_list)

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot:
            return

        async def pool_messages():
            if not msg.guild:
                return
            if not self.bot.stats.get(str(msg.guild.id), {'enable': False})['enable']:
                return
            self.bot.message_pool.append(msg)
            # print('\n', msg.author, msg.content, f"Message pool length: {len(self.bot.message_pool)}")
            # print(len(self.bot.message_pool), end=",")
            sys.stdout.flush()
            if len(self.bot.message_pool) == 100:
                # print('\n', msg.author, msg.content, f"Sending message pool")
                old_message_pool = self.bot.message_pool
                self.bot.message_pool = []
                await self.process_message_pool(old_message_pool)

        await pool_messages()

    @commands.command(aliases=['agelb'])
    async def age_leaderboard(self, ctx: commands.Context, less_than: int = 500):
        """Make a leaderbord of the oldest users in the server that have at least five messages in the last month"""
        activity_list: list[tuple[discord.Member, int]
                            ] = hf.get_top_server_members(ctx.guild, True)
        oldest_users = []
        for member, activity in activity_list:
            if activity < less_than:
                continue
            if str(member.id) in self.bot.db['joindates']:
                actual_joined_timestamp = self.bot.db['joindates'][str(
                    member.id)]
                member.joined_at = datetime.fromtimestamp(
                    actual_joined_timestamp, tz=timezone.utc)
            oldest_users.append((member, member.joined_at))
        oldest_users.sort(key=lambda x: x[1], reverse=False)
        emb = utils.green_embed("")
        emb.title = f"Oldest users in server with more than {less_than} messages in last month"
        pos = 1
        found_self = False
        for user_tuple in oldest_users:
            if user_tuple[0] == ctx.author:
                found_self = True
            if pos < 25:
                emb.add_field(name=f"{pos}) {str(user_tuple[0].display_name)}",
                              value=discord.utils.format_dt(user_tuple[1], style='d'))
            elif pos == 25:
                try:
                    self_joined_pos = oldest_users.index(
                        (ctx.author, ctx.author.joined_at)) + 1
                except ValueError:
                    self_joined_pos = None
                if not found_self and self_joined_pos:
                    emb.add_field(name=f"{self_joined_pos}) {str(ctx.author.display_name)}",
                                  value=discord.utils.format_dt(ctx.author.joined_at, style='d'))
                else:
                    emb.add_field(name=f"{pos}) {str(user_tuple[0].display_name)}",
                                  value=discord.utils.format_dt(user_tuple[1], style='d'))
            else:
                break
            pos += 1
        emb.set_footer(text="Ask Ryan if you need to reset your join date | Input a number after the command to "
                            "change the minimum message count")
        await utils.safe_send(ctx, embed=emb)


async def setup(bot):
    await bot.add_cog(Stats(bot))
