import asyncio
import cProfile
import csv
import importlib
import io
import logging
import os
import pstats
import re
import sys
import time
import unittest
from collections import deque, defaultdict

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional, List, Union, Tuple, Iterable, Callable
from unittest.mock import Mock
from urllib.parse import urlparse

import discord
import numpy as np
from discord import app_commands
from discord.ext import commands
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from cogs.interactions import Interactions

from cogs.utils.BotUtils import bot_utils as utils

dir_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

# here = sys.modules[__name__]
# here.bot = None
# here.loop = None

class Here:
    def __init__(self):
        from Rai import Rai
        self.bot: Optional[Rai] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

here = Here()

BANS_CHANNEL_ID = 329576845949534208
SP_SERV_ID = 243838819743432704
CH_SERV_ID = 266695661670367232
JP_SERVER_ID = 189571157446492161
REAL_RAI_ID = 270366726737231884
FEDE_GUILD = discord.Object(941155953682821201)
RY_SERV = discord.Object(275146036178059265)

SP_SERV_GUILD = discord.Object(SP_SERV_ID)
JP_SERV_GUILD = discord.Object(JP_SERVER_ID)


def setup(bot, loop: asyncio.AbstractEventLoop):
    """This command is run in the setup_hook function in Rai.py"""
    global here
    if here.bot is None:
        here.bot = bot
    else:
        pass

    if here.loop is None:
        here.loop = loop
    else:
        pass

    # # currently commented out because there are no tests to run
    # test_module = importlib.import_module("cogs.utils.tests.test_helper_functions")
    # test_module = importlib.reload(test_module)
    # suite = unittest.TestLoader().loadTestsFromModule(test_module)
    # test_runner = unittest.TextTestRunner(verbosity=1)
    # # Verbosity:
    # # 0 (quiet): you just get the total numbers of tests executed and the global result
    # # 1 (default): you get the same plus a dot for every successful test or a F for every failure
    # # 2 (verbose): you get the help string of every test and the result
    # test_runner.run(suite)


_lock = asyncio.Lock()


def count_messages(member_id: int, guild: discord.Guild) -> int:
    """Returns an integer of number of messages sent in the last month"""
    msgs = 0
    try:
        config = here.bot.stats[str(guild.id)]['messages']
        for day in config:
            if str(member_id) in config[day]:
                user = config[day][str(member_id)]
                if 'channels' not in user:
                    continue
                msgs += sum([user['channels'][c] for c in user['channels']])
        return msgs
    except (KeyError, AttributeError):
        return 0


def get_top_stats_list(stats_type: str,
                       guild: discord.Guild,
                       return_numbers=False) -> Union[list[tuple[discord.Member, int]], list[discord.Member]]:
    """Returns a sorted list of the most active members of the guild.
    Only returns members currently in the server. If a member has left the server, they will
    not be returned in this list.
    
    If return_numbers = True, it will return a list of [(member, number_of_messages), ...]
    If false, it will be just a list of members, [member, member, ...]"""
    try:
        config = here.bot.stats[str(guild.id)]['messages']
    except (KeyError, AttributeError):
        return []

    member_activity = defaultdict(int)
    for day in config:
        for member_id in config[day]:
            user = config[day][member_id]
            if stats_type == 'messages':
                if 'channels' not in user:
                    continue
                member_activity[int(member_id)] += sum([user['channels'][c] for c in user['channels']])
            elif stats_type == 'activity':
                if 'activity' not in user:
                    continue
                member_activity[int(member_id)] += sum([user['activity'][c] for c in user['activity']])

    sorted_members = sorted(member_activity.items(), key=lambda x: x[1], reverse=True)
    top_members = []
    for member_id, activity in sorted_members:
        member = guild.get_member(member_id)
        if member:
            if return_numbers:
                top_members.append((member, activity))
            else:
                top_members.append(member)
    return top_members


def get_top_server_members(
        guild: discord.Guild,
        return_numbers: bool = False
) -> list[discord.Member] | list[tuple[discord.Member, int]]:
    return get_top_stats_list('messages', guild, return_numbers)


def get_top_server_members_activity(guild: discord.Guild, return_numbers: bool = False) -> Union[list[tuple[discord.Member, int]], list[discord.Member]]:
    return get_top_stats_list('activity', guild, return_numbers)


def get_messages_per_day(member_id: int, guild: discord.Guild) -> dict[datetime, int]:
    days: dict[datetime, int] = {}
    first_day: Optional[datetime] = None
    last_day: Optional[datetime] = None
    if not hasattr(here.bot, 'stats'):
        return {}
    try:
        config = here.bot.stats[str(guild.id)]['messages']
        for day_str in config:  # day looks like yyyymmdd: 20230401
            day_str: str
            date: datetime = datetime.strptime(day_str, "%Y%m%d")
            if not first_day:
                first_day = date
            last_day = date
            days[date] = 0
            if str(member_id) in config[day_str]:
                user = config[day_str][str(member_id)]
                if 'channels' not in user:
                    continue
                days[date] += sum([user['channels'][c] for c in user['channels']])
    except (KeyError, AttributeError):
        return {}

    if len(days) == 0:
        return {}

    if len(days) == 1:
        the_single_day: datetime = list(days.keys())[0]
        twentynine_days_before: datetime = the_single_day - timedelta(days=29)
        first_day: datetime = twentynine_days_before
        days[twentynine_days_before] = 0

    assert first_day != last_day, f"The first {first_day} and last day {last_day} in this code should never be equal"
    assert last_day > first_day, f"The last day {last_day} here should always be greater than the first day {first_day}"
    assert first_day + timedelta(days=32) > last_day, f"There are more than 32 days separating first " \
                                                      f"{first_day} and last {last_day} day"
    one_day = timedelta(days=1)
    for day in days.copy():
        day: datetime
        next_day: datetime = day + one_day
        infinite_loop_avoidance_counter = 0
        while next_day not in days and next_day <= last_day:
            days[next_day] = 0
            next_day = next_day + one_day
            infinite_loop_avoidance_counter += 1
            if infinite_loop_avoidance_counter > 50:
                raise ValueError("This code has somehow entered an infinite loop")

    # noinspection PyTypeChecker
    # below operation for some reason thinks it returns list[datetime], but it's like [(datetime, int), (datetime, int)]
    days_list: list[tuple[datetime, int]] = list(days.items())
    days_list = sorted(days_list, key=lambda i: i[0])
    days = dict(days_list)
    return days


def get_stats_per_channel(member_id: int, guild: discord.Guild, desired_stat: str = '') -> dict[int: int]:
    """Queries bot stats database and arranges relevant data for a user per channel in a guild

    Pass "messages", "emoji", or "lang" into "desired_stat" to get a specific stat.
    Else, returns (total_msgs_month, total_msgs_week, message_count, emoji_count, lang_count)"""
    try:
        config = here.bot.stats[str(guild.id)]['messages']
    except (KeyError, AttributeError):
        return {}

    # ### Collect all the data from the database ###
    emoji_dict = {emoji.name: emoji for emoji in guild.emojis}
    message_count = {}
    emoji_count = {}
    lang_count = {}
    total_msgs_month = 0
    total_msgs_week = 0
    for day in config:
        if str(member_id) in config[day]:
            user = config[day][str(member_id)]

            if 'channels' not in user:
                continue
            for channel in user['channels']:
                channel: str
                guild_channel = guild.get_channel_or_thread(int(channel))
                if guild_channel:
                    message_count[channel] = message_count.get(channel, 0) + user['channels'][channel]
                else:
                    # for channels that don't exist anymore, assign them all to a "0" channel to be grouped later
                    message_count['0'] = message_count.get('0', 0) + user['channels'][channel]

                days_ago = (discord.utils.utcnow() -
                            datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)).days
                if days_ago <= 7:
                    total_msgs_week += user['channels'][channel]
                total_msgs_month += user['channels'][channel]

            if 'emoji' in user:
                for emoji in user['emoji']:
                    if emoji in emoji_dict:
                        name = emoji_dict[emoji]
                    else:
                        name = emoji
                    emoji_count[name] = emoji_count.get(name, 0) + user['emoji'][emoji]

            if 'lang' in user:
                for lang in user['lang']:
                    lang_count[lang] = lang_count.get(lang, 0) + user['lang'][lang]

    if desired_stat.startswith('message'):
        return total_msgs_month, total_msgs_week, message_count
    elif desired_stat.startswith('emoji'):
        return emoji_count
    elif desired_stat.startswith('lang'):
        return lang_count
    else:
        return total_msgs_month, total_msgs_week, message_count, emoji_count, lang_count


