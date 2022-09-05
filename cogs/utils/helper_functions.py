import asyncio
import csv
import io
import json
import os
import re
import shutil
import sys
import traceback
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Union, Tuple

import discord
import numpy as np
from discord import app_commands, ui
from discord.ext import commands
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from cogs.interactions import Interactions

dir_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

here = sys.modules[__name__]
here.bot: Optional[commands.Bot] = None
here._loop = None

BANS_CHANNEL_ID = 329576845949534208
SP_SERV_ID = 243838819743432704
SP_SERV_GUILD = discord.Object(SP_SERV_ID)
FEDE_GUILD = discord.Object(941155953682821201)
RY_SERV = discord.Object(275146036178059265)


def setup(bot, loop):
    """This command is run in the setup_hook function in Rai.py"""
    if here.bot is None:
        here.bot = bot
    else:
        pass

    if here._loop is None:
        here._loop = loop
    else:
        pass


# credit: https://gist.github.com/dperini/729294
_url = re.compile(
    r"""
            # protocol identifier
            (?:https?|ftp)://
            # user:pass authentication
            (?:\S+(?::\S*)?@)?
            (?:
              # IP address exclusion
              # private & local networks
              (?!(?:10|127)(?:\.\d{1,3}){3})
              (?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})
              (?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})
              # IP address dotted notation octets
              # excludes loopback network 0.0.0.0
              # excludes reserved space >= 224.0.0.0
              # excludes network & broacast addresses
              # (first & last IP address of each class)
              (?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])
              (?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}
              \.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4])
            |
              # host name
              (?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+
              # domain name
              (?:\.(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)*
              # TLD identifier
              \.[a-z\u00a1-\uffff]{2,}
              # TLD may end with dot
              \.?
            )
            # port number
            (?::\d{2,5})?
            # resource path
            (?:[/?#]\S*)?
        """, re.VERBOSE | re.I)

_emoji = re.compile(r'<a?(:[A-Za-z0-9_]+:|#|@|@&)!?[0-9]{17,20}>')

_lock = asyncio.Lock()


def count_messages(member, guild=None) -> int:
    """Returns an integer of number of messages sent in the last month"""
    msgs = 0
    if not guild:
        guild = member.guild
    try:
        config = here.bot.stats[str(guild.id)]['messages']
        for day in config:
            if str(member.id) in config[day]:
                user = config[day][str(member.id)]
                msgs += sum([user['channels'][c] for c in user['channels']])
        return msgs
    except KeyError:
        return 0


def calculate_voice_time(member_id: int, guild_id: Union[int, discord.Guild]) -> int:
    """Returns number of seconds a user has been in voice"""
    if isinstance(guild_id, discord.Guild):
        guild_id: int = guild_id.id
    assert isinstance(guild_id, int)
    voice_config: dict = here.bot.stats[str(guild_id)]['voice']['total_time']
    voice_time_minutes: int = 0
    for day in voice_config:
        if str(member_id) in voice_config[day]:
            time = voice_config[day][str(member_id)]
            voice_time_minutes += time
    voice_time_seconds = voice_time_minutes * 60
    return voice_time_seconds


def add_to_modlog(ctx, user, modlog_type, reason, silent, length=None):
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

    config.setdefault(str(user.id), []).append({'type': modlog_type,
                                                'reason': reason,
                                                'date': discord.utils.utcnow().strftime("%Y/%m/%d %H:%M UTC"),
                                                'silent': silent,
                                                'length': length,
                                                'jump_url': jump_url})
    return config


def green_embed(text):
    return discord.Embed(description=text, color=0x23ddf1)


def red_embed(text):
    return discord.Embed(description=text, color=0x9C1313)


def grey_embed(text):
    return discord.Embed(description=text, color=0x848A84)


