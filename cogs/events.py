import urllib
import string
import re
import asyncio
import os
from urllib.error import HTTPError
from datetime import timedelta, datetime, timezone

import discord
from discord.ext import commands
from Levenshtein import distance as LDist

from .utils import helper_functions as hf
from .general import General
from .interactions import Interactions

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

ENG_ROLE = {
    266695661670367232: 266778623631949826,  # C-E Learning English Role
    320439136236601344: 474825178204078081  # r/CL Learning English Role
}
RYRY_RAI_BOT_ID = 270366726737231884


class Events(commands.Cog):
    """This module contains event listeners not in logger.py"""

    def __init__(self, bot):
        self.bot = bot
        self.ignored_characters = []

    @commands.Cog.listener()
    async def on_message(self, msg):
        if msg.author.bot:
            if msg.author.id != 720900750724825138:  # a window for BurdBot to post questions to AOTW
                return

        if msg.author.id == self.bot.owner_id:
            pass

        if not self.bot.is_ready:
            return

        ctx = await self.bot.get_context(msg)

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
            if "AOTW recording" in msg.content:
                await ctx.invoke(self.bot.get_command("question"), args=msg.content)

        await burdbot_window()

        # ### Replace tatsumaki/nadeko serverinfo posts
        async def replace_tatsumaki_posts():
            if msg.content in ['t!serverinfo', 't!server', 't!sinfo', '.serverinfo', '.sinfo']:
                if msg.guild.id in [JP_SERVER_ID, SP_SERVER_ID, RY_SERVER_ID]:
                    await ctx.invoke(General.serverinfo)

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

        """Owner self mute"""
        try:
            if self.bot.selfMute and msg.author.id == self.bot.owner_id:
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
        except AttributeError:
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
            # discord.gift is a legit url
            """
            ["freenitros", 'discord nitro for free', 'airdrop discord nitro', 'nitro from steam',
             "hi, i'm tired of csgo, i'm ieaving", 'fuck this trash caiied CS:GO, deieted',
             'nitro distribution', 'Discord Nitro free', "steam gived nitro"
             "take nitro faster, it's aiready running out", "free discord nitro airdrop",
             'discord.ciick', 'discordgiveaway', 'Free Discord Nitro AirDrop',
             'discordnitro', 'discordairdrop', 'discordgift', 'giftdiscord',
             'discord.oniine', 'bit.do/randomgift', 'nitrodiscord', 'steamnitro'
             'discordrgift.com', 'discord-gift.com', 'discord-gifte.com',
             'stmeacomunnitty.ru', 'steamcommrnunity.com', 'stearncornmnuity', 'rustiic.com']
            """
            links = self.bot.db['spam_links']
            # there are some words spelled with "i" instead of "l" in here, that's because I replace all l with i
            # because of spammers who try to write dlscord.com with an l

            if "giphy" in msg.content or "tenor" in msg.content:
                return  # Exempt these sites

            everyone = "@everyone" in msg.content  # only ban if they ping everyone

            try:
                if msg.guild.id == SP_SERVER_ID:
                    if msg.guild.get_channel_or_thread(838403437971767346).permissions_for(msg.author).read_messages:
                        return  # exempt all people in staff channel

                elif msg.guild.id == JP_SERVER_ID:
                    return  # Don't do Japanese server, Cirilla is working there
                    # if msg.guild.get_channel_or_thread(277384105245802497).permissions_for(msg.author).read_messages:
                    #     return  # exempt all people in everything_will_be_fine channel

                elif msg.guild.id == CH_SERVER_ID:
                    if msg.guild.get_channel_or_thread(267784908531957770).permissions_for(msg.author).read_messages:
                        return  # exempt all people in #bot-dev channel

                elif msg.guild.id in [477628709378195456,  # español e ingles (yoshi)
                                      472283823955116032,  # nyaa langs (naru)
                                      320439136236601344,  # /r/ChineseLanguages
                                      116379774825267202,  # nihongo to eigo
                                      484840490651353119,  # go! billy korean
                                      541522953423290370,  # /r/korean
                                      234492134806257665,  # let's learn korean
                                      275146036178059265]:  # test server
                    # 541500177018650641,  # german/english learning server (michdi)
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

            # Force a ban for users with a URL + "nitro" in their message and under 10 messages in the last month
            url_regex = r"https:\/\/(?!(discord|discordapp|discordstatus)\.)[a-zA-Z0-9_\-\.]*\.(com|gift|xyz|ru)"
            if messages < 10 or (messages < 100 and "@everyone" in msg.content):
                if re.findall(url_regex, msg.content.casefold()):
                    if "nitro" in msg.content.casefold() or "Whо is first?" in msg.content.casefold():
                        if msg.guild.id == SP_SERVER_ID:  # for now, only on Spanish server to test
                            everyone = messages = True

            # edit out typical modifications to the URLs to standardized urls for more generality
            msg_content = msg.content.casefold().replace('cll', 'd').replace('cl', 'd').replace('l', 'i')
            msg_content = msg_content.replace('crd', 'rd').replace('-', '').replace('discod', 'discord')
            msg_content = msg_content.replace('rcd', 'rd').replace("niitro", "nitro").replace("rid", "rd")
            msg_content = msg_content.replace('ff', 'f').replace('cords', 'cord')

            for link in links:
                if re.findall(link, msg_content):
                    try:
                        await msg.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass
                    cont = msg.content.replace('http', 'http ')  # break links

                    # a temporary list to prevent the spamming of multiple embeds and bans, dels at end of function
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

                    if msg.guild.id == SP_SERVER_ID:
                        mod_channel = msg.guild.get_channel_or_thread(297877202538594304)  # incidents channel
                    elif msg.guild.id == JP_SERVER_ID:  # JP_SERVER_ID
                        mod_channel = msg.guild.get_channel_or_thread(755269708579733626)  # anything_goes_tho
                    else:
                        mod_channel = msg.guild.get_channel_or_thread(self.bot.db['mod_channel'][str(msg.guild.id)])

                    if everyone and messages:  # ban
                        try:
                            await msg.author.ban(reason=f"Potential spam link: {cont}"[:512], delete_message_days=1)
                        except discord.Forbidden:
                            try:
                                self.bot.spammer_mute.remove(spammer_mute_entry)
                            except ValueError:
                                pass
                            return
                        await mod_channel.send(embed=hf.red_embed(f"Banned user {msg.author} ({msg.author.id}) for "
                                                                  f"potential  spam link:\n```{cont}```"))
                    elif messages:  # mute
                        ctx.author = ctx.guild.me
                        await ctx.invoke(self.bot.get_command('mute'),
                                         args=f"1h {str(msg.author.id)} "
                                              f"Inactive user sending Nitro spam-like message (please confirm)"
                                              f"\n```{cont}```")
                        await mod_channel.send(f"(@here) {msg.author.mention}",
                                               embed=hf.red_embed(f"🔇❓**MUTED** user {msg.author} ({msg.author.id}) "
                                                                  f"for potential spam link, [please confirm "
                                                                  f"the content]({msg.jump_url}) and possibly ban:"
                                                                  f"\n```{cont}```"))

                    else:  # notify
                        await mod_channel.send(f"(@here) {msg.author.mention}",
                                               embed=hf.red_embed(f"❓The active user {msg.author} ({msg.author.id}) "
                                                                  f"sent a potential spam link, please confirm "
                                                                  f"the content and possibly ban:\n```{cont}```"))

                    # remove from temporary list after all actions done
                    try:
                        self.bot.spammer_mute.remove(spammer_mute_entry)
                    except ValueError:
                        pass
                    return

        try:
            await hacked_account_ban()
        except Exception:
            if hasattr(self.bot, "spammer_mute"):
                try:
                    self.bot.spammer_mute.remove((msg.guild.id, msg.author.id))
                except ValueError:
                    pass
            raise

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
            category_roles = [msg.guild.get_role(802629332425375794),
                              msg.guild.get_role(802657919400804412),
                              msg.guild.get_role(831574815718506507)]
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
                    await msg.author.add_roles(english_role, *category_roles)
                except discord.NotFound:
                    return
            if language_score['spanish']:
                txt1 = " I've given you the `Spanish Native` role! ¡Te he asignado el rol de `Spanish Native!`\n\n"
                try:
                    await msg.author.add_roles(spanish_role, *category_roles)
                except discord.NotFound:
                    return
            if language_score['other']:
                txt1 = " I've given you the `Other Native` role! ¡Te he asignado el rol de `Other Native!`\n\n"
                try:
                    await msg.author.add_roles(other_role, *category_roles)
                except discord.NotFound:
                    return
            if language_score['both']:
                txt1 = " I've given you both roles! ¡Te he asignado ambos roles! "
                try:
                    await msg.author.add_roles(english_role, spanish_role, *category_roles)
                except discord.NotFound:
                    return

                    #  "You can add more roles in <#703075065016877066>:\n" \
                   #  "Puedes añadirte más en <#703075065016877066>:\n\n" \
            txt2 = "Before using the server, please read the rules in <#243859172268048385>.\n" \
                   "Antes de usar el servidor, por favor lee las reglas en <#243859172268048385>."
            await hf.safe_send(msg.channel, msg.author.mention + txt1 + txt2)

        await smart_welcome(msg)

        async def mods_ping():
            """mods ping on spanish server"""
            if str(msg.guild.id) not in self.bot.db['staff_ping']:
                return

            if 'channel' not in self.bot.db['staff_ping'][str(msg.guild.id)]:
                return

            config = self.bot.db['staff_ping'][str(msg.guild.id)]
            staff_role_id = config.get("role")  # try to get role id from staff_ping db
            if not staff_role_id:  # no entry in staff_ping db
                staff_role_id = self.bot.db['mod_role'].get(str(msg.guild.id), {}).get("id")
            if not staff_role_id:
                return  # This guild doesn't have a mod role or staff ping role set
            staff_role = msg.guild.get_role(staff_role_id)
            if not staff_role:
                return

            if f"<@&{staff_role_id}>" in msg.content:
                edited_msg = re.sub(rf'<?@?&?{str(staff_role_id)}>? ?', '', msg.content)
            else:
                return
            user_id_regex = r"<?@?!?(\d{17,22})>? ?"
            users = re.findall(user_id_regex, edited_msg)
            users = ' '.join(users)
            edited_msg = re.sub(user_id_regex, "", edited_msg)
            notif = await Interactions(self.bot).staffping_code(ctx=ctx, users=users, reason=edited_msg)

            if hasattr(self.bot, 'synced_reactions'):
                self.bot.synced_reactions.append((notif, msg))
            else:
                self.bot.synced_reactions = [(notif, msg)]

            return
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
            emb.add_field(name="Message:", value=msg.content[:1024 - len(link)] + link)

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
                    if isinstance(msg.channel, discord.Thread):
                        channel_id = msg.channel.parent.id
                    elif isinstance(msg.channel, discord.TextChannel):
                        channel_id = msg.channel.id
                    else:
                        return
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
                    if msg.guild.id == SP_SERVER_ID and msg.channel.id != 817074401680818186:
                        if hasattr(self.bot, 'langdetect'):
                            detected_lang = hf.detect_language(stripped_msg)
                        else:
                            return None, False
                    else:
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
                    if isinstance(msg.channel, discord.Thread):
                        channel_id = msg.channel.parent.id
                    elif isinstance(msg.channel, discord.TextChannel):
                        channel_id = msg.channel.id
                    else:
                        return
                    if ('*' not in msg.content
                            and channel_id not in self.bot.db['hardcore'][str(CH_SERVER_ID)]['ignore']):
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
                    await ctx.invoke(self.bot.get_command('mute'), args=f"1h {str(msg.author.id)} {reason}")

                    # notify in mod channel if it is set
                    if str(msg.guild.id) in self.bot.db['mod_channel']:
                        mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][str(ctx.guild.id)])
                        if msg.guild.id == SP_SERVER_ID:
                            mod_channel = msg.guild.get_channel_or_thread(297877202538594304)  # incidents channel
                        if mod_channel:
                            await hf.safe_send(mod_channel, msg.author.id,
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

        await antispam_check()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        to_delete = []
        for x in self.bot.db:
            for key in self.bot.db[x]:
                if str(guild.id) == key:
                    to_delete.append((x, key))
        for i in to_delete:
            del (self.bot.db[i[0]][i[1]])

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
            if str(reaction.emoji) in '🗑':
                if user == self.bot.user:
                    return  # Don't let Rai delete messages that Rai attaches :x: to
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
                    target = None

                    if reaction.message == pair[0]:
                        target = pair[1]
                    elif reaction.message == pair[1]:
                        target = pair[0]

                    if target:
                        try:
                            await target.add_reaction(reaction)
                        except (discord.Forbidden, discord.HTTPException) as e:
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
                            await ctx.invoke(General.blacklist_add, args=user_id)
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
                        await ctx.invoke(General.blacklist_add,
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
                self.bot.get_user(202995638860906496).send(
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
                self.bot.get_user(202995638860906496).send(
                    'on_raw_reaction_remove: Lacking `Manage Roles` permission'
                    f'<#{payload.guild_id}>')
            except AttributeError:
                return

    @commands.command(hidden=True)
    async def command_into_voice(self, ctx, member, after):
        if not ctx.author == self.bot.user:  # only Rai can use this
            return
        await self.into_voice(member, after)

    async def into_voice(self, member, after):
        if member.bot:
            return
        if after.afk or after.deaf or after.self_deaf or len(after.channel.members) <= 1:
            return
        guild = str(member.guild.id)
        member_id = str(member.id)
        config = self.bot.stats[guild]['voice']
        if member_id not in config['in_voice']:
            config['in_voice'][member_id] = discord.utils.utcnow().strftime("%Y/%m/%d %H:%M UTC")

    @commands.command(hidden=True)
    async def command_out_of_voice(self, ctx, member):
        if not ctx.author == self.bot.user:
            return
        await self.out_of_voice(member, date_str=None)

    async def out_of_voice(self, member, date_str=None):
        guild = str(member.guild.id)
        member_id = str(member.id)
        config = self.bot.stats[guild]['voice']
        if member_id not in config['in_voice']:
            return

        # calculate how long they've been in voice
        join_time = datetime.strptime(
            config['in_voice'][str(member.id)], "%Y/%m/%d %H:%M UTC").replace(tzinfo=timezone.utc)
        total_length = (discord.utils.utcnow() - join_time).seconds
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
    async def on_voice_state_update(self, member, before, after):
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
                            await hf.safe_send(member, "I tried to give you a role for being in a voice channel for "
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
                                await hf.safe_send(member,
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
                                await hf.safe_send(member,
                                                   "I tried to give you a role for being in a voice channel for "
                                                   "over 30 minutes, but either there was some kind of HTML "
                                                   "error or I lacked permission to assign/remove roles. Please "
                                                   "tell the admins of your server, or use the command "
                                                   "`;timed_voice_role` to disable the module.")
                                return
                            return

        await turkish_server_30_mins_role()

    @commands.Cog.listener()
    async def on_command(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['guildstats']:
            self.bot.db['guildstats'][str(ctx.guild.id)] = {'messages': {}, 'commands': {}}
        config: dict = self.bot.db['guildstats'][str(ctx.guild.id)]['commands']

        date_str = discord.utils.utcnow().strftime("%Y%m%d")
        config[date_str] = config.setdefault(date_str, 0) + 1


async def setup(bot):
    await bot.add_cog(Events(bot))
