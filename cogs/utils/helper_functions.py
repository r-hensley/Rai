import discord
import asyncio
import os
import re
from discord.ext import commands
import json
import sys

dir_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

self = sys.modules[__name__]
self.bot = None


def setup(bot):
    if self.bot is None:
        self.bot = bot
    else:
        msg = f"Bot is alerady initialized to {self.bot}"
        raise RuntimeError(msg)


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

_emoji = re.compile(r'<a?:[A-Za-z0-9\_]+:[0-9]{17,20}>')


def dump_json():
    with open(f'{dir_path}/database_2.json', 'w') as write_file:
        json.dump(self.bot.db, write_file, indent=4)
        write_file.flush()
        os.fsync(write_file.fileno())
    os.remove(f'{dir_path}/database.json')
    os.rename(f'{dir_path}/database_2.json', f'{dir_path}/database.json')


def is_admin():
    async def pred(ctx):
        try:
            ID = self.bot.db['mod_role'][str(ctx.guild.id)]['id']
            mod_role = ctx.guild.get_role(ID)
            return mod_role in ctx.author.roles or ctx.channel.permissions_for(ctx.author).administrator
        except KeyError:
            return ctx.channel.permissions_for(ctx.author).administrator
        except TypeError:
            return ctx.channel.permissions_for(ctx.author).administrator

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
        me = self.bot.get_user(self.bot.owner_id)
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
    return _emoji.sub('', _url.sub('', msg.content))


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