def count_activity(member_id: int, guild: discord.Guild) -> int:
    """Returns an integer value for activity in a server in the last month"""
    activity_score = 0
    try:
        config = here.bot.stats[str(guild.id)]['messages']
        for day in config:
            if str(member_id) in config[day]:
                user = config[day][str(member_id)]
                if 'activity' not in user:
                    continue
                activity_score += sum([user['activity'][c] for c in user['activity']])
        return activity_score
    except (KeyError, AttributeError):
        return 0


def calculate_voice_time(member_id: int, guild_id: Union[int, discord.Guild]) -> int:
    """Returns number of seconds a user has been in voice"""
    if isinstance(guild_id, discord.Guild):
        guild_id: int = guild_id.id
    assert isinstance(guild_id, int)
    try:
        voice_config: dict = here.bot.stats[str(guild_id)]['voice']['total_time']
    except (KeyError, AttributeError):
        return 0
    voice_time_minutes: int = 0
    for day in voice_config:
        if str(member_id) in voice_config[day]:
            day_voice_time = voice_config[day][str(member_id)]
            voice_time_minutes += day_voice_time
    voice_time_seconds = voice_time_minutes * 60
    return voice_time_seconds


def format_interval(interval: Union[timedelta, int, float], show_minutes=True,
                    show_seconds=False, include_spaces=True) -> str:
    """
    Display a time interval in a format like "10d 2h 5m"
    :param include_spaces: whether to include spaces between the components
    :param interval: time interval as a timedelta or as seconds
    :param show_minutes: whether to add the minutes to the string
    :param show_seconds: whether to add the seconds to the string
    :return: a string of the time interval, or "no more time" if there was nothing to display
    """
    if isinstance(interval, (int, float)):
        interval = timedelta(seconds=interval)

    total_seconds = int(interval.total_seconds())
    sign = ''
    if total_seconds < 0:
        sign = '-'
        total_seconds = -total_seconds

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    components = []
    if days:
        components.append(f"{days}d")
    if hours:
        components.append(f"{hours}h")
    if minutes and show_minutes:
        components.append(f"{minutes}m")
    if seconds and show_seconds:
        components.append(f"{seconds}s")

    space = " " if include_spaces else ""
    if components:
        return space.join(f"{sign}{component}" for component in components)
    else:
        if show_seconds:
            unit = 's'
        elif show_minutes:
            unit = 'm'
        else:
            unit = 'h'
        return f"0{unit}"


def add_to_modlog(ctx: Optional[commands.Context],
                  user: Union[discord.Member, List[Union[discord.Member, discord.User, discord.Guild, None]]],
                  modlog_type: str,
                  reason: str,
                  silent: bool,
                  length: Union[str, timedelta] = None,  # length str is something like "24h", "3d 2h", etc
                  datetime_in: datetime = None):
    """
    - ctx: a context object, or can be 'None'
    if ctx is None, then user should be a list of [member, guild]
    else, user is a discord.Member or discord.User object.
    - user: a discord.Member or discord.User object, or a list of [member, guild] if ctx is None
    user can also be a user ID (int)
    - reason: the reason for the modlog entry
    - silent: whether the event was silent (didn't ping the user)
    - length: for temporary mutes and bans, the length of the mute or ban.
    - date: if specified, will set the date that the modlog entry was created
    """
    if ctx:
        if ctx.message:
            jump_url = ctx.message.jump_url
        else:
            jump_url = None
        config = here.bot.db['modlog'].setdefault(str(ctx.guild.id), {'channel': None})
    else:  # "user" is actually a list of [member, guild] here, forgive me for how shitty that is lol
        guild = user[1]
        user = user[0]
        jump_url = None  # this would be the case for entries that come from the logger module
        if str(guild.id) in here.bot.db['modlog']:
            config = here.bot.db['modlog'][str(guild.id)]

        else:
            return  # this should only happen from on_member_ban events from logger module

    if isinstance(user, int):
        # passed an ID instead of user/member object
        user_id: int = user
    else:
        user_id = user.id

    if isinstance(length, timedelta):
        length = format_interval(length, show_seconds=False, show_minutes=True)
        
    if not datetime_in:
        date = discord.utils.utcnow().strftime("%Y/%m/%d %H:%M UTC")
    else:
        date = datetime_in.strftime("%Y/%m/%d %H:%M UTC")

    config.setdefault(str(user_id), []).append({'type': modlog_type,
                                                'reason': reason,
                                                'date': date,
                                                'silent': silent,
                                                'length': length,
                                                'jump_url': jump_url})
    return config


def parse_time(
        time_in: str,
        return_seconds: bool = False
    ) -> tuple[str, tuple[int, ...] | tuple[None, ...]]:
    """
    Parses a time string and returns a formatted UTC datetime string plus a time length.
    
    Allowed time units:
        - Seconds (s)
        - Minutes (m)
        - Hours (h)
        - Days (d)
        - Weeks (w)
        - Years (y)

    :param time_in: a string like "2d3h", "10h", "1y2d", "1y", "10s", etc.
    :return:
      - *time_string*: Formatted UTC datetime string ("%Y/%m/%d %H:%M UTC")
      - *length*: tuple (days, hours, minutes) if parsed successfully, or (None, None, None) if failed.
    """
    time_re = re.fullmatch(r''
                           r'((\d+)y)?'
                           r'((\d+)w)?'
                           r'((\d+)d)?'
                           r'((\d+)h)?'
                           r'((\d+)m)?'
                           r'((\d+)s)?', time_in)
    if not time_re:
        if return_seconds:
            return '', (None, None, None, None)
        else:
            return '', (None, None, None)
    
    years = int(time_re.group(2) or 0)
    weeks = int(time_re.group(4) or 0)
    days = int(time_re.group(6) or 0)
    hours = int(time_re.group(8) or 0)
    minutes = int(time_re.group(10) or 0)
    seconds = int(time_re.group(12) or 0)
    
    # move years and weeks into days
    total_days = (years * 365) + (weeks * 7) + days
    
    # keep hours the same
    total_hours = hours
    
    # move seconds into minutes
    if return_seconds:
        total_minutes = minutes
        total_seconds = seconds
    else:
        total_minutes = int(minutes + seconds / 86400)
        total_seconds = None
    
    if total_days > 1_000_000:
        # to avoid C integer overflow at 1,000,000 days
        length: tuple[int, int, int] = (999_999, 0, 0)
    else:
        length = (total_days, total_hours, total_minutes)
        
    finish_time = discord.utils.utcnow() + timedelta(days=length[0], hours=length[1], minutes=length[2])
    if return_seconds:
        length += (total_seconds,)
        finish_time += timedelta(seconds=length[3])
    time_string = finish_time.strftime("%Y/%m/%d %H:%M UTC")
    
    return time_string, length


def submod_check(ctx: commands.Context):
    if not ctx.guild:
        return
    if admin_check(ctx):
        return True

    submod_roles = []
    try:
        for r_id in here.bot.db['submod_role'][str(ctx.guild.id)]['id']:
            submod_roles.append(ctx.guild.get_role(r_id))
    except KeyError:
        return

    for role in submod_roles:
        if role in ctx.author.roles:
            return True


def is_submod():
    async def pred(ctx):
        return submod_check(ctx)

    return commands.check(pred)


def helper_check(ctx):
    if not ctx.guild:
        return
    if admin_check(ctx):
        return True
    if submod_check(ctx):
        return True
    try:
        role_id = here.bot.db['helper_role'][str(ctx.guild.id)]['id']
    except KeyError:
        return
    helper_role = ctx.guild.get_role(role_id)
    return helper_role in ctx.author.roles


def is_helper():
    async def pred(ctx):
        return helper_check(ctx)

    return commands.check(pred)


def voicemod_check(ctx):
    if submod_check(ctx) or ctx.author.id in [650044067194863647]:  # hardcoded mods
        return True
    try:
        return ctx.author.id in here.bot.db['voicemod'][str(ctx.guild.id)]
    except KeyError:
        pass