async def safe_send(destination,
                    content: str = None, *,
                    embed: discord.Embed = None,
                    embeds: list[discord.Embed] = None,
                    delete_after: float = None,
                    file: discord.File = None,
                    view: discord.ui.View = None):
    """A command to be clearer about permission errors when sending messages"""
    if not content and not embed and not file:
        if type(destination) == str:
            raise SyntaxError("You maybe forgot to state a destination in the safe_send() function")
        elif issubclass(destination, discord.abc.Messageable):
            raise SyntaxError("The content you tried to send in the safe_send() function was None")
        else:
            raise SyntaxError("There was an error parsing the arguments of the safe_send() function")

    perms_set = perms = False
    if isinstance(destination, commands.Context):
        if destination.guild:
            perms = destination.channel.permissions_for(destination.guild.me)
            perms_set = True
    elif isinstance(destination, discord.TextChannel):
        perms = destination.permissions_for(destination.guild.me)
        perms_set = True
    if not destination:
        return

    if perms_set:
        if embed and not perms.embed_links and perms.send_messages:
            await destination.send("I lack permission to upload embeds here.")
            return

    try:
        if isinstance(destination, discord.User):
            if not destination.dm_channel:
                await destination.create_dm()
        return await destination.send(content,
                                      embed=embed,
                                      embeds=embeds,
                                      delete_after=delete_after,
                                      file=file,
                                      view=view)
    except discord.Forbidden:
        if isinstance(destination, commands.Context):
            ctx = destination  # shorter and more accurate name
            msg_content = f"Rai tried to send a message to #{ctx.channel.name} but lacked permissions to do so " \
                          f"(either messages or embeds)."

            try:
                await safe_send(ctx.author, msg_content)
            except (discord.Forbidden, discord.HTTPException):
                pass

        raise


def parse_time(time: str) -> Tuple[str, list[int]]:
    """
    Parses time from a string and returns a datetime formatted string plus a number of days and hours
    :param time: a string like "2d3h" or "10h"
    :return: *time_string*: A string for the database corresponding to a datetime formatted with "%Y/%m/%d %H:%M UTC"/
    *length*: a list with ints [days, hours, minutes]
    """
    time_re = re.search(r'^((\d+)y)?((\d+)d)?((\d+)h)?((\d+)m)?$',
                        time)  # group 2, 4, 6, 8: years, days, hours, minutes
    if time_re:
        if years := time_re.group(2):
            years: int = int(years)
        else:
            years = 0

        if days := time_re.group(4):
            days: int = years * 365 + int(days)
        else:
            days = years * 365

        if hours := time_re.group(6):
            hours: int = int(hours)
        else:
            hours = 0

        if minutes := time_re.group(8):
            minutes: int = int(minutes)
        else:
            minutes = 0

        length: List[int] = [days, hours, minutes]

    else:
        return '', []
    finish_time = discord.utils.utcnow() + timedelta(days=length[0], hours=length[1], minutes=length[2])
    time_string: str = finish_time.strftime("%Y/%m/%d %H:%M UTC")
    return time_string, length


async def member_converter(ctx, user_in) -> Optional[discord.Member]:
    # check for an ID
    user_id = re.findall(r"(^<@!?\d{17,22}>$|^\d{17,22}$)", str(user_in))
    if user_id:
        user_id = user_id[0].replace('<@', '').replace('>', '').replace('!', '')
        member = ctx.guild.get_member(int(user_id))
        return member

    # check for an exact name
    member = ctx.guild.get_member_named(user_in)
    if member:
        return member

    # try the beginning of the name
    member_list = [(member.name.casefold(), member.nick.casefold() if member.nick else '', member)
                   for member in ctx.guild.members]
    user_in = user_in.casefold()
    for member in member_list:
        if member[0].startswith(user_in):
            return member[2]
        if member[1].startswith(user_in):
            return member[2]

    # is it anywhere in the name
    for member in member_list:
        if user_in in member[0]:
            return member[2]
        if user_in in member[1]:
            return member[2]

    if ctx.author != ctx.bot.user:
        await ctx.send('Member not found in the server')
    return None


def _predump_json():
    db_copy = deepcopy(here.bot.db)
    stats_copy = deepcopy(here.bot.stats)
    if not os.path.exists(f'{dir_path}/db_2.json'):
        # if backup files don't exist yet, create them
        shutil.copy(f'{dir_path}/db.json', f'{dir_path}/db_2.json')
        shutil.copy(f'{dir_path}/db_2.json', f'{dir_path}/db_3.json')
        shutil.copy(f'{dir_path}/db_3.json', f'{dir_path}/db_4.json')
        shutil.copy(f'{dir_path}/stats.json', f'{dir_path}/stats_2.json')
        shutil.copy(f'{dir_path}/stats_2.json', f'{dir_path}/stats_3.json')
        shutil.copy(f'{dir_path}/stats_3.json', f'{dir_path}/stats_4.json')
    else:
        # make incremental backups of db.json
        shutil.copy(f'{dir_path}/db_3.json', f'{dir_path}/db_4.json')
        shutil.copy(f'{dir_path}/db_2.json', f'{dir_path}/db_3.json')
        shutil.copy(f'{dir_path}/db.json', f'{dir_path}/db_2.json')

        # make incremental backups of stats.json
        shutil.copy(f'{dir_path}/stats_3.json', f'{dir_path}/stats_4.json')
        shutil.copy(f'{dir_path}/stats_2.json', f'{dir_path}/stats_3.json')
        shutil.copy(f'{dir_path}/stats.json', f'{dir_path}/stats_2.json')

    with open(f'{dir_path}/db_temp.json', 'w') as write_file:
        json.dump(db_copy, write_file, indent=4)
    shutil.copy(f'{dir_path}/db_temp.json', f'{dir_path}/db.json')

    with open(f'{dir_path}/stats_temp.json', 'w') as write_file:
        json.dump(stats_copy, write_file, indent=1)
    shutil.copy(f'{dir_path}/stats_temp.json', f'{dir_path}/stats.json')


