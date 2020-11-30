import discord
from discord.ext import commands
from datetime import datetime, timedelta, date
from .utils import helper_functions as hf
import re
import textblob
from Levenshtein import distance as LDist
import string
import asyncio, aiohttp, async_timeout
from urllib.error import HTTPError
from bs4 import BeautifulSoup
from collections import Counter
from inspect import cleandoc
from random import choice

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
COLOR_CHANNEL_ID = 577382927596257280
BLACKLIST_CHANNEL_ID = 533863928263082014
BANS_CHANNEL_ID = 329576845949534208
MODERATING_CHANNEL_ID = 257990571103223809
MODCHAT_SERVER_ID = 257984339025985546
RYRY_SPAM_CHAN = 275879535977955330
JP_SERVER_ID = 189571157446492161
SP_SERVER_ID = 243838819743432704
CH_SERVER_ID = 266695661670367232
CL_SERVER_ID = 320439136236601344
RY_SERVER_ID = 275146036178059265


ENG_ROLE = {
    266695661670367232: 266778623631949826, # C-E Learning English Role
    320439136236601344: 474825178204078081 # r/CL Learning English Role
}


def blacklist_check():
    async def pred(ctx):
        if not ctx.guild:
            return
        if ctx.author in ctx.bot.get_guild(MODCHAT_SERVER_ID).members:
            if ctx.guild.id == MODCHAT_SERVER_ID or hf.admin_check(ctx):
                return True

    return commands.check(pred)