def is_voicemod():
    async def pred(ctx):
        return voicemod_check(ctx)

    return commands.check(pred)


def admin_check(ctx):
    if isinstance(ctx, commands.Context):
        author = ctx.author  # Comes from a normal command
    elif isinstance(ctx, discord.Interaction):
        author = ctx.user  # This function was called from inside a slash command
    else:
        return

    if not ctx.guild:
        return

    # allow retired mods on Spanish server to use Rai commands
    if ctx.guild.id == SP_SERV_ID:
        retired_mod_role = ctx.guild.get_role(1014256322436415580)
        if retired_mod_role in ctx.author.roles:
            return True

    try:
        ID = here.bot.db['mod_role'][str(ctx.guild.id)]['id']
        if isinstance(ID, list):
            for i in ID:
                mod_role = ctx.guild.get_role(i)
                if mod_role in author.roles or ctx.channel.permissions_for(author).administrator:
                    return True
        else:
            mod_role = ctx.guild.get_role(ID)
            return mod_role in author.roles or ctx.channel.permissions_for(author).administrator
    except (KeyError, TypeError):
        return ctx.channel.permissions_for(author).administrator


def is_admin():
    async def pred(ctx):
        return admin_check(ctx)

    return commands.check(pred)


def database_toggle(guild: discord.Guild, module_dict: dict):
    """Enable or disable a module"""
    try:
        config = module_dict[str(guild.id)]
        config['enable'] = not config['enable']
    except KeyError:
        config = module_dict[str(guild.id)] = {'enable': True}
    return config


async def ban_check_servers(bot, bans_channel, member, ping=False, embed=None):
    in_servers_msg = f"__I have found the user {str(member)} ({member.id}) in the following guilds:__"
    guilds: list[tuple[discord.Guild, int, str]] = []
    if member in bans_channel.guild.members:
        ping = False
    for guild in bot.guilds:  # type: discord.Guild
        if guild.id in bot.db['ignored_servers']:
            continue
        if member in guild.members:
            messages: int = count_messages(member, guild)
            day = ''
            if messages:
                try:
                    config = bot.stats[str(guild.id)]['messages']
                    for day in reversed(list(config)):  # type: str
                        if str(member.id) in config[day]:
                            break
                except KeyError:
                    pass
            guilds.append((guild, messages, day))

    for guild_entry in guilds:  # discord.Guild, number_of_messages: int, last_message_day: str
        in_servers_msg += f"\n**{guild_entry[0].name}**"
        if guild_entry[1]:
            date = f"{guild_entry[2][0:4]}/{guild_entry[2][4:6]}/{guild_entry[2][6:]}"
            in_servers_msg += f" (Messages: {guild_entry[1]}, Last message: {date})"

        pings = ''
        if ping:
            if str(guild_entry[0].id) in bot.db['bansub']['guild_to_role']:
                role_id = bot.db['bansub']['guild_to_role'][str(guild_entry[0].id)]
                for user in bot.db['bansub']['user_to_role']:
                    if role_id in bot.db['bansub']['user_to_role'][user]:
                        pings += f" <@{user}> "

            # Try to send the notification of a newly banned user directly to mod channels with pings
            sent_to_mod_channel = False
            mod_channel_id = bot.db['mod_channel'].get(str(guild_entry[0].id), 0)
            mod_channel = bot.get_channel(mod_channel_id)
            if mod_channel:
                try:
                    if embed:
                        msg = await utils.safe_send(mod_channel,
                                              f"{member.mention}\n"
                                              f"@here {pings} The below user has been banned on another server "
                                              f"and is in your server.",
                                              embed=embed)
                    else:
                        msg = await utils.safe_send(mod_channel, f"@here {pings} The below user has been banned on another "
                                                           f"server and is currently in your server.")
                    sent_to_mod_channel = True
                    ctx = await bot.get_context(msg)
                    await ctx.invoke(bot.get_command("modlog"), member.id)
                except (discord.HTTPException, discord.Forbidden):
                    pass
            if not sent_to_mod_channel:
                in_servers_msg += pings

    if guilds:
        await bans_channel.send(in_servers_msg)


async def long_deleted_msg_notification(msg):
    try:
        notification = 'Hardcore deleted a long message:'
        await msg.author.send(f"{notification}```{msg.content[:1962]}```")
    except discord.Forbidden:
        return


async def uhc_check(msg):
    try:
        if msg.guild.id == 189571157446492161 and len(msg.content) > 3:
            if here.bot.db['ultraHardcore'].setdefault('users', {}).get(str(msg.author.id), [False])[0]:
                lowercase_msg_content = msg.content.casefold().replace('what is your native language', '') \
                    .replace('welcome', '').replace("what's your native language", "")
                jpRole = msg.guild.get_role(196765998706196480)

                ratio = utils.jpenratio(lowercase_msg_content)
                # if I delete a long message

                if not lowercase_msg_content:
                    return

                # allow Kotoba bot commands
                if msg.content[0:2] in ['k!', 't!', '-h'] \
                        or msg.content[0] == ';':
                    # if people abuse this, they must use no spaces
                    if msg.content.count(' ') < 2 or msg.author.id == 202995638860906496:
                        return  # please don't abuse this

                # delete the messages
                if ratio or ratio == 0.0:
                    if isinstance(msg.channel, discord.Thread):
                        channel_id = msg.channel.parent.id
                    elif isinstance(msg.channel, (discord.TextChannel, discord.VoiceChannel)):
                        channel_id = msg.channel.id
                    else:
                        return
                    if channel_id not in here.bot.db['ultraHardcore']['ignore']:
                        msg_content = msg.content
                        if jpRole in msg.author.roles:
                            if ratio < .25:
                                try:
                                    await msg.delete()
                                except discord.NotFound:
                                    pass
                                if len(msg_content) > 30:
                                    await long_deleted_msg_notification(msg)
                        else:
                            if ratio > .75:
                                try:
                                    await msg.delete()
                                except discord.NotFound:
                                    pass
                                if len(msg_content) > 60:
                                    await long_deleted_msg_notification(msg)
    except AttributeError:
        pass
        

def _pre_load_language_detection_model():
    english = []
    spanish = []
    if not os.path.exists(f'{dir_path}/cogs/utils/principiante.csv'):
        logging.error("Language detection model not loaded, missing csv files")
        return  # Ask Ryry013 for the language files needed to make this work
    for csv_name in ['principiante.csv', 'avanzado.csv', 'beginner.csv', 'advanced.csv']:
        with open(f"{dir_path}/cogs/utils/{csv_name}", newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile, delimiter=' ', quotechar='|')
            if csv_name in ['principiante.csv', 'avanzado.csv']:
                for row in reader:
                    spanish.append(row[2])
            else:
                for row in reader:
                    english.append(row[2])

    def make_set(_english, _spanish, pipeline=None):
        if pipeline:
            eng_pred = pipeline.predict(_english)
            sp_pred = pipeline.predict(_spanish)
            new_english = []
            new_spanish = []
            for i in range(len(_english)):
                if eng_pred[i] == 'en':
                    new_english.append(_english[i])
            for i in range(len(_spanish)):
                if sp_pred[i] == 'sp':
                    new_spanish.append(_spanish[i])
            _spanish = new_spanish
            _english = new_english

        x = np.array(_english + _spanish)
        y = np.array(['en'] * len(_english) + ['sp'] * len(_spanish))

        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.05, random_state=42)
        cnt = CountVectorizer(analyzer='char', ngram_range=(2, 2))

        pipeline = Pipeline([
            ('vectorizer', cnt),
            ('model', MultinomialNB())
        ])

        pipeline.fit(x_train, y_train)
        # y_pred = pipeline.predict(x_test)

        return pipeline

    here.bot.langdetect = make_set(english, spanish, make_set(english, spanish, make_set(english, spanish)))


def detect_language(text) -> Optional[str]:
    probs = here.bot.langdetect.predict_proba([text])[0]
    if probs[0] > 0.9:
        return 'en'
    elif probs[0] < 0.1:
        return 'es'
    else:
        return None


async def load_language_detection_model():
    await here.loop.run_in_executor(None, _pre_load_language_detection_model)