async def dump_json():
    async with _lock:
        try:
            await here._loop.run_in_executor(None, _predump_json)
        except RuntimeError:
            print("Restarting dump_json on a RuntimeError")
            await here._loop.run_in_executor(None, _predump_json)


def submod_check(ctx):
    if not ctx.guild:
        return
    if admin_check(ctx):
        return True
    try:
        role_id = here.bot.db['submod_role'][str(ctx.guild.id)]['id']
    except KeyError:
        return
    submod_role = ctx.guild.get_role(role_id)
    return submod_role in ctx.author.roles


def is_submod():
    async def pred(ctx):
        return submod_check(ctx)

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

    try:
        ID = here.bot.db['mod_role'][str(ctx.guild.id)]['id']
        mod_role = ctx.guild.get_role(ID)
        return mod_role in author.roles or ctx.channel.permissions_for(author).administrator
    except (KeyError, TypeError):
        return ctx.channel.permissions_for(author).administrator


def is_admin():
    async def pred(ctx):
        return admin_check(ctx)

    return commands.check(pred)


def database_toggle(ctx, module_name):
    try:
        config = module_name[str(ctx.guild.id)]
        config['enable'] = not config['enable']
    except KeyError:
        config = module_name[str(ctx.guild.id)] = {'enable': True}
    return config


def rem_emoji_url(msg):
    if isinstance(msg, discord.Message):
        msg = msg.content
    new_msg = _emoji.sub('', _url.sub('', msg))
    for char in msg:
        if is_emoji(char):
            new_msg = new_msg.replace(char, '').replace('  ', '')
    return new_msg