class General(commands.Cog):
    """My custom cog that does stuff!"""

    def __init__(self, bot):
        self.bot = bot
        self.ignored_characters = []
        hf.setup(bot)

    @commands.Cog.listener()
    async def on_message(self, msg):
        if msg.author.bot:
            if msg.author.id != 720900750724825138:  # a window for BurdBot to post questions to AOTW
                return

        """BurdBot's window to open questions in #audio_of_the_week"""
        async def burdbot_window():
            if msg.channel.id != 620997764524015647:  # aotw_feedback
                return
            if msg.author.id != 720900750724825138:  # burdbot
                return
            if not msg.attachments:
                return
            ctx = await self.bot.get_context(msg)
            if "AOTW recording" in msg.content:
                await ctx.invoke(self.bot.get_command("question"), args=msg.content)
        await burdbot_window()

        # """Messages/pings to Rai"""
        # async def message_to_bot():
        #     if msg.content:
        #         if msg.content[0] == ';':
        #             return
        #     if (msg.channel == msg.author.dm_channel and msg.author.id not in [202995638860906496, 414873201349361664]) \
        #             or '270366726737231884' in msg.content:
        #         if isinstance(msg.channel, discord.DMChannel):
        #             embed = hf.green_embed(f"DM from {msg.author.mention} "
        #                                    f"({msg.author.name}#{msg.author.discriminator}) - "
        #                                    f"[Jump URL]({msg.jump_url})")
        #             async for message in msg.channel.history(limit=2):
        #                 if 'report' in message.content.casefold() and message.author == self.bot.user:
        #                     return
        #         else:
        #             embed = hf.green_embed(f"Ping from {msg.author.mention} "
        #                                    f"({msg.author.name}#{msg.author.discriminator}) in {msg.channel.mention} "
        #                                    f"({msg.guild.name}) - [Jump URL]({msg.jump_url})")
        #         if msg.content:
        #             embed.add_field(name="Text", value=msg.content[:1024])
        #         if msg.content[1024:]:
        #             embed.add_field(name="Text pt. 2", value=msg.content[1024:])
        #         if msg.attachments:
        #             for attachment in msg.attachments:
        #                 embed.add_field(name="Attachment", value=attachment.url)
        #
        #         channel_id = str(msg.channel.id)
        #         length = len(channel_id)
        #         i = [channel_id[round(0 * length / 3): round(1 * length / 3)],
        #              channel_id[round(1 * length / 3): round(2 * length / 3)],
        #              channel_id[round(2 * length / 3): round(3 * length / 3)]]
        #         color = {'r': int(i[0]) % 255, 'g': int(i[1]) % 255, 'b': int(i[2]) % 255}
        #         embed.color = discord.Color.from_rgb(color['r'], color['g'], color['b'])
        #
        #         spam_chan = self.bot.get_channel(RYRY_SPAM_CHAN)
        #         await spam_chan.send(f"{msg.channel.id} <@202995638860906496>", embed=embed)
        # await message_to_bot()

        """Message as the bot"""
        async def message_as_bot():
            if isinstance(msg.channel, discord.DMChannel) \
                    and msg.author.id == self.bot.owner_id and msg.content[0:3] == 'msg':
                await self.bot.get_channel(int(msg.content[4:22])).send(str(msg.content[22:]))

        await message_as_bot()

        """Replace tatsumaki/nadeko serverinfo posts"""
        async def replace_tatsumaki_posts():
            if msg.content in ['t!serverinfo', 't!server', 't!sinfo', '.serverinfo', '.sinfo']:
                if msg.guild.id in [JP_SERVER_ID, SP_SERVER_ID, RY_SERVER_ID]:
                    new_ctx = await self.bot.get_context(msg)
                    await new_ctx.invoke(self.serverinfo)
        await replace_tatsumaki_posts()

        ##########################################

        if not msg.guild:  # all code after this has msg.guild requirement
            return

        ##########################################

        "automatic word filter"
        async def wordfilter():
            if not msg.guild.me.guild_permissions.ban_members:
                return
            if str(msg.guild.id) not in self.bot.db['wordfilter']:
                return
            config = self.bot.db['wordfilter'][str(msg.guild.id)]
            if not config:
                return

            time_ago = datetime.utcnow() - msg.author.joined_at

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
                                asyncio.sleep(3)
                                await msg.author.ban(reason=reason)
                            except (discord.Forbidden, discord.HTTPException):
                                pass
        await wordfilter()

        """Ping me if someone says my name"""
        async def mention_ping():
            cont = str(msg.content).casefold()
            if msg.author.bot or msg.author.id == 202995638860906496:
                return
            for word in cont.casefold():
                for ignored_word in ['http', ':']:
                    if ignored_word in word:
                        cont = cont.replace(word, "")

            found_word = False
            ignored_words = ['bryan', 'aryan', 'biryani', 'ryan gosling', 'ryan-reynold', 'ryan reynold', 'ryan_army']
            for word in ignored_words:
                if word in cont.casefold():  # why do people say these so often...
                    cont = re.sub(word, '', cont, flags=re.IGNORECASE)
                if msg.guild:
                    if msg.guild.id == SP_SERVER_ID:
                        cont = re.sub(r'ryan', '', cont, flags=re.IGNORECASE)

            to_check_words = ['ryry', 'ryan', 'らいらい', 'ライライ', '来雷', '雷来']
            for word in to_check_words:
                if word in cont.casefold():
                    found_word = True

            if found_word:
                await self.bot.spamChan.send(
                    f'**By {msg.author.name} in {msg.channel.mention}** ({msg.channel.name}): '
                    f'\n{msg.content}'
                    f'\n{msg.jump_url} <@202995638860906496>'[:2000])

        await mention_ping()

        """Self mute"""
        try:
            if self.bot.db['selfmute'][str(msg.guild.id)][str(msg.author.id)]['enable']:
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
        except KeyError:
            pass

        """check for servers of banned IDs"""
        async def check_guilds():
            if msg.guild.id == MODCHAT_SERVER_ID:
                async def check_user(content):
                    bans_channel = msg.channel
                    re_result = re.findall('(?:^| |\n)(\d{17,22})', content)
                    users = []
                    if re_result:
                        for user_id in [int(user_id) for user_id in re_result]:
                            if user_id == 270366726737231884:
                                continue
                            user = self.bot.get_user(user_id)
                            if user:
                                users.append(user)
                    for user in users:
                        await hf.ban_check_servers(self.bot, bans_channel, user, ping=False)

                await check_user(msg.content)
                for embed in msg.embeds:
                    if embed.description:
                        await check_user(embed.description)

        await check_guilds()

        """chinese server banned words"""
        words = ['动态网自由门', '天安門', '天安门', '法輪功', '李洪志', 'Free Tibet', 'Tiananmen Square',
                 '反右派鬥爭', 'The Anti-Rightist Struggle', '大躍進政策', 'The Great Leap Forward', '文化大革命',
                 '人權', 'Human Rights', '民運', 'Democratization', '自由', 'Freedom', '獨立', 'Independence']
        if msg.guild.id in [CH_SERVER_ID, 494502230385491978, CL_SERVER_ID, RY_SERVER_ID]:
            word_count = 0
            for word in words:
                if word in msg.content:
                    word_count += 1
                if word_count == 5:
                    mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][str(msg.guild.id)])
                    log_channel = self.bot.get_channel(self.bot.db['bans'][str(msg.guild.id)]['channel'])
                    if datetime.utcnow() - msg.author.joined_at < timedelta(minutes=60):
                        try:
                            await msg.delete()
                        except discord.Forbidden:
                            await hf.safe_send(mod_channel,
                                               f"Rai is lacking the permission to delete messages for the Chinese "
                                               f"spam message.")
                        except discord.NotFound:
                            pass

                        # await msg.author.send("That message doesn't do anything to Chinese computers.  It doesn't "
                        #                       "get their internet shut down or get them arrested or anything.  "
                        #                       "It's just annoying, so please stop trying it.")
                        try:
                            await asyncio.sleep(3)
                            await msg.author.ban(reason=f"__Reason__: Automatic ban: Chinese banned words spam\n"
                                                        f"{msg.content[:100]}")
                        except discord.Forbidden:
                            await hf.safe_send(mod_channel,
                                               f"I tried to ban someone for the Chinese spam message, but I lack "
                                               f"the permission to ban users.")

                        await hf.safe_send(log_channel, f"Banned {msg.author.name} for the banned words spam message."
                                                        f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                                        f"\n```{msg.content}"[:1850] + '```')

                        break
                    else:
                        await hf.safe_send(mod_channel,
                                           f"Warning: {msg.author.name} may have said the banned words spam message"
                                           f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                           f"\n```{msg.content}"[:1995] + '```')
                        break

        """best sex dating"""
        async def spam_account_bans():
            words = ['amazingsexdating', 'bestdatingforall', 'nakedphotos.club', 'privatepage.vip', 'viewc.site',
                     'libra-sale.io', 'ethway.io', 'omg-airdrop', 'linkairdrop', "Airdrop Time!"]
            try:
                for word in words:
                    if word in msg.content:
                        time_ago = datetime.utcnow() - msg.author.joined_at
                        msg_text = f"Bot spam message in [{msg.guild.name}] - [{msg.channel.name}] by " \
                                   f"{msg.author.name} (joined {time_ago.seconds//3600}h " \
                                   f"{time_ago.seconds%3600//60}m ago [{time_ago}])```{msg.content}```"
                        await self.bot.get_user(self.bot.owner_id).send(msg_text)
                        if str(msg.author.guild.id) not in self.bot.db['auto_bans']:
                            return
                        if self.bot.db['auto_bans'][str(msg.author.guild.id)]['enable']:
                            if time_ago < timedelta(minutes=20) or \
                                    (msg.channel.id == 559291089018814464 and time_ago < timedelta(hours=5)):
                                if msg.author.id in [202995638860906496, 414873201349361664]:
                                    return
                                await msg.author.ban(reason=f'For posting spam link: {msg.content}',
                                                     delete_message_days=1)
                                self.bot.db['global_blacklist']['blacklist'].append(msg.author.id)
                                channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
                                emb = hf.red_embed(f"{msg.author.id} (automatic addition)")
                                emb.add_field(name="Reason", value=msg.content)
                                await hf.safe_send(channel, embed=emb)
                                created_ago = datetime.utcnow() - msg.author.created_at
                                joined_ago = datetime.utcnow() - msg.author.joined_at
                                message = f"**Banned a user for posting a {word} link.**" \
                                          f"\n**ID:** {msg.author.id}" \
                                          f"\n**Server:** {msg.author.guild.name}" \
                                          f"\n**Name:** {msg.author.name} {msg.author.mention}" \
                                          f"\n**Account creation:** {msg.author.created_at} " \
                                          f"({created_ago.days}d {created_ago.seconds//3600}h ago)" \
                                          f"\n**Server join:** {msg.author.joined_at} " \
                                          f"({joined_ago.days}d {joined_ago.seconds//3600}h ago)" \
                                          f"\n**Message:** {msg.content}"
                                emb2 = hf.red_embed(message)
                                emb2.color = discord.Color(int('000000', 16))
                                await self.bot.get_channel(BANS_CHANNEL_ID).send(embed=emb2)
                                if str(msg.guild.id) in self.bot.db['bans']:
                                    if self.bot.db['bans'][str(msg.guild.id)]['channel']:
                                        channel_id = self.bot.db['bans'][str(msg.guild.id)]['channel']
                                        await self.bot.get_channel(channel_id).send(embed=emb2)
                                return

            except KeyError as e:
                print(f'>>passed for key error on amazingsexdating: {e}<<')
                pass
            except AttributeError as e:
                print(f'>>passed for attributeerror in amazingsexdating: {e}<<')
                pass

        await spam_account_bans()

        """spanish server welcome channel module"""
        async def smart_welcome(msg):
            if msg.channel.id == SP_SERVER_ID:
                content = re.sub('> .*\n', '', msg.content.casefold())
                content = content.translate(str.maketrans('', '', string.punctuation))
                for word in ['hello', 'hi', 'hola', 'thanks', 'gracias']:
                    if content == word:
                        return
                if msg.content == '<@270366726737231884>':  # ping to Rai
                    return
                english_role = msg.guild.get_role(243853718758359040)
                spanish_role = msg.guild.get_role(243854128424550401)
                other_role = msg.guild.get_role(247020385730691073)
                for role in [english_role, spanish_role, other_role]:
                    if role in msg.author.roles:
                        return
                if datetime.utcnow() - msg.author.joined_at < timedelta(seconds=3):
                    return

                english = ['english', 'inglés', 'anglohablante', 'angloparlante']
                spanish = ['spanish', 'español', 'hispanohablante', 'hispanoparlante', 'castellano']
                other = ['other', 'neither', 'otro', 'otra', 'arabic', 'french', 'árabe', 'francés', 'portuguese',
                         'brazil', 'portuguesa', 'brazilian']
                both = ['both', 'ambos', 'los dos']
                txt1 = ''
                bools = [0, 0, 0, 0]  # eng, sp, other, both
                split = content.split()

                def check_language(language, index):
                    skip_next_word = False
                    for language_word in language:
                        for content_word in split:
                            if len(content_word) <= 3:
                                continue
                            if content_word in ['there']:
                                continue
                            if skip_next_word:
                                skip_next_word = False
                                continue
                            if content_word.startswith("learn") or content_word.startswith('aprend') \
                                    or content_word.startswith('estud') or content_word.startswith('stud') or \
                                    content_word.startswith('fluent'):
                                skip_next_word = True
                                continue
                            if LDist(language_word, content_word) < 3:
                                bools[index] += 1

                check_language(english, 0)
                check_language(spanish, 1)
                check_language(other, 2)
                check_language(both, 3)

                bool_results = 0
                for language_bool in bools:
                    if language_bool:
                        bool_results += 1
                if bool_results != 1:
                    await msg.channel.send(f"{msg.author.mention}\n"
                                           f"Hello! Welcome to the server!          Is your **native language**: "
                                           f"__English__, __Spanish__, __both__, or __neither__?\n"
                                           f"¡Hola! ¡Bienvenido(a) al servidor!    ¿Tu **idioma materno** es: "
                                           f"__el inglés__, __el español__, __ambos__ u __otro__?")
                    return

                if msg.content.startswith(';') or msg.content.startswith('.'):
                    return

                if bools[0]:
                    txt1 = " I've given you the `English Native` role! ¡Te he asignado el rol de `English Native`!\n\n"
                    await msg.author.add_roles(english_role)
                if bools[1]:
                    txt1 = " I've given you the `Spanish Native` role! ¡Te he asignado el rol de `Spanish Native!`\n\n"
                    await msg.author.add_roles(spanish_role)
                if bools[2]:
                    txt1 = " I've given you the `Other Native` role! ¡Te he asignado el rol de `Other Native!`\n\n"
                    await msg.author.add_roles(other_role)
                if bools[3]:
                    txt1 = " I've given you both roles! ¡Te he asignado ambos roles! "
                    await msg.author.add_roles(english_role, spanish_role)

                txt2 = "You can add more roles in <#703075065016877066>:\n" \
                       "Puedes añadirte más en <#703075065016877066>:\n\n" \
                       "Before using the server, please read the rules in <#243859172268048385>.\n" \
                       "Antes de usar el servidor, por favor lee las reglas en <#499544213466120192>."
                await hf.safe_send(msg.channel, msg.author.mention + txt1 + txt2)
        await smart_welcome(msg)

        """mods ping on spanish server"""
        if msg.guild.id in [SP_SERVER_ID, JP_SERVER_ID]:
            if '<@&642782671109488641>' in msg.content or '<@&240647591770062848>' in msg.content:
                em = discord.Embed(title=f"Staff Ping",
                                   description=f"From {msg.author.mention} ({msg.author.name}) "
                                               f"in {msg.channel.mention}\n[Jump URL]({msg.jump_url})",
                                   color=discord.Color(int('FFAA00', 16)),
                                   timestamp=datetime.utcnow())
                content = msg.content.replace('<@&642782671109488641>', '').replace('<@&240647591770062848>', '')
                if content:
                    em.add_field(name="Content", value=content)
                for user in self.bot.db['staff_ping'][str(msg.guild.id)]:
                    await hf.safe_send(self.bot.get_user(user), embed=em)
                if msg.guild.id == SP_SERVER_ID:
                    await hf.safe_send(msg.guild.get_channel(643077231534407690), embed=em)
                if msg.guild.id == JP_SERVER_ID:
                    await hf.safe_send(msg.guild.get_channel(755269708579733626), embed=em)

        """Replace .mute on spanish server"""
        if msg.guild.id == SP_SERVER_ID:
            if msg.content.startswith('.mute'):
                ctx = await self.bot.get_context(msg)
                if not hf.submod_check(ctx):
                    return
                args = msg.content.split()[1:]
                if len(args) == 1:
                    await ctx.invoke(self.bot.get_command('mute'), args[0])
                elif len(args) > 1:
                    await ctx.invoke(self.bot.get_command('mute'), args[0], member=' '.join(args[1:]))
                else:
                    await hf.safe_send(ctx, "Use `;mute` instead")

        """super_watch"""
        async def super_watch():
            try:
                config = self.bot.db['super_watch'][str(msg.guild.id)]
            except KeyError:
                return
            if str(msg.author.id) in config['users']:
                desc = "❗ "
                which = 'sw'
            elif hf.count_messages(msg.author) < 10 and config.get('enable', None):
                minutes_ago_created = int(((datetime.utcnow() - msg.author.created_at).total_seconds()) // 60)
                if minutes_ago_created > 60 or msg.channel.id == SP_SERVER_ID:
                    return
                desc = '🆕 '
                which = 'new'
            else:
                return

            desc += f"**{msg.author.name}#{msg.author.discriminator}** ({msg.author.id})"
            emb = discord.Embed(description=desc, color=0x00FFFF, timestamp=datetime.utcnow())
            emb.set_footer(text=f"#{msg.channel.name}")

            link = f"\n([Jump URL]({msg.jump_url})"
            if which == 'sw':
                if config['users'][str(msg.author.id)]:
                    link += f" － [Entry Reason]({config['users'][str(msg.author.id)]})"
            link += ')'
            emb.add_field(name="Message:", value=msg.content[:2000-len(link)] + link)

            await hf.safe_send(self.bot.get_channel(config['channel']), embed=emb)
        await super_watch()

        """Lang check: will check if above 3 characters + hardcore, or if above 15 characters + stats"""
        async def lang_check():
            lang = None
            hardcore = False
            if str(msg.guild.id) not in self.bot.stats:
                return None, False
            stripped_msg = hf.rem_emoji_url(msg)
            check_lang = False

            if msg.guild.id == SP_SERVER_ID and '*' not in msg.content and len(stripped_msg):
                if stripped_msg[0] not in '=;>' and len(stripped_msg) > 3:
                    if msg.channel.id not in self.bot.db['hardcore'][str(SP_SERVER_ID)]['ignore']:
                        hardcore_role = msg.guild.get_role(self.bot.db['hardcore'][str(SP_SERVER_ID)]['role'])
                        if hardcore_role in msg.author.roles:
                            check_lang = True
                            hardcore = True

            if str(msg.guild.id) in self.bot.stats:
                if len(stripped_msg) > 15 and self.bot.stats[str(msg.guild.id)].get('enable', None):
                    check_lang = True

            if check_lang:
                try:
                    pass
                    lang = await hf.detect_language(stripped_msg)
                except (textblob.exceptions.TranslatorError, HTTPError, TimeoutError):
                    pass
            return lang, hardcore
        lang, hardcore = await lang_check()

        """Message counting"""
        # 'stats':
        #     guild id: str:
        #         'enable' = True/False
        #         'messages' (for ,u):
        #             {20200403:
        #                 {user id: str:
        #                   'emoji': {emoji1: 1, emoji2: 3},
        #                   'lang': {'eng': 25, 'sp': 30},
        #                   'channels': {
        #                     channel id: str: 30,
        #                     channel id: str: 20}
        #                 user_id2:
        #                   emoji: {emoji1: 1, emoji2: 3},
        #                   lang: {'eng': 25, 'sp': 30},
        #                   channels: {
        #                     channel1: 40,
        #                     channel2: 10}
        #                 ...}
        #             20200404:
        #                 {user_id1:
        #                   emoji: {emoji1: 1, emoji2: 3},
        #                   lang: {'eng': 25, 'sp': 30},
        #                   channels: {
        #                     channel1: 30,
        #                     channel2: 20}
        #                 user_id2:
        #                   emoji: {emoji1: 1, emoji2: 3},
        #                   lang: {'eng': 25, 'sp': 30},
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
            date_str = datetime.utcnow().strftime("%Y%m%d")
            if date_str not in config['messages']:
                config['messages'][date_str] = {}
            today = config['messages'][date_str]
            author = str(msg.author.id)
            channel = str(msg.channel.id)

            # message count
            today.setdefault(author, {})
            today[author].setdefault('channels', {})
            today[author]['channels'][channel] = today[author]['channels'].get(channel, 0) + 1

            # emojis
            emojis = re.findall(':([A-Za-z0-9\_]+):', msg.content)
            for character in msg.content:
                if hf.is_emoji(character):
                    emojis.append(character)
                if hf.is_ignored_emoji(character) and character not in self.ignored_characters:
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

        """Ultra Hardcore"""
        await hf.uhc_check(msg)

        """Chinese server hardcore mode"""
        async def cn_lang_check(check_hardcore_role=True):
            content = re.sub("(>>>|>) .*$\n?", "", msg.content, flags=re.M)  # removes lines that start with a quote
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

                ratio = hf.jpenratio(content)
                if ratio is not None:  # it might be "0" so I can't do "if ratio"
                    if learning_eng in msg.author.roles:
                        if ratio < .55:
                            try:
                                await msg.delete()
                            except discord.errors.NotFound:
                                pass
                            if len(content) > 30:
                                await hf.long_deleted_msg_notification(msg)
                    else:
                        if ratio > .45:
                            try:
                                await msg.delete()
                            except discord.errors.NotFound:
                                pass
                            if len(content) > 60:
                                await hf.long_deleted_msg_notification(msg)

        if msg.guild.id in [CH_SERVER_ID, CL_SERVER_ID]:
            try:
                if msg.channel.id in self.bot.db['forcehardcore']:
                    await cn_lang_check(check_hardcore_role=False)

                elif msg.guild.id == CH_SERVER_ID:
                    if ('*' not in msg.content
                            and msg.channel.id not in self.bot.db['hardcore'][str(CH_SERVER_ID)]['ignore']):
                        await cn_lang_check()
            except KeyError:
                self.bot.db['forcehardcore'] = []

        """Spanish server hardcore"""
        async def spanish_server_hardcore():
            if not hardcore:  # this should be set in the lang_check function
                return
            learning_eng = msg.guild.get_role(247021017740869632)
            learning_sp = msg.guild.get_role(297415063302832128)
            if learning_eng in msg.author.roles:  # learning English, delete all Spanish
                if lang == 'es':
                    try:
                        await msg.delete()
                    except discord.errors.NotFound:
                        return
                    if len(msg.content) > 30:
                        await hf.long_deleted_msg_notification(msg)
            elif learning_sp in msg.author.roles:  # learning Spanish, delete all English
                if 'holi' in msg.content.casefold():
                    return
                if lang == 'en':
                    try:
                        await msg.delete()
                    except discord.errors.NotFound:
                        return
                    if len(msg.content) > 30:
                        await hf.long_deleted_msg_notification(msg)
            else:
                try:
                    await msg.author.send("You have hardcore enabled but you don't have the proper "
                                          "learning role.  Please attach either 'Learning Spanish' or "
                                          "'Learning English' to properly use hardcore mode, or take "
                                          "off hardcore mode using the reactions in the server rules "
                                          "page")
                except discord.errors.Forbidden:
                    pass
        await spanish_server_hardcore()

        """no filter hc"""
        async def no_filter_hc():
            if msg.channel.id == 193966083886153729:
                jpRole = msg.guild.get_role(196765998706196480)
                enRole = msg.guild.get_role(197100137665921024)
                if jpRole in msg.author.roles and enRole in msg.author.roles:
                    return
                ratio = hf.jpenratio(msg.content.casefold())
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
                        except (discord.errors.NotFound, discord.Forbidden):
                            pass
                else:
                    if ratio > .45:
                        try:
                            await msg.delete()
                            await msg.author.send(f"I've deleted your message from {nf}. In that channel, you must "
                                                  "speak Japanese only. Here is the message I deleted:")
                            await msg.author.send(f"```{msg.content[:1993]}```")
                        except (discord.errors.NotFound, discord.Forbidden):
                            pass
        await no_filter_hc()

    @commands.command(hidden=True)
    @commands.bot_has_permissions(send_messages=True)
    async def help(self, ctx, *, arg=''):
        async def check_command(command):
            try:
                a = await command.can_run(ctx)
            except commands.BotMissingPermissions:
                a = False
            except commands.CheckFailure:
                a = False
            b = not command.hidden
            return a and b

        if arg:  # user wants help on a specific command/cog
            requested = self.bot.get_command(arg)
            which = 'command'
            if not requested:
                requested = self.bot.get_cog(arg)
                which = 'cog'
            if not requested:
                await hf.safe_send(ctx, "I was unable to find the command or command module you requested.")
                return
            if which == 'command':
                message = f"**;{requested.qualified_name}**\n"
                if requested.aliases:
                    message += f"Aliases: `{'`, `'.join(requested.aliases)}`\n"
                if isinstance(requested, commands.Group):
                    usable_commands = sorted([c.name for c in requested.commands if await check_command(c)])
                    if usable_commands:
                        message += f"Subcommands: `{'`, `'.join(usable_commands)}`\n" \
                                   f"Use subcommands by chaining with the command group name. For example, " \
                                   f"`;{requested.name} {usable_commands[0]}`\n"

                message += '\n'
                if requested.help:
                    message += requested.help
                emb = hf.green_embed(cleandoc(message))
                await hf.safe_send(ctx, embed=emb)

            else:  # requested a cog
                message = f"**;{requested.qualified_name}**\n"
                c_list = sorted([c.name for c in requested.get_commands() if await check_command(c)])
                if c_list:
                    message += f"Commands: `{'`, `'.join(c_list)}`\n\n"
                else:
                    message += '\n\n'
                message += requested.description
                emb = hf.green_embed(cleandoc(message))
                await hf.safe_send(ctx, embed=emb)

        else:  # user wants to see full command list
            cmd_dict = {}
            to_send = "Type `;help <command>` for more info on any command or category. For (subcommands), chain with" \
                      " the parent command.\n\n"
            for cog in self.bot.cogs:
                cmd_dict[cog] = []
                for command in self.bot.cogs[cog].get_commands():
                    if await check_command(command):
                        if isinstance(command, commands.Group):
                            to_append = [command.name, [c.name for c in command.commands if await check_command(c)]]
                            if to_append[1]:
                                cmd_dict[cog].append(f"`{to_append[0]}` (`{'`, `'.join(sorted(to_append[1]))}`)")
                            else:
                                cmd_dict[cog].append(f"`{to_append[0]}`")
                        else:
                            cmd_dict[cog].append(f"`{command.name}`")

            for cog in sorted([name for name in cmd_dict]):
                if cmd_dict[cog]:
                    to_send += f"__**{cog}**__  {', '.join(sorted(cmd_dict[cog]))}\n"
            await hf.safe_send(ctx, to_send)

    @commands.command(hidden=True)
    async def _check_desync_voice(self, ctx):
        config = self.bot.stats
        for guild_id in config:
            if guild_id not in config:
                continue
            if not config[guild_id]['enable']:
                continue
            guild_config = config[guild_id]
            guild = self.bot.get_guild(int(guild_id))
            try:
                voice_channels = guild.voice_channels
            except AttributeError:
                continue
            users_in_voice = []
            for channel in voice_channels:
                users_in_voice += [str(member.id) for member in channel.members]
            for user_id in guild_config['voice']['in_voice'].copy():  # all users in the database
                if user_id not in users_in_voice:  # if not in voice, remove from database
                    member = guild.get_member(int(user_id))
                    if not member:
                        del guild_config['voice']['in_voice'][user_id]
                        return
                    await ctx.invoke(self.bot.get_command("command_out_of_voice"), member)

            for user_id in users_in_voice.copy():  # all users in voice
                member = guild.get_member(int(user_id))
                vs = member.voice
                if vs:
                    if vs.deaf or vs.self_deaf or vs.afk:  # deafened or afk but in database, remove
                        await ctx.invoke(self.bot.get_command("command_out_of_voice"), member)
                    if user_id not in guild_config['voice']['in_voice']:  # in voice, not in database, add
                        if vs.channel:
                            await ctx.invoke(self.bot.get_command("command_into_voice"), member, vs)
                else:
                    await ctx.invoke(self.bot.get_command("command_out_of_voice"), member)  # in voice but no vs? remove

    @commands.command(hidden=True)
    async def _unban_users(self, ctx):
        config = self.bot.db['bans']
        for guild_id in config:
            unbanned_users = []
            guild_config = config[guild_id]
            try:
                mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][guild_id])
            except KeyError:
                mod_channel = None
            if 'timed_bans' in guild_config:
                for member_id in guild_config['timed_bans'].copy():
                    unban_time = datetime.strptime(guild_config['timed_bans'][member_id], "%Y/%m/%d %H:%M UTC")
                    if unban_time < datetime.utcnow():
                        guild = self.bot.get_guild(int(guild_id))
                        member = discord.Object(id=member_id)
                        try:
                            await guild.unban(member, reason="End of timed ban")
                            del config[guild_id]['timed_bans'][member_id]
                            unbanned_users.append(member_id)
                        except discord.NotFound:
                            pass
            if mod_channel and unbanned_users:
                text_list = []
                for i in unbanned_users:
                    user = self.bot.get_user(int(i))
                    text_list.append(f"{user.mention} ({user.name})")
                await hf.safe_send(mod_channel,
                                   embed=discord.Embed(description=f"I've unbanned {', '.join(text_list)}, as "
                                                                   f"the time for their temporary ban has expired",
                                                       color=discord.Color(int('00ffaa', 16))))

    @commands.command(hidden=True)
    async def _unmute_users(self, ctx):
        configs = ['mutes', 'voice_mutes']
        for db_name in configs:
            config = self.bot.db[db_name]
            for guild_id in config:
                unmuted_users = []
                guild_config = config[guild_id]
                try:
                    mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][guild_id])
                except KeyError:
                    mod_channel = None
                if 'timed_mutes' in guild_config:
                    for member_id in guild_config['timed_mutes'].copy():
                        unmute_time = datetime.strptime(guild_config['timed_mutes'][member_id], "%Y/%m/%d %H:%M UTC")
                        if unmute_time < datetime.utcnow():
                            if db_name == 'mutes':
                                result = await ctx.invoke(self.bot.get_command('unmute'), member_id, int(guild_id))
                            else:
                                result = await ctx.invoke(self.bot.get_command('voiceunmute'), member_id, int(guild_id))
                            if result:
                                unmuted_users.append(member_id)
                if unmuted_users and mod_channel:
                    text_list = []
                    for i in unmuted_users:
                        user = self.bot.get_user(int(i))
                        if user:
                            text_list.append(f"{user.mention} ({user.name})")
                        if not user:
                            text_list.append(f"{i}")
                    await hf.safe_send(mod_channel,
                                       embed=discord.Embed(description=f"I've unmuted {', '.join(text_list)}, as "
                                                                       f"the time for their temporary mute has expired",
                                                           color=discord.Color(int('00ffaa', 16))))

    @commands.command(hidden=True)
    async def _unselfmute_users(self, ctx):
        config = self.bot.db['selfmute']
        for guild_id in config:
            unmuted_users = []
            guild_config = config[guild_id]
            for user_id in guild_config.copy():
                try:
                    unmute_time = datetime.strptime(guild_config[user_id]['time'], "%Y/%m/%d %H:%M UTC")
                except TypeError:
                    print("there was a TypeError on _unselfmute", guild_id, user_id, guild_config[user_id]['time'])
                    del(guild_config[user_id])
                    continue
                if unmute_time < datetime.utcnow():
                    del(guild_config[user_id])
                    unmuted_users.append(user_id)
            if unmuted_users:
                for user_id in unmuted_users:
                    user = self.bot.get_user(int(user_id))
                    try:
                        await hf.safe_send(user, "Your selfmute has expired.")
                    except discord.Forbidden:
                        pass

    @commands.command(hidden=True)
    async def _delete_old_stats_days(self, ctx):
        for server_id in self.bot.stats:
            config = self.bot.stats[server_id]
            for day in config['messages'].copy():
                days_ago = (datetime.utcnow() - datetime.strptime(day, "%Y%m%d")).days
                if days_ago > 30:
                    for user_id in config['messages'][day]:
                        for channel_id in config['messages'][day][user_id]:
                            try:
                                int(channel_id)  # skip 'emoji' and 'lang' entries
                            except ValueError:
                                continue
                            if 'member_totals' not in config:
                                config['member_totals'] = {}
                            if user_id in config['member_totals']:
                                config['member_totals'][user_id] += config['messages'][day][user_id][channel_id]
                            else:
                                config['member_totals'][user_id] = config['messages'][day][user_id][channel_id]
                    del config['messages'][day]
            for day in config['voice']['total_time'].copy():
                days_ago = (datetime.utcnow() - datetime.strptime(day, "%Y%m%d")).days
                if days_ago > 30:
                    del config['voice']['total_time'][day]

    @commands.command(hidden=True)
    async def _check_lhscan(self, ctx):
        for url in self.bot.db['lhscan']:
            result = await self.lhscan_get_chapter(url)
            if type(result) == str:
                return
            try:
                chapter = f"https://loveheaven.net/{result['href']}"
            except TypeError:
                raise
            if chapter == self.bot.db['lhscan'][url]['last']:
                continue
            for user in self.bot.db['lhscan'][url]['subscribers']:
                u = self.bot.get_user(user)
                await hf.safe_send(u, f"New chapter: https://loveheaven.net/{result['href']}")
            self.bot.db['lhscan'][url]['last'] = chapter

    async def lhscan_get_chapter(self, url):
        try:
            with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        r = resp
                        data = await resp.text()
        except (aiohttp.InvalidURL, aiohttp.ClientConnectorError):
            return f'invalid_url:  Your URL was invalid ({url})'
        if r.status != 200:
            try:
                return f'html_error: Error {r.status_code}: {r.reason} ({url})'
            except AttributeError:
                return f'html_error: {r.reason} ({url})'
        soup = BeautifulSoup(data, 'html.parser')
        return soup.find('a', attrs={'class': 'chapter'})

    @commands.command()
    async def topic(self, ctx):
        """Provides a random conversation topic.
        Hint: make sure you also answer "why". Challenge your friends on their answers.
        If you disagree with their answer, talk it out."""
        topics = [line.rstrip('\n') for line in open(f"{dir_path}/cogs/utils/conversation_topics.txt", 'r',
                                                     encoding='utf8')]
        topic = choice(topics)
        while topic.startswith('#'):
            topic = choice(topics)
        await hf.safe_send(ctx, topic)

    @commands.command()
    @commands.is_owner()
    async def get_emojis(self, ctx):
        emojis = ctx.guild.emojis
        index = 1
        for emoji in emojis:
            if emoji.animated:
                continue
            with open(f"{dir_path}\emojis\{emoji.name}.png", 'wb') as im:
                await emoji.url.save(im)
            index += 1

    @commands.command()
    @commands.guild_only()
    async def inrole(self, ctx, *, role_name):
        """Type `;inrole <role_name>` to see a list of users in a role."""
        role_name = role_name.casefold()
        role = discord.utils.find(lambda i: i.name.casefold() == role_name, ctx.guild.roles)
        if not role:
            for i in ctx.guild.roles:
                if i.name.casefold().startswith(role_name):
                    role = i
                    break
        if not role:
            await hf.safe_send(ctx, "I couldn't find the role you specified.")
            return
        emb = discord.Embed(title=f"**List of members in {role.name} role - {len(role.members)}**",
                            description="",
                            color=0x00FF00)
        members = sorted(role.members, key=lambda m: m.name.casefold())
        for member in members:
            new_desc = emb.description + f"{member.name}#{member.discriminator}\n"
            if len(new_desc) < 2045:
                emb.description = new_desc
            else:
                emb.description += "..."
                break
        await hf.safe_send(ctx, embed=emb)

    @commands.group(aliases=['hc'], invoke_without_command=True)
    @commands.guild_only()
    @commands.check(lambda ctx: ctx.guild.id in [SP_SERVER_ID, CH_SERVER_ID] if ctx.guild else False)
    async def hardcore(self, ctx):
        """Adds/removes the hardcore role from you."""
        role = ctx.guild.get_role(self.bot.db['hardcore'][str(ctx.guild.id)]['role'])
        if role in ctx.author.roles:
            await ctx.author.remove_roles(role)
            try:
                await hf.safe_send(ctx, "I've removed hardcore from you.")
            except discord.Forbidden:
                pass
        else:
            await ctx.author.add_roles(role)
            await hf.safe_send(ctx, "I've added hardcore to you. You can only speak in the language you're learning.")

    @commands.command(aliases=['forcehardcore', 'forcedhardcore'])
    @commands.guild_only()
    @commands.check(lambda ctx: ctx.guild.id in [CH_SERVER_ID, CL_SERVER_ID] if ctx.guild else False)
    @commands.bot_has_permissions(manage_messages=True)
    @hf.is_admin()
    async def force_hardcore(self, ctx):
        try:
            if ctx.channel.id in self.bot.db['forcehardcore']:
                self.bot.db['forcehardcore'].remove(ctx.channel.id)
                await hf.safe_send(ctx, f"Removed {ctx.channel.name} from list of channels for forced hardcore mode")
            else:
                self.bot.db['forcehardcore'].append(ctx.channel.id)
                await hf.safe_send(ctx, f"Added {ctx.channel.name} to list of channels for forced hardcore mode")
        except KeyError:
            self.bot.db['forcehardcore'] = [ctx.channel.id]
            await hf.safe_send(ctx, f"Created forced hardcore mode config; "
                                    f"added {ctx.channel.name} to list of channels for forced hardcore mode")

    @hardcore.command()
    async def ignore(self, ctx):
        """Ignores a channel for hardcore mode."""
        if str(ctx.guild.id) in self.bot.db['hardcore']:
            config = self.bot.db['hardcore'][str(ctx.guild.id)]
        else:
            return
        try:
            if ctx.channel.id not in config['ignore']:
                config['ignore'].append(ctx.channel.id)
                await hf.safe_send(ctx, f"Added {ctx.channel.name} to list of ignored channels for hardcore mode")
            else:
                config['ignore'].remove(ctx.channel.id)
                await hf.safe_send(ctx, f"Removed {ctx.channel.name} from list of ignored channels for hardcore mode")
        except KeyError:
            config['ignore'] = [ctx.channel.id]
            await hf.safe_send(ctx, f"Added {ctx.channel.name} to list of ignored channels for hardcore mode")

    @hardcore.command()
    async def list(self, ctx):
        """Lists the channels in hardcore mode."""
        channels = []
        try:
            for channel_id in self.bot.db['hardcore'][str(ctx.guild.id)]['ignore']:
                channel = self.bot.get_channel(int(channel_id))
                if channel:
                    channels.append(channel)
                else:
                    self.bot.db['hardcore'][str(ctx.guild.id)]['ignore'].remove(channel_id)
                    await hf.safe_send(ctx, f"Removed {channel_id} from list of excepted channels (couldn't find it).")
        except KeyError:
            return
        if channels:
            string = "__List of channels excepted from hardcore__:\n#" + '\n#'.join([c.name for c in channels])
            await hf.safe_send(ctx, string)

    @commands.group(hidden=True, aliases=['lh'], invoke_without_command=True)
    async def lhscan(self, ctx, url=None):
        """A command group for subscribing to LHScan mangas."""
        await ctx.invoke(self.lhscan_add, url)

    @lhscan.command(name='add')
    async def lhscan_add(self, ctx, url):
        """Adds a URL to your subscriptions."""
        search = await self.lhscan_get_chapter(url)
        if isinstance(search, str):
            if search.startswith('html_error'):
                await hf.safe_send(ctx, search)
                return
            if search.startswith('invalid_url'):
                await hf.safe_send(ctx, search)
                return
        if not search:
            await hf.safe_send(ctx, "The search failed to find a chapter")
            return
        if url not in self.bot.db['lhscan']:
            self.bot.db['lhscan'][url] = {'last': f"https://loveheaven.net/{search['href']}",
                                          'subscribers': [ctx.author.id]}
        else:
            if ctx.author.id not in self.bot.db['lhscan'][url]['subscribers']:
                self.bot.db['lhscan'][url]['subscribers'].append(ctx.author.id)
            else:
                await hf.safe_send(ctx, "You're already subscribed to this manga.")
                return
        await hf.safe_send(ctx, f"The latest chapter is: https://loveheaven.net/{search['href']}\n\n"
                                f"I'll tell you next time a chapter is uploaded.")

    @lhscan.command(name='remove')
    async def lhscan_remove(self, ctx, url):
        """Unsubscribes you from a manga. Input the URL: `;lh remove <url>`."""
        if url not in self.bot.db['lhscan']:
            await hf.safe_send(ctx, "No one is subscribed to that manga. Check your URL.")
            return
        else:
            if ctx.author.id in self.bot.db['lhscan'][url]['subscribers']:
                self.bot.db['lhscan'][url]['subscribers'].remove(ctx.author.id)
                await hf.safe_send(ctx, "You've been unsubscribed from that manga.")
                if len(self.bot.db['lhscan'][url]['subscribers']) == 0:
                    del self.bot.db['lhscan'][url]
            else:
                await hf.safe_send("You're not subscribed to that manga.")
                return

    @lhscan.command(name='list')
    async def lhscan_list(self, ctx):
        """Lists the manga you subscribed to."""
        subscriptions = []
        for url in self.bot.db['lhscan']:
            if ctx.author.id in self.bot.db['lhscan'][url]['subscribers']:
                subscriptions.append(f"<{url}>")
        subs_list = '\n'.join(subscriptions)
        if subscriptions:
            await hf.safe_send(ctx, f"The list of mangas you're subscribed to:\n{subs_list}")
        else:
            await hf.safe_send(ctx, "You're not subscribed to any mangas.")

    @commands.command(aliases=['git'])
    @commands.bot_has_permissions(send_messages=True)
    async def github(self, ctx):
        """Gives my github page"""
        await hf.safe_send(ctx, 'https://github.com/ryry013/Rai')

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def punch(self, ctx, user: discord.Member = None):
        """A punch command I made as a test"""
        if not user:
            user = ctx.author
        await hf.safe_send(ctx, "ONE PUNCH! And " + user.mention + " is out! ლ(ಠ益ಠლ)")

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def ping(self, ctx, x=4):
        """sends back 'hello'"""
        await hf.safe_send(ctx, str(round(self.bot.latency, x)) + 's')

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def invite(self, ctx):
        """Gives an invite to bring this bot to your server"""
        modchat = self.bot.get_guild(MODCHAT_SERVER_ID)
        if modchat:
            members = modchat.members
        else:
            members = []
        if ctx.author in members or ctx.author.id == self.bot.owner_id:
            await hf.safe_send(ctx, discord.utils.oauth_url(self.bot.user.id,
                                                            permissions=discord.Permissions(permissions=27776)))
        else:
            await hf.safe_send(ctx, "Sorry, the bot is currently not public. "
                                    "The bot owner can send you an invite link.")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user: discord.Member):
        """removes people from the waiting list for ;report if they react with '🚫' to a certain message"""
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
                        await hf.safe_send(mod_channel, msg_to_mod_channel)
                        return
                await user.send("You aren't on the waiting list.")

        if str(reaction.emoji) in '🗑❌':
            if reaction.message.author == self.bot.user and \
                    (user.id == self.bot.owner_id or reaction.message.channel.permissions_for(user).manage_messages):
                await reaction.message.delete()

        if user.bot:
            return
        if not hasattr(user, 'guild'):
            return
        if str(user.guild.id) not in self.bot.stats:
            return
        if self.bot.stats[str(user.guild.id)]['enable']:
            try:
                emoji = reaction.emoji.name
            except AttributeError:
                emoji = reaction.emoji
            config = self.bot.stats[str(user.guild.id)]
            date_str = datetime.utcnow().strftime("%Y%m%d")
            if date_str not in config['messages']:
                config['messages'][date_str] = {}
            today = config['messages'][date_str]
            today.setdefault(str(user.id), {})
            today[str(user.id)].setdefault('emoji', {})
            today[str(user.id)]['emoji'][emoji] = today[str(user.id)]['emoji'].get(emoji, 0) + 1

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
                    del(self.bot.db['reactionroles'][guild_id][message_id][emoji_str])
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
                if user_id not in config['votes2']:
                    return
                if str(payload.user_id) in config['residency']:
                    voting_guild_id = config['residency'][str(payload.user_id)]
                    if voting_guild_id not in config['votes2'][user_id]['votes']:
                        if message.embeds[0].color != discord.Color(int('ff0000', 16)):
                            await ctx.invoke(self.blacklist_add, args=user_id)
                else:
                    try:
                        await hf.safe_send(ctx.author, "Please claim residency on a server first with "
                                                       "`;global_blacklist residency`")
                    except discord.Forbidden:
                        await hf.safe_send(ctx, "Please claim residency on a server first with `;global_blacklist "
                                                "residency`.")
                    return

            elif payload.channel_id == BANS_CHANNEL_ID:
                channel = self.bot.get_channel(BANS_CHANNEL_ID)
                message = await channel.fetch_message(payload.message_id)
                ctx = await self.bot.get_context(message)
                ctx.author = self.bot.get_user(payload.user_id)
                ctx.reacted_user_id = payload.user_id
                user_id = re.search('^.*\n\((\d{17,22})\)', message.embeds[0].description).group(1)
                try:
                    reason = re.search('__Reason__: (.*)$', message.embeds[0].description, flags=re.S).group(1)
                except AttributeError as e:
                    await hf.safe_send(channel, "I couldn't find the reason attached to the ban log for addition to "
                                                "the GBL.")
                    return
                config = self.bot.db['global_blacklist']
                if str(payload.user_id) in config['residency']:
                    if user_id not in config['blacklist'] and str(user_id) not in config['votes2']:
                        await ctx.invoke(self.blacklist_add,
                                         args=f"{user_id} {reason}\n[Ban Entry]({message.jump_url})")
                else:
                    await hf.safe_send(ctx.author, "Please claim residency on a server first with `;gbl residency`")
                    return

        if payload.emoji.name == '✅':  # captcha
            if str(payload.guild_id) in self.bot.db['captcha']:
                config = self.bot.db['captcha'][str(payload.guild_id)]
                if config['enable']:
                    guild = self.bot.get_guild(payload.guild_id)
                    role = guild.get_role(config['role'])
                    if not 'message' in config:
                        return
                    if payload.message_id == config['message']:
                        try:
                            await guild.get_member(payload.user_id).add_roles(role)
                            return
                        except discord.errors.Forbidden:
                            await self.bot.get_user(202995638860906496).send(
                                'on_raw_reaction_add: Lacking `Manage Roles` permission'
                                f' <#{payload.guild_id}>')

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
            await user.add_roles(assignable_role)

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
            except discord.errors.Forbidden:
                self.bot.get_user(202995638860906496).send(
                    'on_raw_reaction_add: Lacking `Manage Roles` permission'
                    f'<#{payload.guild_id}>')
            except AttributeError:
                return

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id:
            return
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
            await user.remove_roles(assignable_role)

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
            except discord.errors.Forbidden:
                self.bot.get_user(202995638860906496).send(
                    'on_raw_reaction_remove: Lacking `Manage Roles` permission'
                    f'<#{payload.guild_id}>')
            except AttributeError:
                return

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    async def pencil(self, ctx):
        """Adds a pencil to your name. Rai cannot edit the nickname of someone above it on the role list"""
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        try:
            await ctx.author.edit(nick=ctx.author.display_name + '📝')
            msg = await hf.safe_send(ctx,
                                     "I've added 📝 to your name.  This means you wish to be corrected in your sentences")
            asyncio.sleep(7)
            await msg.delete()
        except discord.errors.Forbidden:
            msg = await hf.safe_send(ctx, "I lack the permissions to change your nickname")
            asyncio.sleep(7)
            await msg.delete()
        except discord.errors.HTTPException:
            try:
                await ctx.message.add_reaction('💢')
            except discord.NotFound:
                pass

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    async def eraser(self, ctx):
        """Erases the pencil from `;pencil`. Rai cannot edit the nicknames of users above it on the role list."""
        try:
            await ctx.author.edit(nick=ctx.author.display_name[:-1])
            await ctx.message.add_reaction('◀')
        except discord.errors.Forbidden:
            await hf.safe_send(ctx, "I lack the permissions to change your nickname")

    @commands.command(aliases=['ryry'])
    @commands.bot_has_permissions(send_messages=True)
    async def ryan(self, ctx):
        """Posts a link to the help docs server for my bot"""
        await hf.safe_send(ctx, "You can find some shitty docs for how to use my bot here: "
                                "https://github.com/ryry013/Rai/blob/master/README.md \n"
                                "You can ask questions and find some further details here: https://discord.gg/7k5MMpr")

    @commands.command(aliases=[';p', ';s', ';play', ';skip', '_;', '-;', ')', '__;', '___;', ';leave', ';join',
                               ';l', ';q', ';queue', ';pause', ';volume', ';1', ';vol', ';np', ';list'], hidden=True)
    async def ignore_commands_list(self, ctx):
        pass

    @commands.command(aliases=['cl', 'checklanguage'])
    @commands.bot_has_permissions(send_messages=True)
    @commands.is_owner()
    # @commands.cooldown(1, 15, type=commands.BucketType.user)
    async def check_language(self, ctx, *, msg: str):
        """Shows what's happening behind the scenes for hardcore mode.  Will try to detect the language that your\
        message was typed in, and display the results.  Note that this is non-deterministic code, which means\
        repeated results of the same exact message might give different results every time.

        Usage: `;cl <text you wish to check>`"""
        stripped_msg = hf.rem_emoji_url(msg)
        if not stripped_msg:
            stripped_msg = ' '
        try:
            lang_result = await hf.detect_language(stripped_msg)
        except textblob.exceptions.TranslatorError:
            lang_result = "There was an error detecting the languages"
        except HTTPError:
            await hf.safe_send(ctx, "You're being rate limited maybe")
            return
        str = f"Your message:```{msg}```" \
              f"The message I see (no emojis or urls): ```{stripped_msg}```" \
              f"The language I detect: ```{lang_result}```"

        await hf.safe_send(ctx, str)

    @commands.command(aliases=['server', 'info', 'sinfo'])
    @commands.cooldown(1, 30, type=commands.BucketType.channel)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def serverinfo(self, ctx):
        """Shows info about this server"""
        guild = ctx.guild
        if not guild:
            await hf.safe_send(ctx,
                               f"{ctx.channel}.  Is that what you were looking for?  (Why are you trying to call info "
                               f"on 'this server' in a DM?)")
            return
        em = discord.Embed(title=f"**{guild.name}**",
                           description=f"**ID:** {guild.id}",
                           timestamp=guild.created_at,
                           colour=discord.Colour(0x877AD6))
        em.set_thumbnail(url=guild.icon_url)
        em.add_field(name="Region", value=guild.region)
        em.add_field(name="Channels", value=f"{len(guild.text_channels)} text / {len(guild.voice_channels)} voice")
        em.add_field(name="Verification Level", value=guild.verification_level)
        em.add_field(name="Guild created on (UTC)", value=guild.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        em.add_field(name="Number of members", value=ctx.guild.member_count)

        if guild.afk_channel:
            em.add_field(name="Voice AFK Timeout",
                         value=f"{guild.afk_timeout//60} mins → {guild.afk_channel.mention}")

        if guild.explicit_content_filter != "disabled":
            em.add_field(name="Explicit Content Filter", value=guild.explicit_content_filter)

        if guild.id not in [JP_SERVER_ID, SP_SERVER_ID]:
            em.add_field(name="Server owner", value=f"{guild.owner.name}#{guild.owner.discriminator}")

        # count top 6 member roles
        if len(guild.members) < 30000:
            role_count = Counter(role.name for member in guild.members
                                 for role in member.roles if not role.is_default())

            top_six_roles = '\n'.join(f"{role}: {count}" for role, count in role_count.most_common(6))
            em.add_field(name=f"Top 6 roles (out of {len(guild.roles)})", value=top_six_roles)
        else:
            em.add_field(name="Roles", value=str(len(guild.roles)))

        how_long_ago = datetime.utcnow() - guild.created_at
        days = how_long_ago.days
        years = days // 365
        bef_str = ''
        if years:
            bef_str = f"{years} years, "
        months = (days - 365 * years) // 30.416666666666668
        if months:
            bef_str += f"{int(months)} months, "
        days = days - 365 * years - round(30.416666666666668 * months)
        bef_str += f"{days} days"
        em.set_footer(text=f"Guild created {bef_str} ago on:")
        if len(em.fields) % 2 == 0:
            two = em.fields[-2]
            em.add_field(name=two.name, value=two.value)
            em.remove_field(-3)
        try:
            await hf.safe_send(ctx, embed=em)
        except discord.Forbidden:
            pass

    @commands.group(invoke_without_command=True, aliases=['gb', 'gbl', 'blacklist'], hidden=True)
    @blacklist_check()
    async def global_blacklist(self, ctx):
        """A global blacklist for banning spammers, requires three votes from mods from three different servers"""
        config = hf.database_toggle(ctx, self.bot.db['global_blacklist'])
        if config['enable']:
            if not ctx.me.guild_permissions.ban_members:
                await hf.safe_send(ctx,
                                   'I lack the permission to ban members.  Please fix that before enabling this module')
                hf.database_toggle(ctx, self.bot.db['global_blacklist'])
                return
            await hf.safe_send(ctx,
                               "Enabled the global blacklist on this server.  Anyone voted into the blacklist by three "
                               "mods and joining your server will be automatically banned.  "
                               "Type `;global_blacklist residency` to claim your residency on a server.")
        else:
            await hf.safe_send(ctx, "Disabled the global blacklist.  "
                                    "Anyone on the blacklist will be able to join  your server.")

    @global_blacklist.command(name='reason', aliases=['edit'])
    @blacklist_check()
    async def blacklist_reason(self, ctx, entry_message_id, *, reason):
        """Add a reason to a blacklist entry: `;gbl reason <message_id> <reason>`"""
        blacklist_channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
        try:
            entry_message = await blacklist_channel.fetch_message(int(entry_message_id))
        except discord.NotFound:
            await hf.safe_send(ctx, "I couldn't find the message you were trying to edit. Make sure you link to "
                                    f"the message ID in the {blacklist_channel.mention}.")
            return
        emb = entry_message.embeds[0]
        old_reason = emb.fields[1].value
        emb.set_field_at(1, name=emb.fields[1].name, value=reason)
        await entry_message.edit(embed=emb)
        await hf.safe_send(ctx, f"Changed reason of {entry_message.jump_url}\nOld reason: ```{old_reason}```")

    @global_blacklist.command(name='remove', alias=['delete'])
    @blacklist_check()
    async def blacklist_remove(self, ctx, entry_message_id):
        """Removes a voting entry from the blacklist channel."""
        blacklist_channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
        try:
            entry_message = await blacklist_channel.fetch_message(int(entry_message_id))
        except discord.NotFound:
            await hf.safe_send(ctx,
                               f"Message not found.  If you inputted the ID of a user, please input the message ID of "
                               f"the entry in the blacklist instead.")
            return
        emb = entry_message.embeds[0]
        target_id = emb.title.split(' ')[0]

        try:
            self.bot.db['global_blacklist']['blacklist'].remove(str(target_id))
        except ValueError:
            pass
        except KeyError:
            await hf.safe_send(ctx, "This user is not currently in the GBL.")

        try:
            del self.bot.db['global_blacklist']['votes2'][str(target_id)]
        except ValueError:
            pass
        except KeyError:
            await hf.safe_send(ctx, "This user is not currently under consideration for votes.")

        await entry_message.delete()

        emb.color = discord.Color(int('ff00', 16))
        emb.set_field_at(0, name="Entry removed by", value=f"{ctx.author.name}#{ctx.author.discriminator}")
        await blacklist_channel.send(embed=emb)

        await ctx.message.add_reaction('✅')

    @global_blacklist.command()
    @blacklist_check()
    async def residency(self, ctx):
        """Claims your residency on a server"""
        config = self.bot.db['global_blacklist']['residency']
        if ctx.guild.id == MODCHAT_SERVER_ID:
            await hf.safe_send(ctx, "You can't claim residency here. Please do this command on the server you mod.")
            return

        if str(ctx.author.id) in config:
            server = self.bot.get_guild(config[str(ctx.author.id)])
            await hf.safe_send(ctx,
                               f"You've already claimed residency on {server.name}.  You can not change this without "
                               f"talking to Ryan.")
            return

        await hf.safe_send(ctx,
                           "For the purpose of maintaining fairness in a ban, you're about to claim your mod residency to "
                           f"`{ctx.guild.name}`.  This can not be changed without talking to Ryan.  "
                           f"Do you wish to continue?\n\nType `yes` or `no` (case insensitive).")
        msg = await self.bot.wait_for('message',
                                      timeout=25.0,
                                      check=lambda m: m.author == ctx.author and m.channel == ctx.channel)

        if msg.content.casefold() == 'yes':  # register
            config[str(ctx.author.id)] = ctx.guild.id
            await hf.safe_send(ctx,
                               f"Registered your residency to `{ctx.guild.name}`.  Type `;global_blacklist add <ID>` to "
                               f"vote on a user for the blacklist")

        elif msg.content.casefold() == 'no':  # cancel
            await hf.safe_send(ctx, "Understood.  Exiting module.")

        else:  # invalid response
            await hf.safe_send(ctx, "Invalid response")

    @blacklist_check()
    @global_blacklist.command(aliases=['vote'], name="add")
    async def blacklist_add(self, ctx, *, args):
        """Add people to the blacklist"""
        args = args.replace('\n', ' ').split()
        list_of_ids = []
        reason = "None"
        for arg_index in range(len(args)):
            if re.search('\d{17,22}', args[arg_index]):
                list_of_ids.append(str(args[arg_index]))
            else:
                reason = ' '.join(args[arg_index:])
                break
        channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
        config = self.bot.db['global_blacklist']
        if not list_of_ids:
            await hf.safe_send(ctx.author, f"No valid ID found in command")
            return
        for user in list_of_ids:
            user_obj = self.bot.get_user(user)
            if not user_obj:
                try:
                    user = user.replace('<@!', '').replace('<@', '').replace('>', '')
                    user_obj = await self.bot.fetch_user(user)
                except (discord.NotFound, discord.HTTPException):
                    user_obj = None

            async def post_vote_notification(target_user, reason):
                await ctx.message.add_reaction('✅')
                if not target_user:
                    target_user = ''
                emb = discord.Embed(title=f"{user} {target_user} (1 vote)", color=discord.Color(int('ffff00', 16)))
                emb.add_field(name='Voters', value=ctx.author.name)
                emb.add_field(name='Reason', value=reason)
                msg = await hf.safe_send(channel, embed=emb)
                await msg.add_reaction('⬆')
                return msg

            try:  # the guild ID that the person trying to add a vote belongs to
                user_residency = config['residency'][str(ctx.author.id)]  # a guild id
            except KeyError:
                await hf.safe_send(ctx.author,
                                   "Please claim residency on a server first with `;global_blacklist residency`")
                return

            if user in config['blacklist']:  # already blacklisted
                await hf.safe_send(ctx, f"{user} is already on the blacklist")
                continue

            if user not in config['votes2']:  # 0 votes
                config['votes2'][user] = {'votes': [user_residency], 'message': 0}
                msg = await post_vote_notification(user_obj, reason)
                config['votes2'][user]['message'] = msg.id
                continue

            if user in config['votes2']:  # 1, 2, or 3 votes
                list_of_votes = config['votes2'][user]['votes']
                if user_residency in list_of_votes:
                    await hf.safe_send(ctx.author, f"{user} - Someone from your server already voted")
                    continue

                message = await channel.fetch_message(config['votes2'][user]['message'])
                emb = message.embeds[0]
                title_str = emb.title
                result = re.search('(\((.*)\))? \((.) votes?\)', title_str)
                # target_username = result.group(2)
                num_of_votes = result.group(3)
                emb.title = re.sub('(.) vote', f'{int(num_of_votes)+1} vote', emb.title)
                if num_of_votes in '1':  # 1-->2
                    emb.title = emb.title.replace('vote', 'votes')
                if num_of_votes in '12':  # 1-->2 or 2-->3
                    config['votes2'][user]['votes'].append(user_residency)
                if num_of_votes == '3':  # 2-->3
                    emb.color = discord.Color(int('ff0000', 16))
                    del config['votes2'][user]
                    config['blacklist'].append(int(user))
                emb.set_field_at(0, name=emb.fields[0].name, value=emb.fields[0].value + f', {ctx.author.name}')
                await message.edit(embed=emb)

    @global_blacklist.command(name='list')
    @blacklist_check()
    async def blacklist_list(self, ctx):
        """Lists the users with residencies on each server"""
        users_str = ''
        users_dict = {}
        config = self.bot.db['global_blacklist']['residency']
        for user_id in config:
            user = self.bot.get_user(int(user_id))
            guild = self.bot.get_guild(config[user_id])
            if guild in users_dict:
                users_dict[guild].append(user)
            else:
                users_dict[guild] = [user]
        for guild in users_dict:
            try:
                users_str += f"**{guild.name}:** {', '.join([user.name for user in users_dict[guild]])}\n"
            except AttributeError:
                pass
        emb = discord.Embed(title="Global blacklist residencies", description="Listed below is a breakdown of who "
                                                                              "holds residencies in which servers.\n\n")
        emb.description += users_str
        await hf.safe_send(ctx, embed=emb)

    @global_blacklist.command(name="sub")
    @blacklist_check()
    async def blacklist_bansub(self, ctx):
        """Subscribes yourself to pings for your server"""
        # a list of which server IDs a user is subscribed to
        guild = self.bot.get_guild(MODCHAT_SERVER_ID)
        subbed_roles: list = self.bot.db['bansub']['user_to_role'].setdefault(str(ctx.author.id), [])
        user_role_ids = [role.id for role in ctx.author.roles if str(role.color) == "#206694"]  # only want blue roles
        selection_dictionary = {}  # for later when the user selects a role to toggle
        guild_id_to_role: dict = self.bot.db['bansub']['guild_to_role']  # links a guild ID to the corresponding role
        role_to_guild_id = {guild_id_to_role[a]: a for a in guild_id_to_role}  # reverses the dictionary

        # ########################## DISPLAYING CURRENT SUBSCRIPTIONS ###########################

        counter = 1
        if not subbed_roles:
            msg = "You are currently not subscribed to pings for any servers.\n"
        else:
            msg = "You are currently subscribed to pings for the following servers: \n"
            for role_id in subbed_roles:  # a list of role IDs corresponding to server roles
                if role_id in user_role_ids:
                    user_role_ids.remove(role_id)
                role: discord.Role = guild.get_role(role_id)
                msg += f"    {counter}) {role.name}\n"
                selection_dictionary[counter] = role.id
                counter += 1

        msg += "\nHere are the roles to which you're not subscribed:\n"
        for role_id in user_role_ids:  # remaining here should only be the unsubscribed roles on the user's profile
            role: discord.Role = guild.get_role(role_id)
            msg += f"    {counter}) {role.name}\n"
            selection_dictionary[counter] = role.id
            counter += 1

        # ########################## ASK FOR WHICH ROLE TO TOGGLE ########################

        msg += f"\nTo toggle the subscription for a role, please input now the number for that role."
        await hf.safe_send(ctx, msg)
        try:
            resp = await self.bot.wait_for("message", timeout=20.0,
                                           check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
        except asyncio.TimeoutError:
            await hf.safe_send(ctx, "Module timed out.")
            return
        try:
            resp = int(resp.content)
        except ValueError:
            await hf.safe_send(ctx, "Sorry, I didn't understand your response. Please input only a single number.")
            return
        if resp not in selection_dictionary:
            await hf.safe_send(ctx, "Sorry, I didn't understand your response. Please input only a single number.")
            return

        # ################################ TOGGLE THE ROLE #################################

        role_selection: int = selection_dictionary[resp]
        if role_selection in subbed_roles:
            subbed_roles.remove(role_selection)
            await hf.safe_send(ctx, "I've unsubcribed you from that role.")
        else:
            #      ####### Possibly match a role to a guild ########
            if role_selection not in role_to_guild_id:
                await hf.safe_send(ctx, "Before we continue, you need to tell me which server corresponds to that role."
                                        " We'll only need to do this once for your server. Please tell me either the "
                                        "server ID of that server, or the exact name of it.")
                try:
                    resp = await self.bot.wait_for("message", timeout=20.0,
                                                   check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                    resp = resp.content
                except asyncio.TimeoutError:
                    await hf.safe_send(ctx, "Module timed out.")
                    return

                if re.search('^\d{17,22}$', resp):  # user specifies a guild ID
                    guild = self.bot.get_guild(int(resp))
                    if not guild:
                        await hf.safe_send(ctx, "I couldn't find the guild corresponding to that ID. "
                                                "Please start over.")
                        return
                else:  # user probably specified a guild name
                    guild = discord.utils.find(lambda g: g.name == resp, self.bot.guilds)
                    if not guild:
                        await hf.safe_send(ctx, "I couldn't find the guild corresponding to that guild name. "
                                                "Please start over.")
                        return
                guild_id_to_role[str(guild.id)] = role_selection

            #     ####### Add the role #######
            subbed_roles.append(role_selection)
            await hf.safe_send(ctx, "I've added you to the subscriptions for that role. I'll ping you for that server.")

    @commands.command()
    @commands.guild_only()
    async def lsar(self, ctx, page_num=1):
        """Lists self-assignable roles (type `;lsar <page number>` to view other pages, example: `;lsar 2`)."""
        if not ctx.guild:
            return
        roles_list = []
        config = self.bot.db['SAR'].setdefault(str(ctx.guild.id), {'0': []})
        for group in config.copy():
            if len(config[group]) == 0:
                del config[group]
        groups = sorted([int(key) for key in config])
        groups = [str(i) for i in groups]
        for group in groups:
            for role in config[group]:
                roles_list.append((group, role))
        role_list_str = f"**There are {len(roles_list)} self-assignable roles**\n"
        if len(roles_list) == 1:
            role_list_str = role_list_str.replace('roles', 'role').replace('are', 'is')
        current_group = ''
        try:
            current_group = roles_list[20 * (page_num - 1)][0]
            role_list_str += f"⟪Group {current_group}⟫\n"
        except IndexError:
            pass

        for role_tuple in roles_list[20 * (page_num - 1):20 * page_num]:
            if current_group != role_tuple[0]:
                current_group = groups[groups.index(current_group) + 1]
                role_list_str += f"\n⟪Group {current_group}⟫\n"

            role = ctx.guild.get_role(role_tuple[1])
            if not role:
                await ctx.send(f"Couldn't find role with ID {role_tuple[1]}. Removing from self-assignable roles.")
                config[current_group].remove(role_tuple[1])
                continue
            role_list_str += f"⠀{role.name}\n"

        emb = discord.Embed(description=role_list_str, color=discord.Color(int('00ff00', 16)))
        num_of_pages = (len(roles_list)//20)+1
        footer_text = f"{page_num} / {num_of_pages}"
        if page_num <= num_of_pages:
            footer_text += f" ・ (view the next page: ;lsar {page_num + 1})"
        emb.set_footer(text=footer_text)
        await hf.safe_send(ctx, embed=emb)

    @commands.command(hidden=True)
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    async def i(self, ctx, *, role_name):
        if role_name[:2] == 'am':
            await ctx.invoke(self.iam, role_name=role_name[3:])

    @commands.command(aliases=['im'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    @commands.guild_only()
    async def iam(self, ctx, *, role_name):
        """Command used to self-assign a role. Type `;iam <role name>`. Type `;lsar` to see the list of roles.

        Example: `;iam English`"""
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['SAR']:
            return
        config = self.bot.db['SAR'][str(ctx.guild.id)]
        desired_role = discord.utils.find(lambda role: role.name.casefold() == role_name.casefold(), ctx.guild.roles)
        if not desired_role:
            await hf.safe_send(ctx,
                               embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** No role found"))
            return

        if desired_role in ctx.author.roles:
            await hf.safe_send(ctx, embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** "
                                                       f"You already have that role"))
            return

        for group in config:
            for role_id in config[group]:
                if desired_role.id == role_id:
                    await ctx.author.add_roles(desired_role)
                    await hf.safe_send(ctx, embed=hf.green_embed(
                        f"**{ctx.author.name}#{ctx.author.discriminator}** You now have"
                        f" the **{desired_role.name}** role."))
                    return

    @commands.command(aliases=['iamn'])
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    async def iamnot(self, ctx, *, role_name):
        """Command used to remove a self-assigned role"""
        if str(ctx.guild.id) not in self.bot.db['SAR']:
            return
        config = self.bot.db['SAR'][str(ctx.guild.id)]

        desired_role = discord.utils.find(lambda role: role.name.casefold() == role_name.casefold(), ctx.guild.roles)
        if not desired_role:
            await hf.safe_send(ctx,
                               embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** No role found"))
            return

        if desired_role not in ctx.author.roles:
            await hf.safe_send(ctx, embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** "
                                                       f"You don't have that role"))
            return

        for group in config:
            for role_id in config[group]:
                if desired_role.id == role_id:
                    await ctx.author.remove_roles(desired_role)
                    await hf.safe_send(ctx,
                                       embed=hf.green_embed(
                                           f"**{ctx.author.name}#{ctx.author.discriminator}** You no longer have "
                                           f"the **{desired_role.name}** role."))
                    return

        await hf.safe_send(ctx, embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** That role is not "
                                                   f"self-assignable."))

    @commands.command(aliases=['vmute', 'vm'])
    @hf.is_voicemod()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    async def voicemute(self, ctx, time, member=None, *, reason=None):
        """Mutes a user.  Syntax: `;voicemute <time> <member>`.
        Example: `;voicemute 1d2h Abelian`"""
        async def set_channel_overrides(role):
            failed_channels = []
            for channel in ctx.guild.voice_channels:
                if role not in channel.overwrites:
                    try:
                        await channel.set_permissions(role, speak=False)
                    except discord.Forbidden:
                        failed_channels.append(channel.name)
            return failed_channels

        if str(ctx.guild.id) not in self.bot.db['voice_mutes']:
            await hf.safe_send(ctx, "Doing first-time setup of mute module.  I will create a `rai-mute` role, "
                                    "add then a permission override for it to every channel to prevent communication")
            role = await ctx.guild.create_role(name='rai-voice-mute', reason="For use with ;voicemute command")
            config = self.bot.db['voice_mutes'][str(ctx.guild.id)] = {'role': role.id, 'timed_mutes': {}}
            failed_channels = await set_channel_overrides(role)
            if failed_channels:
                await hf.safe_send(ctx,
                                   f"Couldn't add the role permission to {' ,'.join(failed_channels)}.  If a muted "
                                   f"member joins this (these) channel(s), they'll be able to speak.")
        else:
            config = self.bot.db['voice_mutes'][str(ctx.guild.id)]
            role = ctx.guild.get_role(config['role'])
            await set_channel_overrides(role)

        time_string, length = hf.parse_time(str(time))
        if not time_string:  # indefinite mute
            if not reason:
                reason = ''
            if member:
                reason = f"{member} {reason}"
            member = time
            time = None

        silent = False
        if reason:
            if '-s' in reason or '-n' in reason:
                if ctx.guild.id == JP_SERVER_ID:
                    await hf.safe_send(ctx, "Maybe you meant to use Ciri?")
                reason = reason.replace(' -s', '').replace('-s ', '').replace('-s', '')
                silent = True

        re_result = re.search('^<?@?!?([0-9]{17,22})>?$', member)
        if re_result:
            id = int(re_result.group(1))
            target = ctx.guild.get_member(id)
        else:
            target = None
        if not target:
            await hf.safe_send(ctx, "I could not find the user.  For warns and mutes, please use either an ID or "
                                    "a mention to the user (this is to prevent mistaking people).")
            return

        if role in target.roles:
            await hf.safe_send(ctx, "This user is already muted (already has the mute role)")
            return
        await target.add_roles(role, reason=f"Muted by {ctx.author.name} in {ctx.channel.name}")

        if target.voice:  # if they're in a channel, move them out then in to trigger the mute
            voice_state = target.voice
            try:
                if ctx.guild.afk_channel:
                    await target.move_to(ctx.guild.afk_channel)
                    await target.move_to(voice_state.channel)
                else:
                    for channel in ctx.guild.voice_channels:
                        if not channel.members:
                            await target.move_to(channel)
                            await target.move_to(voice_state.channel)
                            break
            except discord.Forbidden:
                pass

        if time_string:
            config['timed_mutes'][str(target.id)] = time_string

        notif_text = f"**{target.name}#{target.discriminator}** has been **voice muted** from voice chat."
        if time_string:
            notif_text = notif_text[:-1] + f" for {time}."
        if reason:
            notif_text += f"\nReason: {reason}"
        emb = hf.red_embed(notif_text)
        if time_string:
            emb.description = emb.description + f" for {length[0]}d{length[1]}h."
        if silent:
            emb.description += " (The user was not notified of this)"
        await hf.safe_send(ctx, embed=emb)

        modlog_config = hf.add_to_modlog(ctx, target, 'Mute', reason, silent, time)
        modlog_channel = self.bot.get_channel(modlog_config['channel'])

        emb = hf.red_embed(f"You have been voice muted on {ctx.guild.name} server")
        emb.color = discord.Color(int('ffff00', 16))  # embed
        if time_string:
            emb.add_field(name="Length", value=f"{time} (will be unmuted on {time_string})", inline=False)
        else:
            emb.add_field(name="Length", value="Indefinite", inline=False)
        if reason:
            emb.add_field(name="Reason", value=reason)
        if not silent:
            try:
                await target.send(embed=emb)
            except discord.Forbidden:
                await hf.safe_send(ctx, "This user has DMs disabled so I couldn't send the notification.  Canceling...")
                return

        emb.insert_field_at(0, name="User", value=f"{target.name} ({target.id})", inline=False)
        emb.description = "Voice Mute"
        emb.add_field(name="Jump URL", value=ctx.message.jump_url, inline=False)
        emb.set_footer(text=f"Voice muted by {ctx.author.name} ({ctx.author.id})")
        try:
            if modlog_channel:
                await hf.safe_send(modlog_channel, embed=emb)
        except AttributeError:
            await hf.safe_send(ctx, embed=emb)

    @commands.command(aliases=['vum', 'vunmute'])
    @hf.is_voicemod()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    async def voiceunmute(self, ctx, target_in, guild=None):
        """Unmutes a user"""
        if not guild:
            guild = ctx.guild
            target: discord.Member = await hf.member_converter(ctx, target_in)
        else:
            guild = self.bot.get_guild(int(guild))
            target: discord.Member = guild.get_member(int(target_in))
        try:
            config = self.bot.db['voice_mutes'][str(guild.id)]
        except IndexError:
            return
        role = guild.get_role(config['role'])

        failed = False
        if target:
            target_id = target.id
            try:
                await target.remove_roles(role)
                failed = False
            except discord.HTTPException:
                pass

        else:
            if ctx.author == ctx.bot.user:
                target_id = target_in
            else:
                return

        if str(target_id) in config['timed_mutes']:
            del config['timed_mutes'][str(target_id)]

        if ctx.author != ctx.bot.user:
            emb = discord.Embed(description=f"**{target.name}#{target.discriminator}** has been unmuted.",
                                color=discord.Color(int('00ffaa', 16)))
            await hf.safe_send(ctx, embed=emb)

        if not failed:
            return True

    @commands.command(aliases=['selfmute'])
    @commands.guild_only()
    async def self_mute(self, ctx, time=None):
        """Irreversible mutes yourself for a certain amount of hours. Use like `;selfmute <number of hours>`.

        For example: `;selfmute 3` to mute yourself for three hours. This was made half for anti-procrastination, half\
        to end people asking for it."""
        try:
            time = int(time)
        except (ValueError, TypeError):
            await hf.safe_send(ctx, "Please give an integer number.")
            return
        if time:
            try:
                if self.bot.db['selfmute'][str(ctx.guild.id)][str(ctx.author.id)]['enable']:
                    await hf.safe_send(ctx, "You're already muted. No saving you now.")
                    return
            except KeyError:
                pass
        else:
            await hf.safe_send(ctx, "You need to put something! Please give an integer number.")
            return

        if time > 24:
            time = 24
            await hf.safe_send(ctx, "Maxing out at 24h")

        await hf.safe_send(ctx, f"You are about to irreversibly mute yourself for {time} hours. "
                                f"Is this really what you want to do? The mods of this server CANNOT undo "
                                f"this.\nType 'Yes' to confirm.")

        try:
            msg = await self.bot.wait_for('message',
                                          timeout=15,
                                          check=lambda m: m.author == ctx.author and m.channel == ctx.channel)

            if msg.content.casefold() == 'yes':  # confirm
                config = self.bot.db['selfmute'].setdefault(str(ctx.guild.id), {})
                time_string, length = hf.parse_time(f"{time}h")
                config[str(ctx.author.id)] = {'enable': True, 'time': time_string}
                await hf.safe_send(ctx, f"Muted {ctx.author.display_name} for {time} hours. This is irreversible. "
                                        f"The mods have nothing to do with this so no matter what you ask them, "
                                        f"they can't help you. You alone chose to do this.")

        except asyncio.TimeoutError:
            await hf.safe_send(ctx, "Canceling.")
            return

    @commands.command(hidden=True, aliases=['pingmods'])
    @commands.check(lambda ctx: ctx.guild.id in [SP_SERVER_ID, RY_SERVER_ID] if ctx.guild else False)
    async def pingstaff(self, ctx):
        """Puts a `@here` ping into the staff channel with a link to your message"""
        channel = self.bot.get_channel(self.bot.db['mod_channel'][str(ctx.guild.id)])
        desc_text = f"Staff has been pinged in {ctx.channel.mention} [here]({ctx.message.jump_url}) by " \
                    f"{ctx.author.mention}."
        if len(ctx.message.content.split()) > 1:
            desc_text += f"\n\nMessage content: {' '.join(ctx.message.content.split()[1:])}"
        emb = hf.green_embed(desc_text)
        await channel.send("@here", embed=emb)
        try:
            await ctx.message.add_reaction("✅")
        except discord.Forbidden:
            pass

def setup(bot):
    bot.add_cog(General(bot))
