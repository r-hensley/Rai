import discord
import asyncio
import os
import re
from discord.ext import commands
import json
import sys
from datetime import datetime, timedelta
from copy import deepcopy

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


def add_to_modlog(ctx, user, type, reason, silent, length=None):
    config = ctx.bot.db['modlog'].setdefault(str(ctx.guild.id), {'channel': ctx.channel.id})
    config.setdefault(str(user.id), []).append({'type': type,
                                                'reason': reason,
                                                'date': datetime.utcnow().strftime("%Y/%m/%d %H:%M UTC"),
                                                'silent': silent,
                                                'length': length,
                                                'jump_url': ctx.message.jump_url})
    return config


def green_embed(text):
    return discord.Embed(description=text, color=discord.Color(int('00ff00', 16)))


def red_embed(text):
    return discord.Embed(description=text, color=discord.Color(int('ff0000', 16)))


async def safe_send(destination, content=None, *, wait=False, embed=None):
    """A command to be clearer about permission errors when sending messages"""
    if not content and not embed:
        return
    perms_set = perms = False
    if isinstance(destination, commands.Context):
        if destination.guild:
            perms = destination.channel.permissions_for(destination.guild.me)
            perms_set = True
    elif isinstance(destination, discord.TextChannel):
        perms = destination.permissions_for(destination.guild.me)
        perms_set = True

    if perms_set:
        if embed and not perms.embed_links and perms.send_messages:
            await destination.send("I lack permission to upload embeds here.")
            raise discord.Forbidden

    try:
        return await destination.send(content, embed=embed)
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
    time_re = re.findall('^\d+d\d+h$|^\d+d$|^\d+h$', time)
    if time_re:
        if re.findall('^\d+d\d+h$', time):  # format: #d#h
            length = time_re[0][:-1].split('d')
            length = [length[0], length[1]]
        elif re.findall('^\d+d$', time):  # format: #d
            length = [time_re[0][:-1], '0']
        else:  # format: #h
            length = ['0', time_re[0][:-1]]
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
        await ctx.send('User not found')
    return None


def _predump_json():
    with open(f'{dir_path}/db_2.json', 'w') as write_file:
        json.dump(deepcopy(here.bot.db), write_file, indent=4)
    os.replace(f'{dir_path}/db_2.json', f'{dir_path}/db.json')

    with open(f'{dir_path}/stats_2.json', 'w') as write_file:
        json.dump(deepcopy(here.bot.stats), write_file, indent=1)
    os.replace(f'{dir_path}/stats_2.json', f'{dir_path}/stats.json')


async def dump_json():
    with await _lock:
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


def admin_check(ctx):
    if not ctx.guild:
        return
    try:
        ID = here.bot.db['mod_role'][str(ctx.guild.id)]['id']
        mod_role = ctx.guild.get_role(ID)
        return mod_role in ctx.author.roles or ctx.channel.permissions_for(ctx.author).administrator
    except KeyError:
        return ctx.channel.permissions_for(ctx.author).administrator
    except TypeError:
        return ctx.channel.permissions_for(ctx.author).administrator


def is_admin():
    async def pred(ctx):
        return admin_check(ctx)

    return commands.check(pred)


async def long_deleted_msg_notification(msg):
    try:
        notification = 'I may have deleted a message of yours that was long.  Here it was:'
        await msg.author.send(notification)
        await msg.author.send(msg.content)
    except discord.errors.Forbidden:
        if msg.author.id == 401683644529377290:
            return
        await msg.channel.send(f"<@{msg.author.id}> I deleted an important looking message of yours "
                               f"but you seem to have DMs disabled so I couldn't send it to you.")
        notification = \
            f"I deleted someone's message but they had DMs disabled ({msg.author.mention} {msg.author.name})"
        me = here.bot.get_user(here.bot.owner_id)
        await me.send(notification)
        # await me.send(msg.author.name, msg.content)


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

async def ban_check_servers(bot, bans_channel, member):
    in_servers_msg = f"__I have found the user {member.name} ({member.id}) in the following guilds:\n__"
    found = False
    for guild in bot.guilds:
        if member in guild.members:
            found = True
            in_servers_msg += f"{guild.name}\n"
    if found:
        await bans_channel.send(in_servers_msg)

def jpenratio(msg):
    text = _emoji.sub('', _url.sub('', msg.content))
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
        (0x1F980, 0x1F9E0)
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


async def uhc_check(msg):
    try:
        if msg.guild.id == 189571157446492161 and len(msg.content) > 3:
            if here.bot.db['ultraHardcore']['users'].get(str(msg.author.id), [False])[0]:
                msg.content = msg.content.casefold().replace('what is your native language', '') \
                    .replace('welcome', '').replace("what's your native language", "")
                jpRole = msg.guild.get_role(196765998706196480)
                ratio = jpenratio(msg)
                # if I delete a long message

                if not msg.content:
                    return

                # allow Kotoba bot commands
                if msg.content[0:2] in ['k!', 't!'] \
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