async def ban_check_servers(bot, bans_channel, member, ping=False, embed=None):
    in_servers_msg = f"__I have found the user {str(member)} ({member.id}) in the following guilds:__"
    guilds: list[list[discord.Guild, int, str]] = []  # type:
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
            guilds.append([guild, messages, day])

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
                        msg = await safe_send(mod_channel,
                                              f"{member.mention}\n"
                                              f"@here {pings} The below user has been banned on another server "
                                              f"and is in your server.",
                                              embed=embed)
                    else:
                        msg = await safe_send(mod_channel, f"@here {pings} The below user has been banned on another "
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


def jpenratio(msg_content):
    text = _emoji.sub('', _url.sub('', msg_content))
    en, jp, total = get_character_spread(text)
    return en / total if total else None


def get_character_spread(text):
    english = 0
    japanese = 0
    for ch in text:
        if is_cjk(ch):
            japanese += 1
        elif is_english(ch):
            english += 1
    return english, japanese, english + japanese


def generous_is_emoji(char):
    EMOJI_MAPPING = (
        (0x0080, 0x02AF),
        (0x0300, 0x03FF),
        (0x0600, 0x06FF),
        (0x0C00, 0x0C7F),
        (0x1DC0, 0x1DFF),
        (0x1E00, 0x1EFF),
        (0x2000, 0x209F),
        (0x20D0, 0x214F),
        (0x2190, 0x23FF),
        (0x2460, 0x25FF),
        (0x2600, 0x27EF),
        (0x2900, 0x2935),
        (0x2B00, 0x2BFF),
        (0x2C60, 0x2C7F),
        (0x2E00, 0x2E7F),
        (0x3000, 0x303F),
        (0xA490, 0xA4CF),
        (0xE000, 0xF8FF),
        (0xFE00, 0xFE0F),
        (0xFE30, 0xFE4F),
        (0x2757, 0x2757),
        (0x1F000, 0x1F02F),
        (0x1F0A0, 0x1F0FF),
        (0x1F100, 0x1F64F),
        (0x1F680, 0x1F6FF),
        (0x1F910, 0x1F96B),
        (0x1F980, 0x1F9E0),
    )
    return any(start <= ord(char) <= end for start, end in EMOJI_MAPPING)


def is_emoji(char):
    EMOJI_MAPPING = (
        # (0x0080, 0x02AF),
        # (0x0300, 0x03FF),
        # (0x0600, 0x06FF),
        # (0x0C00, 0x0C7F),
        # (0x1DC0, 0x1DFF),
        # (0x1E00, 0x1EFF),
        # (0x2000, 0x209F),
        # (0x20D0, 0x214F),
        # (0x2190, 0x23FF),
        # (0x2460, 0x25FF),
        # (0x2600, 0x27EF),
        # (0x2900, 0x2935),
        # (0x2B00, 0x2BFF),
        # (0x2C60, 0x2C7F),
        # (0x2E00, 0x2E7F),
        # (0x3000, 0x303F),
        (0xA490, 0xA4CF),
        (0xE000, 0xF8FF),
        (0xFE00, 0xFE0F),
        (0xFE30, 0xFE4F),
        (0x1F000, 0x1F02F),
        (0x1F0A0, 0x1F0FF),
        (0x1F100, 0x1F64F),
        (0x1F680, 0x1F6FF),
        (0x1F910, 0x1F96B),
        (0x1F980, 0x1F9E0),
    )
    return any(start <= ord(char) <= end for start, end in EMOJI_MAPPING)


def is_ignored_emoji(char):
    EMOJI_MAPPING = (
        (0x0080, 0x02AF),
        (0x0300, 0x03FF),
        (0x0600, 0x06FF),
        (0x0C00, 0x0C7F),
        (0x1DC0, 0x1DFF),
        (0x1E00, 0x1EFF),
        (0x2000, 0x209F),
        (0x20D0, 0x214F)
    )
    return any(start <= ord(char) <= end for start, end in EMOJI_MAPPING)


def is_cjk(char):
    CJK_MAPPING = (
        (0x3040, 0x30FF),  # Hiragana + Katakana
        (0xFF66, 0xFF9D),  # Half-Width Katakana
        (0x4E00, 0x9FAF)  # Common/Uncommon Kanji
    )
    return any(start <= ord(char) <= end for start, end in CJK_MAPPING)


def is_english(char):
    # basically English characters save for w because of laughter
    RANGE_CHECK = (
        (0x61, 0x76),  # a to v
        (0x78, 0x7a),  # x to z
        (0x41, 0x56),  # A to V
        (0x58, 0x5a),  # X to Z
        (0xFF41, 0xFF56),  # ａ to ｖ
        (0xFF58, 0xFF5A),  # ｘ to ｚ
        (0xFF21, 0xFF36),  # Ａ to Ｖ
        (0xFF58, 0xFF3A),  # Ｘ to Ｚ
    )
    return any(start <= ord(char) <= end for start, end in RANGE_CHECK)


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

                ratio = jpenratio(lowercase_msg_content)
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

    def make_set(english, spanish, pipeline=None):
        if pipeline:
            eng_pred = pipeline.predict(english)
            sp_pred = pipeline.predict(spanish)
            new_english = []
            new_spanish = []
            for i in range(len(english)):
                if eng_pred[i] == 'en':
                    new_english.append(english[i])
            for i in range(len(spanish)):
                if sp_pred[i] == 'sp':
                    new_spanish.append(spanish[i])
            spanish = new_spanish
            english = new_english

        x = np.array(english + spanish)
        y = np.array(['en'] * len(english) + ['sp'] * len(spanish))

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


def detect_language(text):
    probs = here.bot.langdetect.predict_proba([text])[0]
    if probs[0] > 0.9:
        return 'en'
    elif probs[0] < 0.1:
        return 'es'
    else:
        return None


async def load_language_detection_model():
    await here._loop.run_in_executor(None, _pre_load_language_detection_model)


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


def args_discriminator(args: str):
    """
    Takes in a string of args and pulls out IDs and times then leaves the reason.
    :param args: A string containing all the args
    :return: Class object with list 'users', time, reason
    """

    @dataclass
    class Args:
        def __init__(self,
                     user_ids: List[int],
                     time_string: str,
                     length: List[int],
                     time_arg: str,
                     time_obj: datetime,
                     reason: str):
            self.user_ids = user_ids  # list of users
            self.time_string = time_string  # string formatted like %Y/%m/%d %H:%M UTC
            self.length = length  # list of [days, hours, minutes]
            self.time_arg = time_arg
            self.time_obj = time_obj
            self.reason = reason

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


async def send_to_test_channel(*content):
    content = ' '.join([str(i) for i in content])
    test_chan_id = os.getenv("BOT_TEST_CHANNEL")

    if test_chan_id:
        channel = here.bot.get_channel(int(test_chan_id))
        if channel:
            try:
                await safe_send(channel, content)
            except discord.Forbidden:
                print("Failed to send content to test_channel in send_to_test_channel()")


@app_commands.context_menu(name="Delete and log")
@app_commands.guilds(SP_SERV_GUILD)
@app_commands.default_permissions(manage_messages=True)
async def delete_and_log(interaction: discord.Interaction, message: discord.Message):
    await Interactions.delete_and_log(interaction, message)


@app_commands.context_menu(name="Mute user (1h)")
@app_commands.guilds(SP_SERV_GUILD)
@app_commands.default_permissions()
async def context_message_mute(interaction: discord.Interaction, message: discord.Message):
    await Interactions.context_message_mute(interaction, message)


@app_commands.context_menu(name="Mute user (1h)")
@app_commands.guilds(SP_SERV_GUILD)
@app_commands.default_permissions()
async def context_member_mute(interaction: discord.Interaction, member: discord.Member):
    await Interactions.context_member_mute(interaction, member)


@app_commands.context_menu(name="Ban user")
@app_commands.guilds(SP_SERV_GUILD)
@app_commands.default_permissions()
async def ban_and_clear_message(interaction: discord.Interaction,
                                message: discord.Message):  # message commands return the message
    await Interactions.ban_and_clear_main(interaction, message)


@app_commands.context_menu(name="Ban user")
@app_commands.guilds(SP_SERV_GUILD)
@app_commands.default_permissions()
async def ban_and_clear_member(interaction: discord.Interaction,
                               member: discord.User):  # message commands return the message
    await Interactions.ban_and_clear_main(interaction, member)


@app_commands.context_menu(name="View modlog")
@app_commands.guilds(SP_SERV_GUILD)
@app_commands.default_permissions()
async def context_view_modlog(interaction: discord.Interaction, member: discord.Member):
    modlog = here.bot.get_command("modlog")
    ctx = await commands.Context.from_interaction(interaction)
    embed = await ctx.invoke(modlog, str(member.id), post_embed=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.context_menu(name="View user stats")
@app_commands.guilds(SP_SERV_GUILD)
@app_commands.default_permissions()
async def context_view_user_stats(interaction: discord.Interaction, member: discord.Member):
    user = here.bot.get_command("user")
    ctx = await commands.Context.from_interaction(interaction)
    embed = await ctx.invoke(user, member=str(member.id), post_embed=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@app_commands.context_menu(name="Get ID from message")
@app_commands.guilds(SP_SERV_GUILD)
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


async def hf_sync():
    # Sp serv
    commands_in_file = [delete_and_log, context_message_mute, context_member_mute,
                        context_view_modlog, context_view_user_stats, get_id_from_message,
                        ban_and_clear_member, ban_and_clear_message, log_message_context]

    # Add any commands from this file not currently registered in the tree (new/renamed commands)
    for command in commands_in_file:
        # if command.name not in command_names_in_tree:
        here.bot.tree.add_command(command, guild=SP_SERV_GUILD, override=True)

    # Try to sync
    try:
        await here.bot.tree.sync(guild=SP_SERV_GUILD)
    except discord.Forbidden:
        print("Failed to sync commands to SP_SERV_GUILD")

    # Ry serv
    for command in []:
        if command not in here.bot.tree.get_commands(guild=RY_SERV):
            here.bot.tree.add_command(command, guild=RY_SERV, override=True)

    try:
        await here.bot.tree.sync(guild=RY_SERV)
    except discord.Forbidden:
        print("Failed to sync commands to RY_SERV")


def message_list_to_text(msgs: list[discord.Message], text: str = "") -> str:
    for msg in msgs:
        date = msg.created_at.strftime("%d/%m/%y %H:%M:%S")
        author = f"{msg.author.name}#{msg.author.discriminator} ({msg.author.id})"
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
        file = discord.File(write_file, filename=filename)

    return file


async def send_attachments_to_thread_on_message(log_message: discord.Message, attachments_message: discord.Message):
    """This command creates a thread on a log message and uploads all the attachments from an "attachment_message"
    to a thread on the log message"""
    thread = None
    if attachments_message.attachments:
        try:
            # Either get the thread on a message or create a new thread
            if thread := log_message.guild.get_thread(log_message.id):
                pass
            else:
                thread = await log_message.create_thread(name=f"msg_attachments_{attachments_message.id}")
        except (discord.Forbidden, discord.HTTPException):
            pass
        else:
            for attachment in attachments_message.attachments:
                try:
                    file = await attachment.to_file(filename=attachment.filename,
                                                    description=attachment.description,
                                                    use_cached=True,
                                                    spoiler=True)
                except discord.HTTPException:
                    try:
                        file = await attachment.to_file(filename=attachment.filename,
                                                        description=attachment.description,
                                                        spoiler=True)
                    except discord.Forbidden:
                        file = None

                if file:
                    try:
                        await safe_send(thread, file=file)
                    except (discord.Forbidden, discord.HTTPException) as e:
                        try:
                            await safe_send(thread, f"Error attempting to send {attachment.filename} "
                                                    f"({attachment.proxy_url}): {e}")
                        except (discord.Forbidden, discord.HTTPException):
                            pass
                else:
                    file_info = f"Failed to download file: {attachment.filename} - {attachment.description}\n" \
                                f"{attachment.proxy_url}"
                    try:
                        await safe_send(thread, file_info)
                    except (discord.Forbidden, discord.HTTPException):
                        pass

            # archive after uploading all attachments
            await thread.edit(archived=True)

    if attachments_message.embeds:
        for embed in attachments_message.embeds:
            # posting an image expands the image to an embed without title or desc., send those into the thread
            if embed.url and embed.thumbnail and not embed.title and not embed.description:
                if not thread:
                    # Either get the thread on a message or create a new thread
                    if thread := log_message.guild.get_thread(log_message.id):
                        pass
                    else:
                        thread = await log_message.create_thread(name=f"msg_attachments_{attachments_message.id}")
                try:
                    await safe_send(thread, embed.url)
                except (discord.Forbidden, discord.HTTPException) as e:
                    try:
                        await safe_send(thread, f"Error attempting to send attached link to message: {e}")
                    except (discord.Forbidden, discord.HTTPException):
                        pass


async def send_error_embed(bot: discord.Client,
                           ctx: Union[commands.Context, discord.Interaction],
                           error: Exception,
                           embed: discord.Embed):
    error = getattr(error, 'original', error)
    try:
        qualified_name = getattr(ctx.command, 'qualified_name', ctx.command.name)
    except AttributeError:  # ctx.command.name is also None
        qualified_name = "Non-command"
    traceback.print_tb(error.__traceback__)
    print(discord.utils.utcnow())
    print(f'Error in {qualified_name}:', file=sys.stderr)
    print(f'{error.__class__.__name__}: {error}', file=sys.stderr)

    exc = ''.join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
    if ctx.message:
        traceback_text = f'{ctx.message.jump_url}\n```py\n{exc}```'
    elif ctx.channel:
        traceback_text = f'{ctx.channel.mention}\n```py\n{exc}```'
    else:
        traceback_text = f'```py\n{exc}```'

    embed.timestamp = discord.utils.utcnow()
    traceback_logging_channel = int(os.getenv("ERROR_CHANNEL_ID"))
    view = None
    if ctx.message:
        view = discord.ui.View.from_message(ctx.message)
    await bot.get_channel(traceback_logging_channel).send(traceback_text[-2000:], embed=embed, view=view)
    print('')


class RaiView(discord.ui.View):
    async def on_error(self,
                       interaction: discord.Interaction,
                       error: Exception,
                       item: Union[discord.ui.Button, discord.ui.Select, discord.ui.TextInput]):
        e = discord.Embed(title=f'View Component Error ({str(item.type)})', colour=0xcc3366)
        e.add_field(name='Interaction User', value=f"{interaction.user} ({interaction.user.mention})")

        fmt = f'Channel: {interaction.channel} (ID: {interaction.channel.id})'
        if interaction.guild:
            fmt = f'{fmt}\nGuild: {interaction.guild} (ID: {interaction.guild.id})'

        e.add_field(name='Location', value=fmt, inline=False)

        if hasattr(item, "label"):
            e.add_field(name="Item label", value=item.label)

        if interaction.data:
            e.add_field(name="Data", value=f"```{interaction.data}```", inline=False)

        if interaction.extras:
            e.add_field(name="Extras", value=f"```{interaction.extras}```")

        await send_error_embed(interaction.client, interaction, error, e)


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
