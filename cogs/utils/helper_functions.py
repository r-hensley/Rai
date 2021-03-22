import discord
import asyncio
import os
import re
from discord.ext import commands
import json, csv
import sys
from datetime import datetime, timedelta
from copy import deepcopy
import shutil
from textblob import TextBlob as tb
from functools import partial
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.naive_bayes import MultinomialNB
from sklearn.feature_extraction.text import CountVectorizer

dir_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

here = sys.modules[__name__]
here.bot = None

BANS_CHANNEL_ID = 329576845949534208

def setup(bot):
    if here.bot is None:
        here.bot = bot
    else:
        pass


# credit: https://gist.github.com/dperini/729294
_url = re.compile("""
            # protocol identifier
            (?:(?:https?|ftp)://)
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
              (?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))
            |
              # host name
              (?:(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)
              # domain name
              (?:\.(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)*
              # TLD identifier
              (?:\.(?:[a-z\u00a1-\uffff]{2,}))
              # TLD may end with dot
              \.?
            )
            # port number
            (?::\d{2,5})?
            # resource path
            (?:[/?#]\S*)?
        """, re.VERBOSE | re.I)

_emoji = re.compile(r'<a?(:[A-Za-z0-9\_]+:|#|@|@&)!?[0-9]{17,20}>')

_lock = asyncio.Lock()
_loop = asyncio.get_event_loop()


def count_messages(member, guild=None):
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


def add_to_modlog(ctx, user, type, reason, silent, length=None):
    if ctx:
        jump_url = ctx.message.jump_url
        config = here.bot.db['modlog'].setdefault(str(ctx.guild.id), {'channel': None})
    else:  # "user" is actually a list of [member, guild] here, forgive me for how shitty that is lol
        guild = user[1]
        user = user[0]
        jump_url = None  # this would be the case for entries that come from the the logger module
        if str(guild.id) in here.bot.db['modlog']:
            config = here.bot.db['modlog'][str(guild.id)]

        else:
            return  # this should only happen from on_member_ban events from logger module

    config.setdefault(str(user.id), []).append({'type': type,
                                                'reason': reason,
                                                'date': datetime.utcnow().strftime("%Y/%m/%d %H:%M UTC"),
                                                'silent': silent,
                                                'length': length,
                                                'jump_url': jump_url})
    return config


def green_embed(text):
    return discord.Embed(description=text, color=discord.Color(int('00ff00', 16)))


def red_embed(text):
    return discord.Embed(description=text, color=discord.Color(int('ff0000', 16)))


async def safe_send(destination, content=None, *, wait=False, embed=None, delete_after=None, file=None):
    """A command to be clearer about permission errors when sending messages"""
    if not content and not embed and not file:
        raise SyntaxError("You maybe didn't state a destination, or you tried to send a None")
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
        return await destination.send(content, embed=embed, delete_after=delete_after, file=file)
    except discord.Forbidden:
        if isinstance(destination, commands.Context):
            ctx = destination  # shorter and more accurate name
            msg_content = f"Rai tried to a message to #{ctx.channel.name} but lacked permissions to do so (either " \
                          f"messages or embeds)."
            # if ctx.guild:
            # if str(ctx.guild.id) in ctx.bot.db['mod_channel']:
            #     await safe_send(ctx.bot.get_channel(int(ctx.bot.db['mod_channel'][str(ctx.guild.id)])), msg_content)
            # else:
            await safe_send(ctx.author, msg_content)
            # else:
            #     if isinstance(ctx.channel, discord.DMChannel):
            #         pass
        raise


def parse_time(time):
    time_re = re.search('(\d+d\d+h)|(\d+d)|(\d+h)', time)
    if time_re:
        if time_re.group(1):  # format: #d#h
            length = time_re.group(1)[:-1].split('d')
            length = [length[0], length[1]]
        elif time_re.group(2):  # format: #d
            length = [time_re.group(2)[:-1], '0']
        else:  # format: #h
            length = ['0', time_re.group(3)[:-1]]
    else:
        return False, False
    finish_time = datetime.utcnow() + timedelta(days=int(length[0]), hours=int(length[1]))
    time_string = finish_time.strftime("%Y/%m/%d %H:%M UTC")
    return time_string, length