@dataclass
class ModlogEntry:
    def __init__(self,
                 event: str,
                 user: Union[discord.User, discord.Member],
                 guild: discord.Guild,
                 ctx: commands.Context = None,
                 length: str = None,
                 reason: str = None,
                 silent: bool = False,
                 ):
        self.event = event
        self.user = user
        self.guild = guild
        self.ctx = ctx
        self.length = length  # the length of time after which a ban or mute will expire
        self.reason = reason
        self.silent = silent

    def add_to_modlog(self):
        jump_url: Optional[str] = None
        if self.ctx:  # someone called a Rai command like ;ban or ;mute
            if self.ctx.message:
                jump_url = self.ctx.message.jump_url

        if config := here.bot.db['modlog'].setdefault(str(self.guild.id), {'channel': None}):
            pass
        else:
            return  # this should only happen from on_member_ban events from logger module
            # don't log bans not with Rai from servers without modlog set up

        member_modlog = config.setdefault(str(self.user.id), [])
        member_modlog.append({'type': self.event,
                              'reason': self.reason,
                              'date': discord.utils.utcnow().strftime(
                                  "%Y/%m/%d %H:%M UTC"),
                              'silent': self.silent,
                              'length': self.length,
                              'jump_url': jump_url})
        return config


@dataclass
class Args:
    def __init__(self,
                 user_ids: list[int],
                 time_string: str,
                 length: list[int],
                 time_arg: str,
                 time_obj: datetime,
                 reason: str):
        self._user_ids = user_ids  # list of users
        self._time_string = time_string  # string formatted like %Y/%m/%d %H:%M UTC
        self._length = length  # list of [days, hours, minutes]
        self._time_arg = time_arg
        self._time_obj = time_obj
        self._reason = reason
        
    @property
    def user_ids(self) -> list[int]:
        """List of users IDs (integers)"""
        return self._user_ids
    
    @property
    def time_string(self) -> str:
        """String formatted like %Y/%m/%d %H:%M UTC"""
        return self._time_string
    
    @property
    def length(self) -> Optional[list[int]]:
        """List of [days, hours, minutes] as integers"""
        return self._length
    
    @property
    def time_arg(self) -> Optional[str]:
        """String passed in that was parsed, for example, '2h' or '3d2h'"""
        return self._time_arg
    
    @property
    def time_obj(self) -> Optional[datetime]:
        """Datetime object corresponding to ending point of action (a mute, for example)"""
        return self._time_obj
    
    @property
    def timedelta_obj(self) -> timedelta:
        """Timedelta object corresponding to length of action, or 0s timedelta if None"""
        if self._time_obj:
            return self._time_obj - discord.utils.utcnow()
        else:
            return timedelta(seconds=0)
    
    @property
    def reason(self) -> str:
        """The reason for the action"""
        return self._reason


def args_discriminator(args: str) -> Args:
    """
    Takes in a string of args and pulls out IDs and times then leaves the reason.
    :param args: A string containing all the args
    :return: Class object with list 'users', time, reason
    """
    # I could do *args which gives a list, but it creates errors when there are unmatched quotes in the command
    args_list = args.split()

    user_regex = re.compile(r'^<?@?!?(\d{17,22})>?$')  # group 1: ID
    _user_ids: List[int] = []  # list of user ids
    _time_arg: Optional[str] = None
    _time_obj: Optional[datetime] = None
    _length: Optional[list[int]] = None
    _time_string: Optional[str] = None

    # Iterate through beginning arguments taking all IDs and times until you reach the reason
    for arg in args_list.copy():
        if user_id_match := re.search(user_regex, arg):
            _user_ids.append(int(user_id_match.group(1)))
            args_list.remove(arg)
            if f"{arg} " in args:
                args = args.replace(f"{arg} ", "", 1)
            else:
                args = args.replace(arg, "", 1)
        elif (t := parse_time(arg))[0]:
            _time_string = t[0]
            _length = t[1]
            _time_arg = arg
            args_list.remove(arg)
            if f"{arg} " in args:
                args = args.replace(f"{arg} ", "", 1)
            else:
                args = args.replace(arg, "", 1)
        else:
            break  # Assuming all user_ids and times are before the reason
    _reason = args

    if _length:
        try:
            _time_obj = discord.utils.utcnow() + timedelta(days=_length[0], hours=_length[1], minutes=_length[2])
        except OverflowError:
            _time_arg = _time_obj = _length = _time_string = None

    return Args(_user_ids, _time_string, _length, _time_arg, _time_obj, _reason)

@app_commands.context_menu(name="Delete and log")
@app_commands.guilds(SP_SERV_GUILD, JP_SERV_GUILD)
@app_commands.default_permissions(manage_messages=True)
async def delete_and_log(interaction: discord.Interaction, message: discord.Message):
    await Interactions.delete_and_log(interaction, message)


@app_commands.context_menu(name="Mute user (1h)")
@app_commands.guilds(SP_SERV_GUILD, JP_SERV_GUILD)
@app_commands.default_permissions()
async def context_message_mute(interaction: discord.Interaction, message: discord.Message):
    await Interactions.context_message_mute(interaction, message)


@app_commands.context_menu(name="Mute user (1h)")
@app_commands.guilds(SP_SERV_GUILD, JP_SERV_GUILD)
@app_commands.default_permissions()
async def context_member_mute(interaction: discord.Interaction, member: discord.Member):
    await Interactions.context_member_mute(interaction, member)


@app_commands.context_menu(name="Ban user")
@app_commands.guilds(SP_SERV_GUILD, JP_SERV_GUILD)
@app_commands.default_permissions()
async def ban_and_clear_message(interaction: discord.Interaction,
                                message: discord.Message):  # message commands return the message
    await Interactions.ban_and_clear_main(interaction, message)


@app_commands.context_menu(name="Ban user")
@app_commands.guilds(SP_SERV_GUILD, JP_SERV_GUILD)
@app_commands.default_permissions()
async def ban_and_clear_member(interaction: discord.Interaction,
                               member: discord.User):  # message commands return the message
    await Interactions.ban_and_clear_main(interaction, member)


