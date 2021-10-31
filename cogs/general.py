import urllib
from typing import Optional

import discord
from discord.ext import commands
from datetime import timedelta
from .utils import helper_functions as hf
import re
import textblob
from Levenshtein import distance as LDist
import string
import asyncio
from urllib.error import HTTPError
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
TRACEBACKS_CHAN = 554572239836545074
JP_SERVER_ID = 189571157446492161
SP_SERVER_ID = 243838819743432704
CH_SERVER_ID = 266695661670367232
CL_SERVER_ID = 320439136236601344
RY_SERVER_ID = 275146036178059265

ENG_ROLE = {
    266695661670367232: 266778623631949826,  # C-E Learning English Role
    320439136236601344: 474825178204078081  # r/CL Learning English Role
}


def blacklist_check():
    async def pred(ctx):
        if not ctx.guild:
            return
        modchat = ctx.bot.get_guild(MODCHAT_SERVER_ID)
        if not modchat:
            return
        if ctx.author in modchat.members:
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

        if not self.bot.is_ready:
            return

        ##########################################

        if not msg.guild:  # all code after this has msg.guild requirement
            return

        ##########################################

        # ### BurdBot's window to open questions in #audio_of_the_week
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

        # ### Replace tatsumaki/nadeko serverinfo posts
        async def replace_tatsumaki_posts():
            if msg.content in ['t!serverinfo', 't!server', 't!sinfo', '.serverinfo', '.sinfo']:
                if msg.guild.id in [JP_SERVER_ID, SP_SERVER_ID, RY_SERVER_ID]:
                    new_ctx = await self.bot.get_context(msg)
                    await new_ctx.invoke(self.serverinfo)

        await replace_tatsumaki_posts()

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

            try:
                ryry = msg.guild.get_member(202995638860906496)
                if not ryry:
                    return
                if not msg.channel.permissions_for(msg.guild.get_member(202995638860906496)).read_messages:
                    return  # I ain't trying to spy on people
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

            to_check_words = ['ryry', 'ryan', 'らいらい', 'ライライ', '来雷', '雷来']
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
                        await hf.safe_send(mod_channel,
                                           f"Warning: {msg.author.name} may have said the banned words spam message"
                                           f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                           f"\n```{msg.content}"[:1995] + '```')
                        return
                    try:
                        await msg.delete()
                    except discord.Forbidden:
                        await hf.safe_send(mod_channel,
                                           f"Rai is lacking the permission to delete messages for the Chinese "
                                           f"spam message.")
                    except discord.NotFound:
                        pass

                    try:
                        await asyncio.sleep(3)
                        await msg.author.ban(reason=f"__Reason__: Automatic ban: Chinese banned words spam\n"
                                                    f"{msg.content[:100]}", delete_message_days=1)
                    except discord.Forbidden:
                        await hf.safe_send(mod_channel,
                                           f"I tried to ban someone for the Chinese spam message, but I lack "
                                           f"the permission to ban users.")

                    await hf.safe_send(log_channel, f"Banned {msg.author} for the banned words spam message."
                                                    f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                                    f"\n```{msg.content}"[:1850] + '```')

                    return

        await chinese_server_banned_words()

        # ### bans accounts that have been in the server for a while but got hacked so started spamming
        async def hacked_account_ban():
            links = ["freenitros", 'discord nitro for free', 'airdrop discord nitro',
                     "hi, i'm tired of csgo, i'm ieaving", 'nitro distribution', 'Discord Nitro free',
                     "take nitro faster, it's aiready running out",
                     'discord.ciick', 'discordgiveaway',
                     'discordnitro', 'discordairdrop', 'discord-gift',
                     'discord.oniine', 'discordgift', 'bit.do/randomgift',
                     'discordrgift.com', 'discord-gift.com', 'discord-gifte.com',
                     'stmeacomunnitty.ru', 'steamcommrnunity.com', 'rustiic.com']
            # there are some words spelled with "i" instead of "l" in here, that's because I replace all l with i
            # because of spammers who try to write dlscord.com with an l

            everyone = "@everyone" in msg.content  # only ban if they ping everyone

            try:
                if msg.guild.id == SP_SERVER_ID:
                    if msg.guild.get_channel(838403437971767346).permissions_for(msg.author).read_messages:
                        return  # exempt all people in staff channel

                elif msg.guild.id == JP_SERVER_ID:
                    if msg.guild.get_channel(277384105245802497).permissions_for(msg.author).read_messages:
                        return  # exempt all people in everything_will_be_fine channel

                elif msg.guild.id == CH_SERVER_ID:
                    if msg.guild.get_channel(267784908531957770).permissions_for(msg.author).read_messages:
                        return  # exempt all people in #bot-dev channel

                elif msg.guild.id in [541500177018650641,  # german/english learning server (michdi)
                                      477628709378195456,  # español e ingles (yoshi)
                                      472283823955116032,  # nyaa langs (naru)
                                      320439136236601344,  # /r/ChineseLanguages
                                      116379774825267202,  # nihongo to eigo
                                      484840490651353119,  # go! billy korean
                                      541522953423290370,  # /r/korean
                                      234492134806257665,  # let's learn korean
                                      275146036178059265]:  # test server
                    pass

                else:
                    return  # this module only works for spanish/japanese/chinese server

            except AttributeError:
                return
                # permissions_for(msg.author).read_messages -->
                # AttributeError: 'User' object has no attribute '_roles'

            try:
                number_of_messages = hf.count_messages(msg.author)
            except AttributeError:  # AttributeError: 'User' object has no attribute 'guild'
                return
            messages = (number_of_messages < 50)  # only potentially ban users who are inactive to avoid false positives

            # edit out typical modifications to the URLs to standardized urls for more generality
            msg_content = msg.content.casefold().replace('cll', 'd').replace('cl', 'd').replace('l', 'i')
            msg.content = msg.content.replace('crd', 'rd').replace('-', '').replace('discod', 'discord')
            msg.content = msg.content.replace('rcd', 'rd')
            for link in links:
                if link in msg_content:
                    try:
                        await msg.delete()
                    except discord.NotFound:
                        pass
                    cont = msg.content.replace('http', 'http ')  # break links

                    # a temporary list to prevent the spamming of multiple embeds and bans, dels at end of function
                    if not hasattr(self.bot, "spammer_mute"):
                        self.bot.spammer_mute = []  # a temporary list

                    if (spammer_mute_entry := (msg.guild.id, msg.author.id)) in self.bot.spammer_mute:
                        return
                    else:
                        self.bot.spammer_mute.append(spammer_mute_entry)  # will remove at end of function

                    if msg.guild.id == SP_SERVER_ID:
                        mod_channel = msg.guild.get_channel(297877202538594304)  # incidents channel
                    elif msg.guild.id == JP_SERVER_ID:  # JP_SERVER_ID
                        mod_channel = msg.guild.get_channel(755269708579733626)  # anything_goes_tho
                    else:
                        mod_channel = msg.guild.get_channel(self.bot.db['mod_channel'][str(msg.guild.id)])

                    if everyone and messages:  # ban
                        try:
                            await msg.author.ban(reason=f"Potential spam link: {cont}"[:512], delete_message_days=1)
                        except discord.Forbidden:
                            return
                        await mod_channel.send(embed=hf.red_embed(f"Banned user {msg.author} ({msg.author.id}) for "
                                                                  f"potential  spam link:\n```{cont}```"))
                    elif messages:  # mute
                        ctx = await self.bot.get_context(msg)
                        ctx.author = ctx.guild.me
                        await ctx.invoke(self.bot.get_command('mute'),
                                         args=f"1h {str(msg.author.id)} "
                                              f"{'Inactive user sending Nitro spam-like message (please confirm)'}")
                        await mod_channel.send(msg.author.mention,
                                               embed=hf.red_embed(f"🔇❓**MUTED** user {msg.author} ({msg.author.id}) "
                                                                  f"for potential spam link, [please confirm "
                                                                  f"the content]({msg.jump_url}) and possibly ban:"
                                                                  f"\n```{cont}```"))

                    else:  # notify
                        await mod_channel.send(msg.author.mention,
                                               embed=hf.red_embed(f"❓The active user {msg.author} ({msg.author.id}) "
                                                                  f"sent a potential spam link, please confirm "
                                                                  f"the content and possibly ban:\n```{cont}```"))

                    # remove from temporary list after all actions done
                    self.bot.spammer_mute.remove(spammer_mute_entry)

                    return

        await hacked_account_ban()

        # ### bans accounts that spam right after having joined the server
        async def spam_account_bans():
            words = ['amazingsexdating', 'bestdatingforall', 'nakedphotos.club', 'privatepage.vip', 'viewc.site',
                     'libra-sale.io', 'ethway.io', 'omg-airdrop', 'linkairdrop', "Airdrop Time!", "freenitros.ru/",
                     'discorcl.click/', 'discord-giveaway.com/', 'bit.do/randomgift', 'stmeacomunnitty.ru',
                     'discordrgift.com', 'discordc.gift', 'discord-gifte.com'
                     'Discord Nitro for Free', 'AIRDROP DISCORD NITRO']
            if "@everyone" not in msg.content:
                return
            try:
                for word in words:
                    if word in msg.content:
                        time_ago = discord.utils.utcnow() - msg.author.joined_at
                        msg_text = f"Bot spam message in [{msg.guild.name}] - [{msg.channel.name}] by " \
                                   f"{msg.author.name} (joined {time_ago.seconds // 3600}h " \
                                   f"{time_ago.seconds % 3600 // 60}m ago [{time_ago}])```{msg.content}```"
                        await self.bot.get_user(self.bot.owner_id).send(msg_text)
                        if str(msg.author.guild.id) not in self.bot.db['auto_bans']:
                            return
                        if self.bot.db['auto_bans'][str(msg.author.guild.id)]['enable']:
                            if time_ago < timedelta(minutes=20) or \
                                    (msg.channel.id == 559291089018814464 and time_ago < timedelta(hours=5)):
                                if msg.author.id in [202995638860906496, 414873201349361664]:
                                    return
                                try:
                                    await msg.author.ban(reason=f'For posting spam link: {msg.content}'[:512],
                                                         delete_message_days=1)
                                except discord.Forbidden:
                                    return
                                self.bot.db['global_blacklist']['blacklist'].append(msg.author.id)
                                channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
                                emb = hf.red_embed(f"{msg.author.id} (automatic addition)")
                                emb.add_field(name="Reason", value=msg.content)
                                await hf.safe_send(channel, embed=emb)
                                created_ago = discord.utils.utcnow() - msg.author.created_at
                                joined_ago = discord.utils.utcnow() - msg.author.joined_at
                                message = f"**Banned a user for posting a {word} link.**" \
                                          f"\n**ID:** {msg.author.id}" \
                                          f"\n**Server:** {msg.author.guild.name}" \
                                          f"\n**Name:** {msg.author.name} {msg.author.mention}" \
                                          f"\n**Account creation:** {msg.author.created_at} " \
                                          f"({created_ago.days}d {created_ago.seconds // 3600}h ago)" \
                                          f"\n**Server join:** {msg.author.joined_at} " \
                                          f"({joined_ago.days}d {joined_ago.seconds // 3600}h ago)" \
                                          f"\n**Message:** {msg.content}"
                                emb2 = hf.red_embed(message)
                                emb2.color = discord.Color(int('000000', 16))
                                await self.bot.get_channel(BANS_CHANNEL_ID).send(embed=emb2)
                                if str(msg.guild.id) in self.bot.db['bans']:
                                    if self.bot.db['bans'][str(msg.guild.id)]['channel']:
                                        channel_id = self.bot.db['bans'][str(msg.guild.id)]['channel']
                                        await self.bot.get_channel(channel_id).send(embed=emb2)
                                return

            except KeyError:
                pass
            except AttributeError:
                pass

        await spam_account_bans()

        """spanish server welcome channel module"""

        async def smart_welcome(msg):
            if msg.channel.id != SP_SERVER_ID:
                return
            content = re.sub('> .*\n', '', msg.content.casefold())  # remove quotes in case the user quotes bot
            content = content.translate(str.maketrans('', '', string.punctuation))  # remove punctuation
            for word in ['hello', 'hi', 'hola', 'thanks', 'gracias']:
                if content == word:
                    return  # ignore messages that are just these single words
            if msg.content == '<@270366726737231884>':  # ping to Rai
                return  # ignore pings to Rai
            english_role = msg.guild.get_role(243853718758359040)
            spanish_role = msg.guild.get_role(243854128424550401)
            other_role = msg.guild.get_role(247020385730691073)
            for role in [english_role, spanish_role, other_role]:
                if role in msg.author.roles:
                    return  # ignore messages by users with tags already
            if discord.utils.utcnow() - msg.author.joined_at < timedelta(seconds=3):
                return

            english = ['english', 'inglés', 'anglohablante', 'angloparlante']
            spanish = ['spanish', 'español', 'hispanohablante', 'hispanoparlante', 'castellano']
            other = ['other', 'neither', 'otro', 'otra', 'arabic', 'french', 'árabe', 'francés', 'portuguese',
                     'brazil', 'portuguesa', 'brazilian']
            both = ['both', 'ambos', 'los dos']
            txt1 = ''
            language_score = {'english': 0, 'spanish': 0, 'other': 0, 'both': 0}  # eng, sp, other, both
            split = content.split()

            def check_language(language, index):
                skip_next_word = False  # just defining the variable
                for language_word in language:  # language = one of the four word lists above
                    for content_word in split:  # content_word = the words in their message
                        if len(content_word) <= 3:
                            continue  # skip words three letters or less
                        if content_word in ['there']:
                            continue  # this triggers the word "other" so I skip it
                        if skip_next_word:  # if i marked this true from a previous loop...
                            skip_next_word = False  # ...first, reset it to false...
                            continue  # then skip this word
                        if content_word.startswith("learn") or content_word.startswith('aprend') \
                                or content_word.startswith('estud') or content_word.startswith('stud') or \
                                content_word.startswith('fluent'):
                            skip_next_word = True  # if they say any of these words, skip the *next* word
                            continue  # example: "I'm learning English, but native Spanish", skip "English"
                        if LDist(language_word, content_word) < 3:
                            language_score[language[0]] += 1

            check_language(english, 0)  # run the function I just defined four times, once for each of these lists
            check_language(spanish, 1)
            check_language(other, 2)
            check_language(both, 3)

            num_of_hits = 0
            for lang in language_score:
                if language_score[lang]:  # will add 1 if there's any value in that dictionary entry
                    num_of_hits += 1  # so "english spanish" gives 2, but "english english" gives 1

            if num_of_hits != 1:  # the bot found more than one language statement in their message, so ask again
                await msg.channel.send(f"{msg.author.mention}\n"
                                       f"Hello! Welcome to the server!          Is your **native language**: "
                                       f"__English__, __Spanish__, __both__, or __neither__?\n"
                                       f"¡Hola! ¡Bienvenido(a) al servidor!    ¿Tu **idioma materno** es: "
                                       f"__el inglés__, __el español__, __ambos__ u __otro__?")
                return

            if msg.content.startswith(';') or msg.content.startswith('.'):
                return

            if language_score['english']:
                txt1 = " I've given you the `English Native` role! ¡Te he asignado el rol de `English Native`!\n\n"
                try:
                    await msg.author.add_roles(english_role)
                except discord.NotFound:
                    return
            if language_score['spanish']:
                txt1 = " I've given you the `Spanish Native` role! ¡Te he asignado el rol de `Spanish Native!`\n\n"
                try:
                    await msg.author.add_roles(spanish_role)
                except discord.NotFound:
                    return
            if language_score['other']:
                txt1 = " I've given you the `Other Native` role! ¡Te he asignado el rol de `Other Native!`\n\n"
                try:
                    await msg.author.add_roles(other_role)
                except discord.NotFound:
                    return
            if language_score['both']:
                txt1 = " I've given you both roles! ¡Te he asignado ambos roles! "
                try:
                    await msg.author.add_roles(english_role, spanish_role)
                except discord.NotFound:
                    return

            txt2 = "You can add more roles in <#703075065016877066>:\n" \
                   "Puedes añadirte más en <#703075065016877066>:\n\n" \
                   "Before using the server, please read the rules in <#243859172268048385>.\n" \
                   "Antes de usar el servidor, por favor lee las reglas en <#243859172268048385>."
            await hf.safe_send(msg.channel, msg.author.mention + txt1 + txt2)

        await smart_welcome(msg)

        async def mods_ping():
            """mods ping on spanish server"""
            em = discord.Embed(title=f"Staff Ping",
                               description=f"From {msg.author.mention} ({msg.author.name}) "
                                           f"in {msg.channel.mention}\n[Jump URL]({msg.jump_url})",
                               color=discord.Color(int('FFAA00', 16)),
                               timestamp=discord.utils.utcnow())
            if msg.guild.id in [SP_SERVER_ID, JP_SERVER_ID]:
                if '<@&642782671109488641>' in msg.content or '<@&240647591770062848>' in msg.content:
                    content = msg.content.replace('<@&642782671109488641>', '').replace('<@&240647591770062848>', '')

                    if content:
                        em.add_field(name="Content", value=content[:1024])
                    for user in self.bot.db['staff_ping'][str(msg.guild.id)]['users']:
                        await hf.safe_send(self.bot.get_user(user), embed=em)

                    if 'channel' in self.bot.db['staff_ping'][str(msg.guild.id)]:
                        notif_channel = self.bot.get_channel(self.bot.db['staff_ping'][str(msg.guild.id)]['channel'])
                    elif str(msg.guild.id) in self.bot.db['submod_channel']:
                        notif_channel = self.bot.get_channel(self.bot.db['submod_channel'][str(msg.guild.id)])
                    else:
                        return
                    notif = await hf.safe_send(notif_channel, embed=em)

                    # Add message to list of synchronized reaction messages
                    if hasattr(self.bot, 'synced_reactions'):
                        self.bot.synced_reactions[notif] = msg
                        self.bot.synced_reactions[msg] = notif
                    else:
                        self.bot.synced_reactions = {notif: msg, msg: notif}

                """ mods ping on other servers"""
            else:
                if str(msg.guild.id) not in self.bot.db['staff_ping']:
                    return

                if 'channel' not in self.bot.db['staff_ping'][str(msg.guild.id)]:
                    return

                if str(msg.guild.id) in self.bot.db['mod_role']:
                    mod_role = msg.guild.get_role(self.bot.db['mod_role'][str(msg.guild.id)]['id'])
                else:
                    return

                if not mod_role:
                    return

                if mod_role in msg.role_mentions:
                    notif_channel = self.bot.get_channel(self.bot.db['staff_ping'][str(msg.guild.id)]['channel'])
                    await hf.safe_send(notif_channel, embed=em)

        await mods_ping()

        # ### super_watch
        async def super_watch():
            try:
                config = self.bot.db['super_watch'][str(msg.guild.id)]
            except KeyError:
                return

            if not hasattr(msg.author, "guild"):
                return  # idk why this should be an issue but it returned an error once

            if str(msg.author.id) in config['users']:
                desc = "❗ "
                which = 'sw'
            elif hf.count_messages(msg.author) < 10 and config.get('enable', None):
                minutes_ago_created = int(((discord.utils.utcnow() - msg.author.created_at).total_seconds()) // 60)
                if minutes_ago_created > 60 or msg.channel.id == SP_SERVER_ID:
                    return
                desc = '🆕 '
                which = 'new'
            else:
                return

            desc += f"**{msg.author.name}#{msg.author.discriminator}** ({msg.author.id})"
            emb = discord.Embed(description=desc, color=0x00FFFF, timestamp=discord.utils.utcnow())
            emb.set_footer(text=f"#{msg.channel.name}")

            link = f"\n([Jump URL]({msg.jump_url})"
            if which == 'sw':
                if config['users'][str(msg.author.id)]:
                    link += f" － [Entry Reason]({config['users'][str(msg.author.id)]})"
            link += ')'
            emb.add_field(name="Message:", value=msg.content[:2000 - len(link)] + link)

            await hf.safe_send(self.bot.get_channel(config['channel']), embed=emb)

        await super_watch()

        # ### Lang check: will check if above 3 characters + hardcore, or if above 15 characters + stats
        async def lang_check():
            detected_lang = None
            is_hardcore = False
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
                            is_hardcore = True

            if str(msg.guild.id) in self.bot.stats:
                if len(stripped_msg) > 15 and self.bot.stats[str(msg.guild.id)].get('enable', None):
                    check_lang = True

            if check_lang:
                try:
                    if msg.guild.id == SP_SERVER_ID and msg.channel.id != 817074401680818186:
                        if hasattr(self.bot, 'langdetect'):
                            detected_lang = hf.detect_language(stripped_msg)
                        else:
                            return None, False
                    else:
                        try:
                            detected_lang = await hf.textblob_detect_language(stripped_msg)
                        except (textblob.exceptions.TranslatorError, HTTPError, TimeoutError, urllib.error.URLError):
                            return None, False
                except (HTTPError, TimeoutError, urllib.error.URLError):
                    pass
            return detected_lang, is_hardcore

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
            date_str = discord.utils.utcnow().strftime("%Y%m%d")
            if date_str not in config['messages']:
                config['messages'][date_str] = {}
            today = config['messages'][date_str]
            author = str(msg.author.id)
            channel = msg.channel
            if isinstance(channel, discord.TextChannel):
                channel = str(msg.channel.id)
            elif isinstance(channel, discord.Thread):
                if msg.channel.parent:
                    channel = str(msg.channel.parent.id)
                else:
                    return
            else:
                return

            # message count
            today.setdefault(author, {})
            today[author].setdefault('channels', {})
            today[author]['channels'][channel] = today[author]['channels'].get(channel, 0) + 1

            # emojis
            emojis = re.findall(r':([A-Za-z0-9_]+):', msg.content)
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
                    except discord.NotFound:
                        return
                    if len(msg.content) > 30:
                        await hf.long_deleted_msg_notification(msg)
            elif learning_sp in msg.author.roles:  # learning Spanish, delete all English
                if 'holi' in msg.content.casefold():
                    return
                if lang == 'en':
                    try:
                        await msg.delete()
                    except discord.NotFound:
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
                except discord.Forbidden:
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
                    return
                else:
                    self.bot.spammer_mute.append(spammer_mute_entry)  # will remove at end of function

                try:
                    # execute the 1h mute command
                    ctx = await self.bot.get_context(msg)
                    ctx.author = msg.guild.me
                    await ctx.invoke(self.bot.get_command('mute'), args=f"1h {str(msg.author.id)} {reason}")

                    # notify in mod channel if it is set
                    if str(msg.guild.id) in self.bot.db['mod_channel']:
                        mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][str(ctx.guild.id)])
                        if msg.guild.id == SP_SERVER_ID:
                            mod_channel = msg.guild.get_channel(297877202538594304)  # incidents channel
                        if mod_channel:
                            await hf.safe_send(mod_channel,
                                               embed=hf.red_embed(f"Muted for 1h: {str(msg.author)} for {reason}\n"
                                                                  f"[Jump URL]({msg.jump_url})"))

                # skip if something went wrong
                except (discord.Forbidden, discord.HTTPException):
                    pass

                # remove from temporary list after all actions done
                self.bot.spammer_mute.remove(spammer_mute_entry)

            def purge_check(m):
                return m.author == msg.author and m.content == msg.content

            await msg.channel.purge(limit=50, check=purge_check)

        # await antispam_check()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        to_delete = []
        for x in self.bot.db:
            for key in self.bot.db[x]:
                if str(guild.id) == key:
                    to_delete.append((x, key))
        for i in to_delete:
            del (self.bot.db[i[0]][i[1]])

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
            await hf.safe_send(ctx, to_send[:2000])
            if len(to_send) > 2000:
                await hf.safe_send(ctx, to_send[2000:])

    @commands.command()
    @commands.check(lambda ctx: ctx.guild.id == 759132637414817822 if ctx.guild else False)
    async def risk(self, ctx):
        """Typing this command will sub you to pings for when it's your turn."""
        config = self.bot.db['risk']['sub']
        if str(ctx.author.id) in config:
            config[str(ctx.author.id)] = not config[str(ctx.author.id)]
        else:
            config[str(ctx.author.id)] = True
        if config[str(ctx.author.id)]:
            await hf.safe_send(ctx, "You will now receive pings when it's your turn.")
        else:
            await hf.safe_send(ctx, "You will no longer receive pings when it's your turn.")

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
        try:
            await hf.safe_send(ctx, topic)
        except discord.Forbidden:
            pass

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
    @commands.check(lambda ctx: ctx.guild.id in [SP_SERVER_ID, CH_SERVER_ID, CL_SERVER_ID] if ctx.guild else False)
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
    @hf.is_admin()
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
    async def lovehug(self, ctx, url=None):
        """A command group for subscribing to lovehug mangas."""
        await ctx.invoke(self.lovehug_add, url)

    @lovehug.command(name='add')
    async def lovehug_add(self, ctx, url):
        """Adds a URL to your subscriptions."""
        search = await ctx.invoke(self.bot.get_command('lovehug_get_chapter'), url)
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
        if url not in self.bot.db['lovehug']:
            self.bot.db['lovehug'][url] = {'last': f"{url}{search['href']}",
                                           'subscribers': [ctx.author.id]}
        else:
            if ctx.author.id not in self.bot.db['lovehug'][url]['subscribers']:
                self.bot.db['lovehug'][url]['subscribers'].append(ctx.author.id)
            else:
                await hf.safe_send(ctx, "You're already subscribed to this manga.")
                return
        await hf.safe_send(ctx, f"The latest chapter is: {url}{search['href']}\n\n"
                                f"I'll tell you next time a chapter is uploaded.")

    @lovehug.command(name='remove')
    async def lovehug_remove(self, ctx, url):
        """Unsubscribes you from a manga. Input the URL: `;lh remove <url>`."""
        if url not in self.bot.db['lovehug']:
            await hf.safe_send(ctx, "No one is subscribed to that manga. Check your URL.")
            return
        else:
            if ctx.author.id in self.bot.db['lovehug'][url]['subscribers']:
                self.bot.db['lovehug'][url]['subscribers'].remove(ctx.author.id)
                await hf.safe_send(ctx, "You've been unsubscribed from that manga.")
                if len(self.bot.db['lovehug'][url]['subscribers']) == 0:
                    del self.bot.db['lovehug'][url]
            else:
                await hf.safe_send("You're not subscribed to that manga.")
                return

    @lovehug.command(name='list')
    async def lovehug_list(self, ctx):
        """Lists the manga you subscribed to."""
        subscriptions = []
        for url in self.bot.db['lovehug']:
            if ctx.author.id in self.bot.db['lovehug'][url]['subscribers']:
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
                            await hf.safe_send(mod_channel, msg_to_mod_channel)
                            return
                    await user.send("You aren't on the waiting list.")

        await remove_from_waiting_list()

        "I or people with manage messages permission can delete bot messages by attaching X or trash can"

        async def delete_rai_message():
            if str(reaction.emoji) in '🗑❌':
                if reaction.message.author == self.bot.user and \
                        (user.id == self.bot.owner_id or
                         reaction.message.channel.permissions_for(user).manage_messages):
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

        "Remove reactions for if you're self muted"

        async def remove_selfmute_reactions():
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

        "Synchronize reactions on specified messages (staff pings)"

        async def synchronize_reactions():
            if hasattr(self.bot, 'synced_reactions'):
                if reaction.message in self.bot.synced_reactions and not reaction.message.author.bot:
                    target_msg = self.bot.synced_reactions[reaction.message]
                    try:
                        await target_msg.add_reaction(reaction)
                    except (discord.Forbidden, discord.HTTPException) as e:
                        return
            else:
                return

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
                        except discord.Forbidden:
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
            await asyncio.sleep(7)
            await msg.delete()
        except discord.Forbidden:
            msg = await hf.safe_send(ctx, "I lack the permissions to change your nickname")
            await asyncio.sleep(7)
            await msg.delete()
        except discord.HTTPException:
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
        except discord.Forbidden:
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
    @commands.cooldown(1, 15, type=commands.BucketType.user)
    async def check_language(self, ctx, *, msg: str):
        """Shows what's happening behind the scenes for hardcore mode.  Will try to detect the language that your\
        message was typed in, and display the results.  Note that this is non-deterministic code, which means\
        repeated results of the same exact message might give different results every time.

        Usage: `;cl <text you wish to check>`"""
        if not ctx.guild:
            return
        stripped_msg = hf.rem_emoji_url(msg)
        if len(msg) > 900:
            await hf.safe_send(ctx, "Please pick a shorter test  message")
            return
        if not stripped_msg:
            stripped_msg = ' '
        if ctx.guild.id in [SP_SERVER_ID, 759132637414817822]:
            probs = self.bot.langdetect.predict_proba([stripped_msg])[0]
            lang_result = f"English: {round(probs[0], 3)}\nSpanish: {round(probs[1], 3)}"
            ctx.command.reset_cooldown(ctx)
        else:
            lang_result = await hf.textblob_detect_language(stripped_msg)
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
        em.set_thumbnail(url=guild.icon.replace(static_format='png').url)
        em.add_field(name="Region", value=guild.region)
        em.add_field(name="Channels", value=f"{len(guild.text_channels)} text / {len(guild.voice_channels)} voice")
        em.add_field(name="Verification Level", value=guild.verification_level)
        em.add_field(name="Guild created on (UTC)", value=guild.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        em.add_field(name="Number of members", value=ctx.guild.member_count)

        if guild.afk_channel:
            em.add_field(name="Voice AFK Timeout",
                         value=f"{guild.afk_timeout // 60} mins → {guild.afk_channel.mention}")

        if guild.explicit_content_filter != "disabled":
            em.add_field(name="Explicit Content Filter", value=guild.explicit_content_filter)

        if guild.id not in [JP_SERVER_ID, SP_SERVER_ID]:
            em.add_field(name="Server owner", value=f"{guild.owner.name}#{guild.owner.discriminator}")

        # count top 6 member roles
        if len(guild.members) < 60000:
            role_count = Counter(role.name for member in guild.members
                                 for role in member.roles if not role.is_default())

            top_six_roles = '\n'.join(f"{role}: {count}" for role, count in role_count.most_common(6))
            em.add_field(name=f"Top 6 roles (out of {len(guild.roles)})", value=top_six_roles)
        else:
            em.add_field(name="Roles", value=str(len(guild.roles)))

        how_long_ago = discord.utils.utcnow() - guild.created_at
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
        emb.set_field_at(0, name="Entry removed by", value=f"{str(ctx.author)}")
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
                try:
                    await ctx.message.add_reaction('✅')
                except discord.Forbidden:
                    await ctx.send("User added to blacklist ✅")
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
                    try:
                        await hf.safe_send(ctx.author, f"{user} - Someone from your server already voted")
                    except discord.Forbidden:
                        await hf.safe_send(ctx, f"{user} - Someone from your server already voted")
                    continue

                message = await channel.fetch_message(config['votes2'][user]['message'])
                emb = message.embeds[0]
                title_str = emb.title
                result = re.search('(\((.*)\))? \((.) votes?\)', title_str)
                # target_username = result.group(2)
                num_of_votes = result.group(3)
                emb.title = re.sub('(.) vote', f'{int(num_of_votes) + 1} vote', emb.title)
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
        user_role_ids = [role.id for role in ctx.author.roles if str(role.color) == "#3498db"]  # only want blue roles
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

    @global_blacklist.command(name="ignore")
    @blacklist_check()
    async def blacklist_ignore(self, ctx, user_id):
        """Types ;gbl ignore <id> to remove a user from (or add back to) all future logging in the bans channel.
        Use this for test accounts, alt accounts, etc."""
        try:
            user_id = int(user_id)
            if not (17 < len(str(user_id)) < 22):
                raise ValueError
        except ValueError:
            await hf.safe_send(ctx, "Please input a valid ID.")
            return
        if user_id in self.bot.db['bansub']['ignore']:
            self.bot.db['bansub']['ignore'].remove(user_id)
            await hf.safe_send(ctx, embed=hf.red_embed("I've removed that user from the ignore list."))
        else:
            self.bot.db['bansub']['ignore'].append(user_id)
            await hf.safe_send(ctx, embed=hf.green_embed("I've added that user to the ignore list for ban logging."))

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
        num_of_pages = (len(roles_list) // 20) + 1
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

    @staticmethod
    def iam_find_role(ctx, r_name):
        r_name = r_name.casefold()
        found_role = discord.utils.find(lambda r: r.name.casefold() == r_name, ctx.guild.roles)
        if not found_role:
            if 3 <= len(r_name):
                found_role = discord.utils.find(lambda r: r.name.casefold().startswith(r_name), ctx.guild.roles)
                if not found_role:
                    if 3 <= len(r_name) <= 6:
                        found_role = discord.utils.find(lambda r: LDist(r.name.casefold()[:len(r_name)], r_name) <= 1,
                                                        ctx.guild.roles)
                    elif 6 < len(r_name):
                        found_role = discord.utils.find(lambda r: LDist(r.name.casefold()[:len(r_name)], r_name) <= 3,
                                                        ctx.guild.roles)
        return found_role

    @commands.command(aliases=['im'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    @commands.guild_only()
    async def iam(self, ctx, *, role_name):
        """Command used to self-assign a role. Type `;iam <role name>`. Type `;lsar` to see the list of roles.

        You can also just type the beginning of a role name and it will find it. You can also slightly misspel it.

        Example: `;iam English`"""
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['SAR']:
            return
        config = self.bot.db['SAR'][str(ctx.guild.id)]
        role_name = role_name.casefold()
        found_role = self.iam_find_role(ctx, role_name)
        if not found_role:
            await hf.safe_send(ctx,
                               embed=hf.red_embed(f"**{str(ctx.author)}** No role found"))
            return

        if found_role in ctx.author.roles:
            await hf.safe_send(ctx, embed=hf.red_embed(f"**{str(ctx.author)}** "
                                                       f"You already have that role"))
            return

        for group in config:
            for role_id in config[group]:
                if found_role.id == role_id:
                    await ctx.author.add_roles(found_role)
                    await hf.safe_send(ctx, embed=hf.green_embed(
                        f"**{str(ctx.author)}** You now have"
                        f" the **{found_role.name}** role."))
                    return

    @commands.command(aliases=['iamn', '!iam'])
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    async def iamnot(self, ctx, *, role_name):
        """Command used to remove a self-assigned role"""
        if str(ctx.guild.id) not in self.bot.db['SAR']:
            return
        config = self.bot.db['SAR'][str(ctx.guild.id)]

        found_role = self.iam_find_role(ctx, role_name)
        if not found_role:
            await hf.safe_send(ctx,
                               embed=hf.red_embed(f"**{str(ctx.author)}** No role found"))
            return

        if found_role not in ctx.author.roles:
            await hf.safe_send(ctx, embed=hf.red_embed(f"**{str(ctx.author)}** "
                                                       f"You don't have that role"))
            return

        for group in config:
            for role_id in config[group]:
                if found_role.id == role_id:
                    await ctx.author.remove_roles(found_role)
                    await hf.safe_send(ctx,
                                       embed=hf.green_embed(
                                           f"**{str(ctx.author)}** You no longer have "
                                           f"the **{found_role.name}** role."))
                    return

        await hf.safe_send(ctx, embed=hf.red_embed(f"**{str(ctx.author)}** That role is not "
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
            old_channel = target.voice.channel

            if ctx.guild.afk_channel:
                await target.move_to(ctx.guild.afk_channel)
                await target.move_to(old_channel)
            else:
                for channel in ctx.guild.voice_channels:
                    if not channel.members:
                        try:
                            await target.move_to(channel)
                            await target.move_to(old_channel)
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

        modlog_config = hf.add_to_modlog(ctx, target, 'Voice Mute', reason, silent, time)
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
    @commands.bot_has_permissions(send_messages=True)
    @commands.guild_only()
    async def self_mute(self, ctx, time=None):
        """Irreversible mutes yourself for a certain amount of hours. Use like `;selfmute <number of hours>`.

        For example: `;selfmute 3` to mute yourself for three hours. This was made half for anti-procrastination, half\
        to end people asking for it."""
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            await hf.safe_send(ctx, "This command works by manually deleting all the messages of the self-muted user, "
                                    "but Rai currently lacks the `Manage Messages` permission, so you can't use this "
                                    "command.")
            return

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

        old_time = time
        if time <= 0:
            time = 0

        try:
            msg = await self.bot.wait_for('message',
                                          timeout=15,
                                          check=lambda m: m.author == ctx.author and m.channel == ctx.channel)

            if msg.content.casefold() == 'yes':  # confirm
                config = self.bot.db['selfmute'].setdefault(str(ctx.guild.id), {})
                time_string, length = hf.parse_time(f"{time}h")
                config[str(ctx.author.id)] = {'enable': True, 'time': time_string}
                await hf.safe_send(ctx, f"Muted {ctx.author.display_name} for {old_time} hours. This is irreversible. "
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
        notif: Optional[discord.Message] = await channel.send("@here", embed=emb)

        try:
            await ctx.message.add_reaction("✅")
        except discord.Forbidden:
            pass

        if hasattr(self.bot, 'synced_reactions'):
            self.bot.synced_reactions[notif] = ctx.message
            self.bot.synced_reactions[ctx.message] = notif
        else:
            self.bot.synced_reactions = {notif: ctx.message, ctx.message: notif}


def setup(bot):
    bot.add_cog(General(bot))