async def member_converter(ctx, user_in):
    # check for an ID
    user_id = re.findall("(^<@!?\d{17,22}>$|^\d{17,22}$)", str(user_in))
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
    shutil.copy(f'{dir_path}/db_3.json', f'{dir_path}/db_4.json')
    shutil.copy(f'{dir_path}/db_2.json', f'{dir_path}/db_3.json')
    shutil.copy(f'{dir_path}/db.json', f'{dir_path}/db_2.json')
    with open(f'{dir_path}/db_temp.json', 'w') as write_file:
        json.dump(db_copy, write_file, indent=4)
    shutil.copy(f'{dir_path}/db_temp.json', f'{dir_path}/db.json')

    shutil.copy(f'{dir_path}/stats_3.json', f'{dir_path}/stats_4.json')
    shutil.copy(f'{dir_path}/stats_2.json', f'{dir_path}/stats_3.json')
    shutil.copy(f'{dir_path}/stats.json', f'{dir_path}/stats_2.json')
    with open(f'{dir_path}/stats_temp.json', 'w') as write_file:
        json.dump(stats_copy, write_file, indent=1)
    shutil.copy(f'{dir_path}/stats_temp.json', f'{dir_path}/stats.json')


async def dump_json():
    with await _lock:
        try:
            await _loop.run_in_executor(None, _predump_json)
        except RuntimeError:
            print("Restarting dump_json on a RuntimeError")
            await _loop.run_in_executor(None, _predump_json)


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
    if not ctx.guild:
        return
    try:
        ID = here.bot.db['mod_role'][str(ctx.guild.id)]['id']
        mod_role = ctx.guild.get_role(ID)
        return mod_role in ctx.author.roles or ctx.channel.permissions_for(ctx.author).administrator
    except (KeyError, TypeError):
        return ctx.channel.permissions_for(ctx.author).administrator


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


async def ban_check_servers(bot, bans_channel, member, ping=False):
    in_servers_msg = f"__I have found the user {str(member)} ({member.id}) in the following guilds:__"
    guilds = []
    if member in bans_channel.guild.members:
        ping = False
    for guild in bot.guilds:  # type: discord.Guild
        if guild.id in bot.db['ignored_servers']:
            continue
        if member in guild.members:
            messages: int = count_messages(member, guild)
            day = None
            if messages:
                try:
                    config = bot.stats[str(guild.id)]['messages']
                    for day in reversed(list(config)):  # type: str
                        if str(member.id) in config[day]:
                            break
                except KeyError:
                    pass
            guilds.append([guild, messages, day])

    for guild in guilds:  # type: list
        in_servers_msg += f"\n**{guild[0].name}**"
        if guild[1]:
            date = f"{guild[2][0:4]}/{guild[2][4:6]}/{guild[2][6:]}"
            in_servers_msg += f" (Messages: {guild[1]}, Last message: {date})"
        if ping:
            if str(guild[0].id) in bot.db['bansub']['guild_to_role']:
                role_id = bot.db['bansub']['guild_to_role'][str(guild[0].id)]
                for user in bot.db['bansub']['user_to_role']:
                    if role_id in bot.db['bansub']['user_to_role'][user]:
                        in_servers_msg += f" <@{user}> "

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
    except discord.errors.Forbidden:
        return


async def uhc_check(msg):
    try:
        if msg.guild.id == 189571157446492161 and len(msg.content) > 3:
            if here.bot.db['ultraHardcore']['users'].get(str(msg.author.id), [False])[0]:
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
                    if msg.channel.id not in here.bot.db['ultraHardcore']['ignore']:
                        msg_content = msg.content
                        if jpRole in msg.author.roles:
                            if ratio < .55:
                                try:
                                    await msg.delete()
                                except discord.errors.NotFound:
                                    pass
                                if len(msg_content) > 30:
                                    await long_deleted_msg_notification(msg)
                        else:
                            if ratio > .45:
                                try:
                                    await msg.delete()
                                except discord.errors.NotFound:
                                    pass
                                if len(msg_content) > 60:
                                    await long_deleted_msg_notification(msg)
    except AttributeError:
        pass


def _pre_load_language_dection_model():
    english = []
    spanish = []
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


async def load_language_dection_model():
    await _loop.run_in_executor(None, _pre_load_language_dection_model)


def _predetect(text):
    return tb(text).detect_language()


async def textblob_detect_language(text):
    return await _loop.run_in_executor(None, partial(_predetect, text))