@app_commands.context_menu(name="View modlog")
@app_commands.guilds(SP_SERV_GUILD, JP_SERV_GUILD)
@app_commands.default_permissions()
async def context_view_modlog(interaction: discord.Interaction, member: discord.Member):
    modlog = here.bot.get_command("modlog")
    ctx = await commands.Context.from_interaction(interaction)
    embed = await ctx.invoke(modlog, str(member.id), post_embed=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.context_menu(name="View user stats")
@app_commands.guilds(SP_SERV_GUILD, JP_SERV_GUILD)
@app_commands.default_permissions()
async def context_view_user_stats(interaction: discord.Interaction, member: discord.Member):
    # async def user(self, ctx, *, member_in: str = None, post_embed=True):
    user = here.bot.get_command("user")
    ctx = await commands.Context.from_interaction(interaction)
    embed = await ctx.invoke(user, member_in=str(member.id), post_embed=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.context_menu(name="Get ID from message")
@app_commands.guilds(SP_SERV_GUILD, JP_SERV_GUILD)
@app_commands.default_permissions()
async def get_id_from_message(interaction: discord.Interaction, message: discord.Message):
    ids = re.findall(r"\d{17,22}", message.content)
    if ids:
        await interaction.response.send_message(ids[-1], ephemeral=True)
        await interaction.followup.send(f"<@{ids[-1]}>", ephemeral=True)
    else:
        await interaction.response.send_message("No IDs found in the message", ephemeral=True)


@app_commands.context_menu(name="Log a message")
@app_commands.guilds(SP_SERV_GUILD)
@app_commands.default_permissions()
async def log_message_context(interaction: discord.Interaction, message: discord.Message):
    await Interactions.log_message(interaction, message)


async def hf_sync(remove=False):
    # only sync context menu commands for real Rai bot (not forks)
    if here.bot.user.id == REAL_RAI_ID:
        commands_in_file = [delete_and_log, context_message_mute, context_member_mute,
                            context_view_modlog, context_view_user_stats, get_id_from_message,
                            ban_and_clear_member, ban_and_clear_message, log_message_context]
    else:
        commands_in_file = []
        pass
        
    # add option to forcibly remove commands. this is really here for demonstration / ;eval use
    if remove:
        here.bot.tree.clear_commands(guild=SP_SERV_GUILD)
        here.bot.tree.clear_commands(guild=JP_SERV_GUILD)
    
    # Add any commands from this file not currently registered in the tree (new/renamed commands)
    for command in commands_in_file:
        # if command.name not in command_names_in_tree:
        here.bot.tree.add_command(command, guild=SP_SERV_GUILD, override=True)
        here.bot.tree.add_command(command, guild=JP_SERV_GUILD, override=True)

    # Try to sync
    try:
        await here.bot.tree.sync(guild=SP_SERV_GUILD)
    except discord.Forbidden:
        print("Failed to sync commands to SP_SERV_GUILD")

    # Jp server
    try:
        await here.bot.tree.sync(guild=JP_SERV_GUILD)
    except discord.Forbidden:
        print("Failed to sync commands to JP_SERV_GUILD")

    # Ry serv
    for command in []:
        if command not in here.bot.tree.get_commands(guild=RY_SERV):
            here.bot.tree.add_command(command, guild=RY_SERV, override=True)

    try:
        await here.bot.tree.sync(guild=RY_SERV)
    except discord.Forbidden:
        print("Failed to sync commands to RY_SERV")

    # ch serv
    try:
        await here.bot.tree.sync(guild=discord.Object(CH_SERV_ID))
    except discord.Forbidden:
        print("Failed to sync commands to Chinese server")


def message_list_to_text(msgs: list[discord.Message], text: str = "") -> str:
    for msg in msgs:
        date = msg.created_at.strftime("%d/%m/%y %H:%M:%S")
        author = f"{str(msg.author)} ({msg.author.id})"
        if msg.content:
            text += f"({date}) - {author} || {msg.content}\n"
        for embed in msg.embeds:
            embed_cont = ""
            if embed.title:
                embed_cont += f"{embed.title} - "
            if embed.description:
                embed_cont += f"{embed.description} - "
            if embed.url:
                embed_cont += f"{embed.url} - "
            if embed_cont:
                embed_cont = embed_cont[:-3]
            text += f"({date}) - Deleted embed from {author} || {embed_cont}\n"
        for att in msg.attachments:
            text += f"({date}) - Deleted attachment from {author} || {att.filename}: {att.proxy_url}\n"

    return text


def text_to_file(text: str, filename) -> discord.File:
    with io.StringIO() as write_file:
        write_file.write(text)
        write_file.seek(0)
        filename = filename
        # noinspection PyTypeChecker
        file = discord.File(write_file, filename=filename)

    return file


async def send_attachments_to_thread_on_message(log_message: discord.Message, attachments_message: discord.Message):
    """This command creates a thread on a log message and uploads all the attachments from an "attachment_message"
    to a thread on the log message"""
    files = []
    embed_urls = []
    if attachments_message.attachments:
        for attachment in attachments_message.attachments:
            try:
                if isinstance(attachment, Mock):
                    file = await mock_to_file(attachment.proxy_url or attachment.url, spoiler=True)
                else:
                    file = await attachment.to_file(filename=attachment.filename,
                                                    description=attachment.description,
                                                    use_cached=True,
                                                    spoiler=True)
            except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                if isinstance(attachment, Mock):
                    file = await mock_to_file(attachment.url, spoiler=True)
                else:
                    try:
                        file = await attachment.to_file(filename=attachment.filename,
                                                        description=attachment.description,
                                                        spoiler=True, use_cached=False)
                    except (discord.HTTPException, discord.NotFound, discord.Forbidden):
                        file = None
            
            files.append((file, attachment))

    if attachments_message.embeds:
        for embed in attachments_message.embeds:
            if isinstance(embed, Mock):
                embed_urls.append(embed.url)
            else:
                # posting an image expands the image to an embed without title or desc., send those into the thread
                if embed.url and embed.thumbnail and not embed.title and not embed.description:
                    embed_urls.append(embed.url)
       
    found_anything = any([f[0] for f in files] + embed_urls)
    if files + embed_urls:
        if found_anything:
            # Either get the thread on a message or create a new thread
            if thread := log_message.guild.get_thread(log_message.id):
                pass
            else:
                try:
                    thread = await log_message.create_thread(name=f"msg_attachments_{attachments_message.id}")
                except (discord.Forbidden, discord.HTTPException):
                    await log_message.reply("I was unable to create a thread to upload attachments to.")
                    return
        else:
            log_message_embed = log_message.embeds[0]
            if "Was unable to download the" not in log_message_embed.description:
                log_message_embed.description = "Was unable to download the files attached to the message:\n"
            for embed_url in embed_urls:
                log_message_embed.description += f"- {embed_url}\n"
            for attachment in attachments_message.attachments:
                log_message_embed.description += f"- {attachment.filename}\n"
            await log_message.edit(embed=log_message_embed)
            return
    else:
        return  # no files or embed urls were found
    
    
    for file_tuple in files:
        # file_tuple is tuple (file, attachment)
        file = file_tuple[0]
        attachment = file_tuple[1]
        if file:
            try:
                await utils.safe_send(thread, file=file)
            except (discord.Forbidden, discord.HTTPException) as e:
                try:
                    await utils.safe_send(thread, f"Error attempting to send {attachment.filename} "
                                                  f"({attachment.proxy_url}): {e}")
                except (discord.Forbidden, discord.HTTPException):
                    pass
        else:
            file_info = f"Failed to download file: {attachment.filename} - {attachment.description}\n" \
                        f"{attachment.proxy_url}"
            try:
                await utils.safe_send(thread, file_info)
            except (discord.Forbidden, discord.HTTPException):
                pass
        
    for embed_url in embed_urls:
        try:
            await utils.safe_send(thread, embed_url)
        except (discord.Forbidden, discord.HTTPException) as e:
            try:
                await utils.safe_send(thread, f"Error attempting to send attached link to message: {e}")
            except (discord.Forbidden, discord.HTTPException):
                pass
            
    # archive after uploading all attachments
    await thread.edit(archived=True)


def convert_to_datetime(input_str: str) -> Optional[datetime]:
    try:
        return datetime.strptime(input_str, "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return


async def get_message_from_id_or_link(interaction: discord.Interaction,
                                      message_id: str,
                                      message_link: str) -> Optional[discord.Message]:
    if message_link:  # get message ID in order to get URL
        try:
            message_id = message_link.split("/")[-1]
        except IndexError:
            await interaction.response.send_message("The message link format you gave is invalid. Please try "
                                                    "again. An example valid message link is "
                                                    "https://discord.com/channels/243838819743432704/"
                                                    "742449924519755878/1012253103271186442.", ephemeral=True)
            return

    if message_id:  # get URL of image
        try:
            message_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("The message ID format you gave is invalid. Please try again. "
                                                    "An example valid message ID is 1012253103271186442.",
                                                    ephemeral=True)
            return

        try:
            message: discord.Message = await interaction.channel.fetch_message(int(message_id))
        except discord.NotFound:
            await interaction.response.send_message("I could not find the message ID you specified *in this "
                                                    "channel*. Please check the ID of the message.",
                                                    ephemeral=True)
            return

        return message


class RaiMessage(discord.Message):
    # noinspection PyMissingConstructor
    def __init__(self, discord_message: discord.Message):
        # Wrap the original discord.Message
        self.discord_message = discord_message

        # Add custom attributes
        self._lock = asyncio.Lock()  # Lock for thread safety
        self._ctx: Optional[commands.Context] = None  # None if not fetched
        self._error_fetching_ctx = False
        self.detected_lang: Optional[str] = None  # en, sp, None
        self.hardcore: Optional[bool] = None

    def __getattr__(self, name):
        """
        Delegate attribute access to the wrapped discord_message.

        This is only called when the attribute is not found in RaiMessage.
        For example:
        - "msg.detected_lang" returns this class's attribute.
        - "msg.author" returns "self.discord_message.author".
        """
        return getattr(self.discord_message, name)

    @property
    def ctx(self):
        """
        Non-async property to access the context. Throws an error if _ctx is not initialized.
        """
        if self._error_fetching_ctx:
            return None
        if self._ctx is None:
            raise ValueError("Context has not been initialized. Call `await get_ctx()` first.")
        return self._ctx

    async def get_ctx(self):
        """
        Asynchronously fetch and initialize the context if it hasn't been initialized yet.
        """
        if self._ctx is None and not self._error_fetching_ctx:
            async with self._lock:
                if self._ctx is None:  # Double-check inside the lock
                    try:
                        self._ctx = await here.bot.get_context(self.discord_message)
                    except Exception as e:
                        self._ctx = None
                        self._error_fetching_ctx = True
                        raise


class MiniMessage:
    """
    A lightweight representation of a Discord message, designed to store minimal
    information for reduced memory usage. Useful for caching and analysis without
    retaining unnecessary objects.
    
    Attributes:
        message_id (int): The unique ID of the message.
        content (str): The content of the message.
        author_id (int): The ID of the author of the message.
        channel_id (int): The ID of the channel where the message was sent.
        guild_id (Optional[int]): The ID of the guild (server), if applicable.
        attachments (List[dict]): A list of attachment dictionaries containing only URLs.
        
    Properties:
        created_at: The creation timestamp of the message.
        id: The unique ID of the message.
        
        
    Methods:
        to_dict: Convert the MiniMessage to a dictionary for easy storage or JSON serialization.
        from_discord_message: Create a MiniMessage object from a discord.py Message object.
    """
    def __init__(
        self,
        message_id: int,
        content: str,
        author_id: int,
        channel_id: int,
        guild_id: Optional[int] = None,
        attachments: Optional[List[dict]] = None,
        embeds: Optional[List[dict]] = None
    ):
        """
        A minimal message object for reduced memory usage.

        Args:
            message_id (int): The unique ID of the message.
            content (str): The content of the message.
            author_id (int): The ID of the author of the message.
            channel_id (int): The ID of the channel where the message was sent.
            guild_id (Optional[int]): The ID of the guild (server), if applicable.
            attachments (Optional[List[dict]]): A list of attachment dictionaries containing only URLs.
        """
        self.message_id = int(message_id)
        self.content = content
        self.author_id = int(author_id)
        self.channel_id = int(channel_id)
        self.guild_id = int(guild_id) if guild_id else None
        if not self.guild_id:
            channel = here.bot.get_channel(self.channel_id)
            if channel:
                self.guild_id = getattr(channel.guild, "id", None)
        
        # Simplify attachments to just URLs and proxy URLs
        self.attachments = [
            {"url": attachment.get("url", ""), "proxy_url": attachment.get("proxy_url", "")}
            for attachment in (attachments or [])
        ]
        
        self.embeds = [
            {"url": embed.get("url", "")}
            for embed in (embeds or [])
        ]

    @property
    def created_at(self) -> datetime:
        """The creation timestamp of the message."""
        return discord.utils.snowflake_time(self.message_id)

    @property
    def id(self) -> int:
        """The unique ID of the message."""
        return self.message_id

    def to_dict(self):
        """Convert the MiniMessage to a dictionary for easy storage or JSON serialization."""
        return {
            "message_id": self.message_id,
            "content": self.content,
            "author_id": self.author_id,
            "channel_id": self.channel_id,
            "guild_id": self.guild_id,
            "attachments": self.attachments,
            "embeds": self.embeds,
        }

    def to_discord_message(self) -> discord.Message:
        """
        Convert the MiniMessage to a discord.py Message object.

        Returns:
            discord.Message: A discord.py message object (a mock, though)
        """
        # Mock the author (user)
        author = here.bot.get_user(self.author_id)
        if not author:
            author = Mock(spec=discord.User)
            author.id = self.author_id
            author.name = "Unknown User"  # Placeholder name
            author.bot = False
            
        guild = here.bot.get_guild(self.guild_id) if self.guild_id else None
        channel = None
        if not guild:
            guild = Mock(spec=discord.Guild)
            guild.id = self.guild_id
            guild.name = "Unknown Server"
        
        # Resolve channel
        if guild:
            channel = guild.get_channel_or_thread(self.channel_id)
            if not channel:
                channel = here.bot.get_channel(self.channel_id)
        if not channel:
            channel = Mock(spec=discord.TextChannel)
            channel.id = self.channel_id
            channel.name = "Unknown Channel"  # Placeholder name
            channel.guild = guild
        
        # Mock attachments
        # attachments = [MockAttachment(attachment["url"],
        #                               proxy_url=attachment.get("proxy_url", ""),
        #                               filename=attachment["url"].split("/")[-1])
        #                for attachment in self.attachments]
        # discord.Attachment.to_file()
        
        attachments = []
        for attachment in self.attachments:
            mock_attachment = Mock(spec=discord.Attachment)
            mock_attachment.url = attachment["url"]
            mock_attachment.proxy_url = attachment.get("proxy_url", "")
            mock_attachment.filename = urlparse(attachment["url"]).path.split("/")[-1] if attachment["url"] else ""
            attachments.append(mock_attachment)
            
        embeds = []
        for embed in self.embeds:
            mock_embed = Mock(spec=discord.Embed)
            mock_embed.url = embed["url"]
            embeds.append(mock_embed)
        
        # Mock the Message object
        message = Mock(spec=discord.Message)
        message.id = self.message_id
        message.channel = channel
        message.author = author
        message.content = self.content
        message.created_at = self.created_at
        message.attachments = attachments
        message.embeds = embeds
        message.guild = channel.guild if hasattr(channel, 'guild') else None
        message.mentions = []
        message.role_mentions = []
        message.channel_mentions = []
        message.reference = None
        message.reactions = []
        
        return message
        
        # author = here.bot.get_user(self.author_id)
        # if not author:
        #     author = discord.Object(id=self.author_id)
        # channel = here.bot.get_channel_or_thread(self.channel_id)
        # if not channel:
        #     channel = discord.Object(id=self.channel_id)
        # message = discord.PartialMessage(
        #     id=self.message_id,
        #     channel=channel
        # )
        # message.content = self.content

    @classmethod
    def from_discord_message(cls, message: discord.Message) -> "MiniMessage":
        """
        Create a MiniMessage object from a discord.py Message object.

        Args:
            message (discord.Message): A discord.py message object.

        Returns:
            MiniMessage: A simplified version of the message.
        """
        attachments = [
            {"url": attachment.url, "proxy_url": attachment.proxy_url}
            for attachment in message.attachments
        ]
        
        # posting an image expands the image to an embed without title or desc.
        embeds = [
            {"url": embed.url}
            for embed in message.embeds if embed.url and embed.thumbnail and not embed.title and not embed.description
        ]
        
        return cls(
            message_id=message.id,
            content=message.content,
            author_id=message.author.id,
            channel_id=message.channel.id,
            guild_id=message.guild.id if message.guild else None,
            attachments=attachments,
            embeds=embeds
        )
    
    @classmethod
    def from_mini_message(cls, message: "MiniMessage"):
        """Used to update a MiniMessage in an old list to a new structure when MiniMessage is updated."""
        return cls(
            message_id=message.message_id,
            content=message.content,
            author_id=message.author_id,
            channel_id=message.channel_id,
            guild_id=message.guild_id,
            attachments=message.attachments,
        )

    def __eq__(self, other):
        # noinspection PyUnresolvedReferences
        if not isinstance(other, (MiniMessage, RaiMessage, discord.mixins.EqualityComparable)):
            return False
        return self.message_id == other.id

    def __repr__(self):
        """A clean string representation for debugging."""
        if len(self.content) > 20:
            content = f"{self.content[:20]}..."
        else:
            content = self.content
        content = content.replace("\n", " ").replace("`", "")
        date_str = self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"<MiniMessage id={self.message_id}, author_id={self.author_id}, "
            f"channel_id={self.channel_id}, guild_id={self.guild_id}, "
            f"content='{content}', created_at={date_str}>"
        )
    
    def __sizeof__(self) -> int:
        """
        Calculate the memory usage of the MiniMessage object.
        :return: The memory usage in bytes.
        """
        return (
            sys.getsizeof(self.message_id)
            + sys.getsizeof(self.content)
            + sys.getsizeof(self.author_id)
            + sys.getsizeof(self.channel_id)
            + sys.getsizeof(self.guild_id)
            + sys.getsizeof(self.created_at)
            + sum(sys.getsizeof(attachment) for attachment in self.attachments)
            + sys.getsizeof(self.attachments)
        )
    
    def __dict__(self) -> dict:
        """Convert the MiniMessage to a dictionary for easy storage or JSON serialization."""
        return self.to_dict()


class MessageQueue(deque[MiniMessage]):
    """
    A queue of MiniMessage objects with a maximum length to prevent memory overflow.
    
    Properties:
        depth (str): The time difference between the oldest and newest messages.
        memory_usage (str): The memory usage of the queue.
        average_message_length (float): The average length of messages in the queue.
        
    Methods:
        add_message: Add a MiniMessage to the queue.
        get_recent_messages: Retrieve the most recent messages.
        to_dict_list: Convert all messages in the queue to a list of dictionaries.
        find_by_author: Find all messages by a specific author.
        change_length: Change the maximum length of the queue by creating a new queue and returning
        reload: Reload all messages in queue with updated MiniMessage objects (assuming MiniMessage has changed)
    """
    def __init__(self, iterable: Iterable = (), maxlen: Optional[int] = None):
        """
        Create a new MessageQueue object.
        
        :param iterable: Any iterable, for example, a list or deque, including potentially just another MessageQueue.
        :param maxlen: The maximum length of the queue.
        """
        # MessageQueue(message_queue)  # give message queue with same maxlen (this does nothing)
        # MessageQueue(message_queue, maxlen=1000)  # give message queue with new maxlen
        # MessageQueue(maxlen=1000)  # create new message queue with maxlen 1000
        # MessageQueue()  # create new message queue with default maxlen
        self._lock = asyncio.Lock()
        if maxlen == 0:
            raise ValueError("Parameter `maxlen` cannot be 0.")
        
        default_maxlen = 100000
        if isinstance(iterable, MessageQueue):
            maxlen = maxlen or iterable.maxlen
            super().__init__(iterable, maxlen=maxlen)
        else:
            maxlen = maxlen or default_maxlen
            if isinstance(iterable, list) and iterable:
                if isinstance(iterable[0], dict):
                    iterable = [MiniMessage(**msg) for msg in iterable]
                elif isinstance(iterable[0], MiniMessage):
                    pass  # passed a list of MiniMessages rather than a MessageQueue of MiniMessages
                else:
                    raise TypeError(f"Expected list of `MiniMessage` or `dict`, got {type(iterable[0]).__name__}")
            super().__init__(iterable, maxlen=maxlen)
        
    @property
    def depth(self) -> str:
        """Find time difference between oldest and newest message in the queue."""
        if len(self) < 2:
            return "0s"
        return format_interval(self[-1].created_at - self[0].created_at)
    
    @property
    def memory_usage(self) -> str:
        """Calculate the memory usage of the queue."""
        size = self.__sizeof__()
        out = ""
        if size < 1024:
            out += f"{size} B"
        elif size < 1024 ** 2:
            out += f"{size / 1024:.2f} KB"
        elif size < 1024 ** 3:
            out += f"{size / 1024 ** 2:.2f} MB"
        else:
            out += f"{size / 1024 ** 3:.2f} GB"
        
        size_per_msg = size / len(self) if len(self) else 0
        if size_per_msg < 1024:
            out += f" ({size_per_msg:.2f} B/msg, {self.average_message_length:.1f} char/msg)"
        elif size_per_msg < 1024 ** 2:
            out += f" ({size_per_msg / 1024:.2f} KB/msg, {self.average_message_length:.1f} char/msg)"
        elif size_per_msg < 1024 ** 3:
            out += f" ({size_per_msg / 1024 ** 2:.2f} MB/msg, {self.average_message_length:.1f} char/msg)"
        else:
            out += f" ({size_per_msg / 1024 ** 3:.2f} GB/msg, {self.average_message_length:.1f} char/msg)"
        
        return out
    
    @property
    def average_message_length(self) -> float:
        """Calculate the average message length of the queue."""
        return sum(len(msg.content) for msg in self) / len(self) if len(self) else 0

    def reload(self) -> None:
        """Reload all messages in queue with updated MiniMessage objects (assuming MiniMessage has changed)"""
        self.extend([MiniMessage.from_mini_message(msg) for msg in self])

    def add_message(self, message: Union[MiniMessage, discord.Message]) -> None:
        """Add a MiniMessage to the queue."""
        if isinstance(message, discord.Message):
            message = MiniMessage.from_discord_message(message)
        if not isinstance(message, MiniMessage):
            raise TypeError(f"Expected `MiniMessage` or `discord.Message`, got {type(message).__name__}")
        self.append(message)
        
    def get_recent_messages(self, count: int = 10) -> List[MiniMessage]:
        """Retrieve the most recent messages."""
        return list(self)[-count:]

    def to_dict_list(self) -> List[dict]:
        """Convert all messages in the queue to a list of dictionaries."""
        snapshot = list(self)
        return [message.to_dict() for message in snapshot]

    def find_by_author(self, author: Union[int, discord.User, discord.Member]) -> List[MiniMessage]:
        """Find all messages by a specific author."""
        if isinstance(author, (discord.User, discord.Member)):
            author_id = author.id
        elif isinstance(author, int):
            author_id = author
        else:
            raise TypeError(f"Expected `int`, `discord.User`, or `discord.Member`, got {type(author).__name__}")
        
        return [msg for msg in self if msg.author_id == author_id]
    
    def find_by_channel(self, channel: Union[int, discord.abc.Messageable]) -> List[MiniMessage]:
        """Find all messages in a specific channel."""
        if isinstance(channel, (discord.abc.Messageable, discord.abc.GuildChannel, discord.abc.PrivateChannel)):
            channel_id = channel.id
        elif isinstance(channel, int):
            channel_id = channel
        else:
            raise TypeError(f"Expected `int` or `discord.abc.Messageable`, got {type(channel).__name__}")
        return [msg for msg in self if msg.channel_id == channel_id]
    
    def find_by_guild(self, guild: Union[int, discord.Guild]) -> List[MiniMessage]:
        """Find all messages in a specific guild."""
        if isinstance(guild, discord.Guild):
            guild_id = guild.id
        elif isinstance(guild, int):
            guild_id = guild
        else:
            raise TypeError(f"Expected `int` or `discord.Guild`, got {type(guild).__name__}")
        return [msg for msg in self if msg.guild_id == guild_id]
    
    def find(self, *args, **kwargs) -> List[MiniMessage]:
        """Find all messages that match the given criteria. The criteria are passed as keyword arguments.
        
        Example:
            - find(author_id=1234567890, guild_id=1234567890): Find messages by a specific author in a specific guild.
            - find(author_id=1234567890, channel_id=1234567890): Find messages by a specific author in a specific channel.
            - find(message_id=1234567890): Find a message by its ID.
            - find(1234567890): Find a message by its ID.
            - find(discord.User): Find messages by a specific author.
            - find(discord.Guild, discord.User): Find messages by a specific author in a specific guild.
        """
        for arg in args:
            if isinstance(arg, (discord.User, discord.Member)):
                kwargs["author_id"] = arg.id
            elif isinstance(arg, discord.Guild):
                kwargs["guild_id"] = arg.id
            elif isinstance(arg, (discord.abc.Messageable, discord.abc.GuildChannel, discord.abc.PrivateChannel)):
                kwargs["channel_id"] = arg.id
            elif isinstance(arg, int):
                kwargs["message_id"] = arg
            elif potential_id := re.search(r"^\d{17,22}$", str(arg)):
                kwargs["message_id"] = int(potential_id.group())
            else:
                raise TypeError(f"Expected some kind of ID or discord object, got {type(arg).__name__}")
        return [msg for msg in self if all(getattr(msg, key) == value for key, value in kwargs.items())]
    
    def change_length(self, new_length: int) -> "MessageQueue":
        """Change the maximum length of the queue by creating a new queue and returning it."""
        with self._lock:
            if len(self) > new_length:
                sliced_queue = list(self)[-new_length:]
            else:
                sliced_queue = list(self)
            return MessageQueue(sliced_queue, maxlen=new_length)
    
    def __repr__(self) -> str:
        """Print a preview of the list"""
        return (
            f"<MessageQueue: "
            f"{len(self)} messages ー "
            f"{self.depth} depth ー "
            f"{self.memory_usage}>"
        )
    
    def __sizeof__(self) -> int:
        """Calculate the memory usage of the queue."""
        return sys.getsizeof(super()) + sum(sys.getsizeof(msg) for msg in self)
    
    def __dict__(self) -> list[dict]:
        """Convert the MessageQueue to a list of dictionaries."""
        with self._lock:
            return [msg.to_dict() for msg in self]
    
    @classmethod
    def from_dict(cls, data):
        """Create a MessageQueue object from a list of dictionaries."""
        return cls([MiniMessage(**msg_kwargs) for msg_kwargs in data])


async def excessive_dm_activity(guild_id: int, user_id: int) -> Optional[datetime]:
    """Pull from http data whether the user is currently flagged for 'excessive DMs'"""
    try:
        data = await here.bot.http.get_member(guild_id, user_id)
    except (discord.NotFound):
        return # User not found in the guild
    # noinspection PyTypedDict
    unusual_dm_activity_res = data.get('unusual_dm_activity_until')  # certainly exists, just not defined in TypedDict yet
    if unusual_dm_activity_res:
        flag_until: Optional[datetime] = discord.utils.parse_time(unusual_dm_activity_res)  # timestamp in ISO 8601 format
        return flag_until
    

async def suspected_spam_activity_flag(guild_id: int, user_id: int) -> bool:
    """Need to check 'public_flags' attr of bot.http.get_member()['user'], returns an integer which can be put into
    discord.Flags.PublicUserFlags._from_value(<int>), this is the "suspected spam activity" flag.
    Can also do `fetch_user()` --> `user.public_flags.spammer`."""
    try:
        data = await here.bot.http.get_member(guild_id, user_id)
    except discord.NotFound:
        return False  # User not found in the guild
    user_public_flags_int = data.get('user').get('public_flags')
    
    if user_public_flags_int:
        # noinspection PyProtectedMember
        flags: discord.PublicUserFlags = discord.flags.PublicUserFlags._from_value(user_public_flags_int)
        return flags.spammer
    

async def mock_to_file(to_use_url, spoiler: bool = False) -> Optional[discord.File]:
    """Mock the to_file method of discord.Attachment to download the file through the URL and return a discord.File."""
    if not to_use_url:
        raise ValueError(f"Attachment URL ({to_use_url}) not found.")

    # Download the file using my async utils.aiohttp_get_text()
    data = await utils.aiohttp_get(to_use_url)

    if not data:
        return

    # Create a discord.File object
    filename = urlparse(to_use_url).path.split("/")[-1]
    # TypeError: a bytes-like object is required, not 'ClientResponse'
    return discord.File(io.BytesIO(data),
                        filename=filename,
                        spoiler=spoiler,
                        description="No description")


def profileit(sleep_time: float = 0.0):
    def decorator(func):
        if not hasattr(here.bot, 'profiling_decorators'):
            here.bot.profiling_decorators = set()
        here.bot.profiling_decorators.add(func.__module__)  # add cogs that have profiling decorators
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            prof = cProfile.Profile()
            prof.enable()
            try:
                retval = await func(*args, **kwargs)
            finally:
                prof.disable()
                s = io.StringIO()
                ps = pstats.Stats(prof, stream=s).sort_stats(pstats.SortKey.TIME)
                ps.print_stats()
                total_string = s.getvalue()
                total_string_split = total_string.split('\n')
                # looks like this, with "newlines" turning into "" in the split (adding extra list elements)
                #          11351 function calls in 1.001 seconds
                #    Ordered by: internal time
                #    ncalls  tottime  percall  cumtime  percall filename:lineno(function)
                #        12    0.513    0.043    0.513    0.043 {method 'poll' of 'select.epoll' objects}
                #         1    0.476    0.476    0.476    0.476 {method 'enable' of '_lsprof.Profiler' objects}
                #         1    0.004    0.004    0.008    0.008 /home/pi/Documents/bot-venv/lib/python3.11/site-...)
                #     10000    0.004    0.000    0.004    0.000 /home/pi/Documents/bot-venv/lib/python3.11/site-...)
                total_time = float(total_string_split[0].split()[-2])
                if total_time - sleep_time < 0.01:
                    return
                print('!\n!')
                print(f"Profiling {func.__name__}")
                print(total_string_split[0])
                print(total_string_split[1])
                print(total_string_split[2])
                print(total_string_split[3])
                print(total_string_split[4])
                for line in total_string_split[5:]:
                    if not line:
                        continue
                    tottime = float(line.split()[1])
                    if tottime > 0:
                        print(line)
            return retval
    
        return async_wrapper if asyncio.iscoroutinefunction(func) else func
    
    return decorator

def basic_timer(time_allowance: float = 0):
    def decorator(func):
        if not hasattr(here.bot, 'profiling_decorators'):
            here.bot.profiling_decorators = set()
        here.bot.profiling_decorators.add(func.__module__)  # add cogs that have profiling decorators
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            retval = await func(*args, **kwargs)
            end = time.perf_counter()
            print_timing(start, end)
            return retval
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            retval = func(*args, **kwargs)
            end = time.perf_counter()
            print_timing(start, end)
            return retval
        
        def print_timing(start, end):
            diff = end - start
            if diff > time_allowance:
                _module = getattr(func, '__module__', '<none>').replace('cogs.', '')
                print(f"{_module}.{func.__name__} took {diff:.3f}s (basic_timer)")
                
                if func.__name__ == 'on_message':
                    if not hasattr(here.bot, "event_times"):
                        here.bot.event_times = defaultdict(list)
                    if not hasattr(here.bot, "live_latency"):
                        here.bot.live_latency = here.bot.latency
                    latency = round(here.bot.live_latency, 4)  # time in seconds, for example, 0.08629303518682718
                    
                    here.bot.event_times[func.__name__].append((int(discord.utils.utcnow().timestamp()),
                                                               latency,
                                                               round(diff, 4)))
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper
    
    return decorator


async def wait_for(name: str, event: str, timeout: float, check: Optional[Callable[..., bool]]):
    """For "name", write the name of the event without "on_". For example, "voice_state_update" or "member_join"."""
    if not hasattr(here.bot, "wait_for_times"):
        here.bot.wait_for_times = defaultdict(list)
    t1 = time.perf_counter()
    try:
        return await here.bot.wait_for(event, timeout=timeout, check=check)
    finally:
        t2 = time.perf_counter()
        here.bot.wait_for_times[event].append(t2 - t1)
        
        
async def sleep(name, time_in: float, add: bool = False):
    if not hasattr(here.bot, "wait_for_times"):
        here.bot.wait_for_times = defaultdict(list)
    t1 = time.perf_counter()
    await asyncio.sleep(time_in)
    t2 = time.perf_counter()
    if add:
        here.bot.wait_for_times[name][-1] += t2 - t1
    else:
        here.bot.wait_for_times[name].append(t2 - t1)
        
        
def line_profile(t_in, description: str = "", t_threshold: float = 1, offset: float = 0):
    """
    Line profiler for measuring the time between two points in the code.
    :param t_in: Pass in a timestamp, and it'll return the new timestamp
    :param description:
    :param t_threshold: Print only if above this threshold
    :param offset: If there is some kind of sleep or wait in the code, subtract this time from diff
    :return: New timestamp
    """
    t_now = time.perf_counter()
    diff = t_now - t_in - offset
    if diff > t_threshold:
        print(f"{description + ': ' if description else ''} {diff:.3f}s (latency: {here.bot.live_latency:.4f}s)")
    return t_now


async def send_to_test_channel(*content):
    test_chan_id = os.getenv("BOT_TEST_CHANNEL") or 0
    channel = here.bot.get_channel(int(test_chan_id))
    if not channel:
        raise ValueError(f"Channel with ID {test_chan_id} not found.")
    await segment_send(channel, *content)


async def segment_send(channel: Union[int, discord.abc.Messageable], *content, max_messages: int = 5):
    content = ' '.join([str(i) for i in content])
    if isinstance(channel, int):
        channel = here.bot.get_channel(channel)
        if not channel:
            raise ValueError(f"Channel with ID {channel} not found.")
    elif not isinstance(channel, discord.abc.Messageable):
        raise TypeError(f"Expected `int` or `discord.abc.Messageable`, got {type(channel).__name__}")
    
    segments = utils.split_text_into_segments(content, 2000)
    
    try:
        for segment in segments[:max_messages]:
            await utils.safe_send(channel, segment)
        if len(segments) > max_messages:
            await utils.safe_send(channel, f"Message too long, only sent the first 5 segments")
    except discord.Forbidden as e:
        print(f"Error sending message: {e}")