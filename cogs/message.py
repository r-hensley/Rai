import asyncio
import os
import re
import string
import time
import traceback
import urllib
from datetime import timedelta
from functools import wraps
from typing import Optional
from urllib.error import HTTPError

import discord
import openai
import requests
from discord.ext import commands
from emoji import is_emoji
from lingua import Language, LanguageDetectorBuilder

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from Levenshtein import distance as LDist
from deep_translator import GoogleTranslator

from cogs.utils.BotUtils import bot_utils as utils
from .utils import helper_functions as hf

MODCHAT_SERVER_ID = 257984339025985546
RYRY_SPAM_CHAN = 275879535977955330
JP_SERVER_ID = 189571157446492161
SP_SERVER_ID = 243838819743432704
CH_SERVER_ID = 266695661670367232
CL_SERVER_ID = 320439136236601344
RY_SERVER_ID = 275146036178059265
MODBOT_ID = 713245294657273856

ENG_ROLE = {
    266695661670367232: 266778623631949826,  # C-E Learning English Role
    320439136236601344: 474825178204078081  # r/CL Learning English Role
}
RYRY_RAI_BOT_ID = 270366726737231884
on_message_functions = []


def should_execute_task(allow_dms, allow_bots, allow_self, allow_message_types, main_rai_copy_only,
                        self, msg):
    """
    Determines if the task should execute based on message properties.
    """
    if not allow_dms and msg.channel.type == discord.ChannelType.private:
        return False
    if not allow_bots and msg.author.bot:
        return False
    if not allow_self and msg.author.id == self.bot.user.id:
        return False
    if msg.type not in (allow_message_types or []) + [discord.MessageType.default, discord.MessageType.reply]:
        return False
    
    # add your ID here if you want to test the functions unique to Rai
    # most functions that are blocked through this are meant to only be used on the Rai main bot
    # if used on a fork, they'll probably throw errors
    if main_rai_copy_only and self.bot.user.id not in [270366726737231884]:
        return False
    return True


def on_message_function(allow_dms: bool = False,
                        allow_bots: bool = False,
                        allow_self: bool = False,
                        allow_message_types: Optional[list[discord.MessageType]] = None,
                        main_rai_copy_only: bool = False) -> callable:
    def decorator(func: callable):
        # wrapper just to turn function into an asyncio task coroutine
        @wraps(func)  # Ensures the function retains its original name and docstring
        # needs to be async to work with asyncio.gather()
        async def wrapper(*args, **kwargs):
            if not should_execute_task(allow_dms, allow_bots, allow_self, allow_message_types,
                                       main_rai_copy_only, *args):
                return lambda *a, **kw: None  # No-op lambda for skipped tasks

            # time_task() is a wrapper that returns an uncalled async function definition
            # this is what asyncio_task needs, you're supposed to give it a function to call later
            task = utils.asyncio_task(time_task(func, *args, diff_threshold=5),
                                      task_name=f"on_message.{func.__name__}")
            return task

        # Replace `func` with `wrapper` in the registered functions
        on_message_functions.append({
            'func': wrapper,  # Use the wrapper instead of the original function
            'allow_dms': allow_dms,
            'allow_bots': allow_bots,
            'allow_self': allow_self,
            'main_rai_copy_only': main_rai_copy_only
        })

        return wrapper

    return decorator


def log_time(t_in, description: str):
    new_time = time.perf_counter()
    diff = new_time - t_in
    print(f"Elapsed time: {diff:.2f} seconds ({description})")
    return new_time


def time_task(func, *args, diff_threshold=0.5):
    @wraps(func)
    async def time_task_internal():
        t1 = time.perf_counter()
        result = await func(*args)
        t2 = time.perf_counter()
        diff = t2 - t1
        if diff > diff_threshold:
            print(
                f"on_message function {func.__name__} took {diff:.2f} seconds to run.")
        return result

    return time_task_internal


class Message(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ignored_characters = []
        self.sid = SentimentIntensityAnalyzer()

        global on_message_functions
        self.all_tasks = {func['func'] for func in on_message_functions}

        lingua_languages_one = [Language.SPANISH, Language.ENGLISH]
        lingua_languages_two = [Language.FRENCH, Language.ARABIC, Language.PORTUGUESE, Language.JAPANESE,
                                Language.TAGALOG, Language.GERMAN, Language.RUSSIAN, Language.ITALIAN]
        self.lingua_detector_eng_sp = LanguageDetectorBuilder.from_languages(
            *lingua_languages_one).build()
        self.lingua_detector_full = LanguageDetectorBuilder.from_languages(
            *(lingua_languages_one + lingua_languages_two)).build()

    @commands.Cog.listener()
    @hf.basic_timer(5)
    async def on_message(self, msg_in: discord.Message):
        rai_message = hf.RaiMessage(msg_in)
        try:
            await self.log_rai_tracebacks(rai_message)
        except Exception as e:
            print("Exception in log_rai_tracebacks:\n",
                  e, traceback.format_exc())
            # don't propagate error because it could lead to an infinite loop of Rai trying to log the error created
            # by the above function itself

        # if you want something to happen everytime you say something for debugging, put it here
        if rai_message.author.id == self.bot.owner_id:
            pass

        # ignore any non-standard discord user messages
        if rai_message.webhook_id:
            return
        if rai_message.guild and not isinstance(rai_message.author, discord.Member):
            return

        try:
            lang_check_task = utils.asyncio_task(
                time_task(self.lang_check, rai_message, diff_threshold=5))
            rai_message.detected_lang, rai_message.hardcore = await lang_check_task
            # will add slight delay as we wait for this

            # run all tasks in a batch
            await asyncio.gather(*(task(self, rai_message) for task in self.all_tasks))
        except Exception as e:
            # to avoid infinite loops: if Rai throws an error, log it and continue
            if rai_message.author.id == self.bot.user.id:
                print(
                    f"Exception in message sent by bot {rai_message.author.name}:\n", e)
                traceback.print_exc()
            else:
                raise

    async def lang_check(self, msg: hf.RaiMessage) -> tuple[Optional[str], bool]:
        """
        Will check if above 3 characters + hardcore, or if above 15 characters + stats
        :param msg:
        :return:
        """
        if not msg.guild:
            return None, None
        detected_lang = None
        hardcore = False
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
                if str(SP_SERVER_ID) not in self.bot.db['hardcore']:
                    return None, False
                if channel_id not in self.bot.db['hardcore'][str(SP_SERVER_ID)]['ignore']:
                    hardcore_role = msg.guild.get_role(
                        self.bot.db['hardcore'][str(SP_SERVER_ID)]['role'])
                    if hardcore_role in msg.author.roles:
                        check_lang = True
                        hardcore = True

        if str(msg.guild.id) in self.bot.stats:
            if len(stripped_msg) > 15 and self.bot.stats[str(msg.guild.id)].get('enable', None):
                check_lang = True

        if check_lang:
            try:
                if msg.guild.id in [SP_SERVER_ID, 1112421189739090101] and msg.channel.id != 817074401680818186:
                    if hasattr(self.bot, 'langdetect'):
                        detected_lang: Optional[str] = hf.detect_language(
                            stripped_msg)
                    else:
                        return None, False
                else:
                    return None, False
            except (HTTPError, TimeoutError, urllib.error.URLError):
                pass
        return detected_lang, hardcore

    @on_message_function(allow_bots=True)
    async def log_bot_messages(self, msg: hf.RaiMessage):
        if not getattr(self.bot, "bot_message_queue", None):
            self.bot.bot_message_queue = hf.MessageQueue(maxlen=100)
        if msg.author.bot:
            self.bot.bot_message_queue.add_message(msg)

    # don't run this as a typical on_message_function
    async def log_rai_tracebacks(self, msg: hf.RaiMessage):
        new_tracebacks_channel = self.bot.get_channel(1360884895957651496)
        old_traceback_channel_id = int(os.getenv("TRACEBACK_LOGGING_CHANNEL"))
        if msg.channel.id != old_traceback_channel_id:
            return
        if not msg.author == self.bot.user:
            return
        if 'rai_tracebacks' not in self.bot.db:
            self.bot.db['rai_tracebacks'] = []
        if not self.bot.openai:
            return
        # first part is a jump url before traceback
        traceback_msg_split = msg.content.split("```py")
        if len(traceback_msg_split) < 2:
            return
        # last three characters are final ```, take those off too
        traceback_msg = traceback_msg_split[1][:-3]

        # replace parts of the traceback that could change per traceback
        # any discord snowflake IDs
        traceback_msg = re.sub(r"\d{17,22}", "ID", traceback_msg)
        traceback_msg = re.sub(r"line \d+", "line LINE",
                               traceback_msg)  # line numbers
        traceback_msg = re.sub(
            r"File \".+?\"", "File \"FILE\"", traceback_msg)  # File names
        traceback_msg = re.sub(r"0x\w+", "0xHEX", traceback_msg)
        traceback_msg = re.sub(r"\d", "#", traceback_msg)

        # return if rai has seen this traceback before
        if traceback_msg in self.bot.db['rai_tracebacks']:
            return

        # Ask ChatGPT for summary of traceback
        messages = [{"role": "system", "content": "Please summarize the following Python traceback to be parsed "
                     "with a bot. All errors will be things happening in a Discord bot, "
                     "so you don't need to state that in the post title:\n"
                     "1) A title for the post for the error "
                     "(100 characters max, plain text)\n"
                     "(New line)"
                     "2) A summary for why the error happened, and which file / line the "
                     "error happened on. Recommendations for fixing "
                     "the error are not needed (2000 characters max, "
                     "new lines and Discord formatting allowed)"},
                    {"role": "user", "content": "< assume traceback content here >"},
                    {'role': 'assistant', 'content': "HTTPException in on_raw_message_delete from malformed footer URL"
                                                     "\nThis bug comes from an HTTPException in ... "
                                                     "(response continues). It occurred in cogs/modlog.py, line 1234"},
                    {'role': 'user', 'content': msg.content}]

        completion = await self.bot.openai.chat.completions.create(model="gpt-4o-mini", messages=messages)
        # Check the AI's response
        response_text = completion.choices[0].message.content
        post_name = response_text.split('\n')[0]
        if len(post_name) > 100:
            post_name = post_name[:100]
        post_content = '\n'.join(response_text.split('\n')[1:])
        post_content_split = utils.split_text_into_segments(post_content, 1990)

        self.bot.db['rai_tracebacks'].append(traceback_msg)
        try:
            thread = await new_tracebacks_channel.create_thread(name=post_name, content=msg.content, embeds=msg.embeds)
            # thread is actually a ThreadWithMessaged named tuple (thread, message)
            thread = thread.thread
        except discord.Forbidden as e:
            errmsg = f"Permission denied while creating thread in channel {new_tracebacks_channel.id}"
            e.add_note(errmsg)
            raise
        except discord.HTTPException as e:
            errmsg = f"HTTP error while creating thread: {e}"
            e.add_note(errmsg)
            raise
        for msg_split in post_content_split:
            await thread.send(msg_split)

    @on_message_function(allow_bots=True, main_rai_copy_only=True)
    async def replace_tatsumaki_posts(self, msg: hf.RaiMessage):
        if msg.content in ['t!serverinfo', 't!server', 't!sinfo', '.serverinfo', '.sinfo']:
            if msg.guild.id in [JP_SERVER_ID, SP_SERVER_ID, RY_SERVER_ID]:
                await msg.get_ctx()
                serverinfo: commands.Command = self.bot.get_command(
                    "serverinfo")
                # noinspection PyTypeChecker
                await msg.ctx.invoke(serverinfo)

    @on_message_function(allow_bots=True, main_rai_copy_only=True)
    async def post_modlog_in_reports(self, msg: hf.RaiMessage):
        mini_id = str(msg.id)[-3:]
        t1 = time.perf_counter()

        # old report system, modbot posts a message to a channel, then creates a thread on it
        if not isinstance(msg.channel, discord.Thread):
            if msg.author.id != MODBOT_ID:
                return  # only look for thread opening messages from modbot

            await asyncio.sleep(1)  # wait for the generation of the thread

            try:
                thread = msg.channel.get_thread(msg.id)
            except AttributeError:
                return  # failed to get thread, give up

            if thread:
                msg.channel = thread
                content = msg.content
            else:
                return  # failed to get thread, give up again

        # new report system, it's a forum channel so threads are created first, all messages are in threads
        else:
            content = msg.content

        if getattr(msg.channel.owner, "id", 0) != MODBOT_ID:  # modbot
            return
        if msg.author.id != MODBOT_ID:
            return

        t1 = log_time(t1, f"[{mini_id}] 1/2. after sleeping / setting up")

        # if it's the first message of the thread, ignore all the text past "Recent reports:"
        if msg.id == msg.channel.id:
            content = content.split("**__Recent reports:__**")[0]

        # if it's NOT the first message, then ignore the >>> <@ID>: portion of the message
        else:
            content = re.sub(r">>> <@!?\d{17,22}>: ", "", content)

        t1 = log_time(t1, f"[{mini_id}] 3. after splitting content")
        # content = msg.content[25:]

        modlog: commands.Command = self.bot.get_command("modlog")
        await msg.get_ctx()

        # Search for direct mentions of IDs
        user_ids = re.findall(r"<?@?!?(\d{17,19})>?", content)
        user_ids = set(user_ids)  # eliminate duplicate IDs
        for user_id in user_ids:
            try:
                user_id = int(user_id)
            except ValueError:
                continue
            user: discord.Member = msg.guild.get_member(user_id)
            if not user:
                try:
                    _: discord.User = await self.bot.fetch_user(user_id)
                    # if found, then keep going, I just want to see if the user *exists* or not
                except (discord.NotFound, discord.HTTPException):
                    continue
            # noinspection PyTypeChecker
            await msg.ctx.invoke(modlog, id_in=str(user_id))

        t1 = log_time(t1, f"[{mini_id}] 4. after searching for user IDs")

        # Search for usernames like Ryry013#1234
        usernames = re.findall(r"(\S+)#(\d{4})", content)
        usernames = set(usernames)  # eliminate duplicate usernames
        for username in usernames:
            user: discord.Member = discord.utils.get(
                msg.guild.members, name=username[0], discriminator=username[1])
            if user:
                if user.id in user_ids:
                    continue
                # noinspection PyTypeChecker
                await msg.ctx.invoke(modlog, id_in=str(user.id))
        t1 = log_time(t1, f"[{mini_id}] 5. command finish")

    @on_message_function(allow_bots=True)
    async def log_ciri_warnings(self, msg: hf.RaiMessage):
        if msg.guild.id != JP_SERVER_ID:
            return

        if not msg.content.startswith(","):
            return  # only look at ciri commands

        try:
            # minus first character for potential command prefix
            first_word = msg.content.split()[0][1:]
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

        await msg.get_ctx()
        for user_id in args.user_ids:
            user = msg.guild.get_member(int(user_id))
            if not user:
                try:
                    user = await self.bot.fetch_user(int(user_id))
                except discord.NotFound:
                    continue
            modlog_entry = hf.ModlogEntry(event=incident_type,
                                          user=user,
                                          guild=msg.guild,
                                          ctx=msg.ctx,
                                          silent=silent,
                                          reason=args.reason
                                          )
            modlog_entry.add_to_modlog()

    # ### Add to MessageQueue
    @on_message_function()
    async def add_to_message_queue(self, msg: hf.RaiMessage):
        # only add messages to queue for servers that have edited messages or deleted messages logging enabled
        if not any([self.bot.db['deletes'].get(str(msg.guild.id), {}).get('enable', False),
                    self.bot.db['edits'].get(str(msg.guild.id), {}).get('enable', False)]):
            if msg.guild.id != SP_SERVER_ID:
                return
        self.bot.message_queue.add_message(msg)

    # ### ban users from sensitive_topics on spanish server
    @on_message_function()
    async def ban_from_sens_top(self, msg: hf.RaiMessage):
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

    @on_message_function(main_rai_copy_only=True)
    async def wordsnake_channel(self, msg: hf.RaiMessage):
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
                self.bot.db['wordsnake'][word_to_add] = self.bot.db['wordsnake'].setdefault(
                    word_to_add, 0) + 1

            return self.bot.db['wordsnake'][word_to_add]

        new_word = msg.content.split('\n')[0].casefold()
        new_word = new_word.translate(str.maketrans(
            '', '', string.punctuation))  # remove punctuation
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

    @on_message_function()
    async def guild_stats(self, msg: hf.RaiMessage):
        config: dict = self.bot.db['guildstats']
        if str(msg.guild.id) not in config:
            config[str(msg.guild.id)] = {'messages': {}, 'commands': {}}
        config = config[str(msg.guild.id)]['messages']
        date_str = discord.utils.utcnow().strftime("%Y%m%d")
        config[date_str] = config.setdefault(date_str, 0) + 1

    @on_message_function()
    async def wordfilter(self, msg: hf.RaiMessage):
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
                        reason = f"Rai automatic word filter ban:\n{msg.content}"[
                            :512]
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

    # """Ping me if someone says my name"""

    @on_message_function(main_rai_copy_only=True)
    async def mention_ping(self, msg: hf.RaiMessage):
        cont = str(msg.content).casefold()

        if msg.author.id == 202995638860906496:
            return

        to_check_words = ['ryry', 'ryan', 'らいらい', 'ライライ', '来雷', '雷来']

        if msg.guild.id in [254463427949494292,  # french server
                            970703212107661402,  # english server
                            116379774825267202]:  # nihongo to eigo server
            # There's a popular user named "Ryan" in these two servers
            to_check_words.remove('ryan')

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
            # if word in cont.casefold(self, msg: hf.RaiMessage):
            if re.search(fr"(^| |\.){to_check_word}($|\W)", cont.casefold()):
                found_word = True

        if found_word:
            spam_chan = self.bot.get_channel(RYRY_SPAM_CHAN)
            await spam_chan.send(
                f'**By {msg.author.name} in {msg.channel.mention}** ({msg.channel.name}): '
                f'\n{msg.content}'
                f'\n{msg.jump_url}'[:2000])

    @on_message_function(main_rai_copy_only=True)
    async def ori_mention_ping(self, msg: hf.RaiMessage):
        cont = str(msg.content).casefold()
        ori_id = 581324505331400733

        if msg.author.id == ori_id:
            return

        to_check_words = ['ori', 'fireside', 'oriana', 'pasapalabra']

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

    # """Self mute"""

    @on_message_function()
    async def self_mute(self, msg: hf.RaiMessage):
        try:
            if self.bot.db['selfmute'][str(msg.guild.id)][str(msg.author.id)]['enable']:
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
        except KeyError:
            pass

    # """Owner self mute"""

    @on_message_function()
    async def owner_self_mute(self, msg: hf.RaiMessage):
        try:
            if self.bot.selfMute and msg.author.id == self.bot.owner_id:
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
        except AttributeError:
            pass

    # """check for mutual servers of banned users"""

    @on_message_function(main_rai_copy_only=True)
    async def check_guilds(self, msg: hf.RaiMessage):
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

    # """chinese server banned words"""

    # @on_message_function()
    # async def chinese_server_banned_words(self, msg: hf.RaiMessage):
    #     words = ['动态网自由门', '天安門', '天安门', '法輪功', '李洪志', 'Free Tibet', 'Tiananmen Square',
    #              '反右派鬥爭', 'The Anti-Rightist Struggle', '大躍進政策', 'The Great Leap Forward', '文化大革命',
    #              '人權', 'Human Rights', '民運', 'Democratization', '自由', 'Freedom', '獨立', 'Independence']
    #     if msg.guild.id not in [CH_SERVER_ID, 494502230385491978, CL_SERVER_ID, RY_SERVER_ID]:
    #         return
    #     word_count = 0
    #     for word in words:
    #         if word in msg.content:
    #             word_count += 1
    #         if word_count == 5:
    #             mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][str(msg.guild.id)])
    #             log_channel = self.bot.get_channel(self.bot.db['bans'][str(msg.guild.id)]['channel'])
    #             if discord.utils.utcnow() - msg.author.joined_at > timedelta(minutes=60):
    #                 await utils.safe_send(mod_channel,
    #                                       f"Warning: {msg.author.name} may have said the banned words spam message"
    #                                       f"\nMessage was posted in {msg.channel.mention}.  Message:"
    #                                       f"\n```{msg.content}"[:1995] + '```')
    #                 return
    #             try:
    #                 await msg.delete()
    #             except discord.Forbidden:
    #                 await utils.safe_send(mod_channel,
    #                                       "Rai is lacking the permission to delete messages for the Chinese "
    #                                       "spam message.")
    #             except discord.NotFound:
    #                 pass

    #             try:
    #                 await asyncio.sleep(3)
    #                 await msg.author.ban(reason=f"Automatic ban: Chinese banned words spam\n"
    #                                             f"{msg.content[:100]}", delete_message_seconds=1 * 60 * 60 * 24)
    #             except discord.Forbidden:
    #                 await utils.safe_send(mod_channel,
    #                                       "I tried to ban someone for the Chinese spam message, but I lack "
    #                                       "the permission to ban users.")

    #             await utils.safe_send(log_channel, f"Banned {msg.author} for the banned words spam message."
    #                                                f"\nMessage was posted in {msg.channel.mention}.  Message:"
    #                                                f"\n```{msg.content}"[:1850] + '```')

    #             return

    @on_message_function(main_rai_copy_only=True)
    async def mods_ping(self, msg: hf.RaiMessage):
        """
        This function triggers whenever someone pings the configured staff role in the guild.
        1. Checks that the guild is configured for staff pings (via self.bot.db['staff_ping']).
        2. Removes the staff role mention from the original message to avoid duplication.
        3. Extracts user mentions (IDs) from the message to pass them to staffping_code.
        4. Calls the staffping_code function to send a mod notification.
        5. Appends a synced reaction pair (notif, msg) if the bot uses reaction syncing.
        6. If multiple staff pings occur within 10 minutes in the same channel, skip re-summarizing.
        7. For specific servers (SP_SERVER_ID, JP_SERVER_ID), captures up to 50 preceding messages
           and sends them, along with instructions, to OpenAI for a concise summary of the chat context.
        8. If the AI responds with 'No summary available', the function exits quietly.
        9. Otherwise, the summary is split (if long) and sent to the staff ping message as replies.
        """

        # 1) Confirm the guild is configured for staff pings
        if str(msg.guild.id) not in self.bot.db['staff_ping']:
            return
        if 'channel' not in self.bot.db['staff_ping'][str(msg.guild.id)]:
            return

        config = self.bot.db['staff_ping'][str(msg.guild.id)]
        # try to get role id from staff_ping db
        staff_role_id = config.get("role")
        if not staff_role_id:  # no entry in staff_ping db
            staff_role_id = self.bot.db['mod_role'].get(
                str(msg.guild.id), {}).get("id")
            if isinstance(staff_role_id, list):
                staff_role_id = staff_role_id[0]
        if not staff_role_id:
            # This guild doesn't have a mod role or staff ping role set
            return

        staff_role = msg.guild.get_role(staff_role_id)
        if not staff_role:
            return

        # 2) Check if the staff role was actually pinged and remove it from the message content
        if f"<@&{staff_role_id}>" in msg.content:
            edited_msg = re.sub(
                rf'<?@?&?{str(staff_role_id)}>? ?', '', msg.content)
        else:
            return

        # 3) Extract user mentions (IDs) from the message for staffping_code
        user_id_regex = r"<?@?!?(\d{17,22})>? ?"
        users = re.findall(user_id_regex, edited_msg)
        users = ' '.join(users)
        edited_msg = re.sub(user_id_regex, "", edited_msg)

        # 4) Call staffping_code in the Interactions cog to send the staff notification
        # get cog, then the function inside the cog
        interactions = self.bot.get_cog("Interactions")
        await msg.get_ctx()
        notif = await interactions.staffping_code(ctx=msg.ctx, users=users, reason=edited_msg)

        # 5) Record synced reactions for the bot if using that system
        if hasattr(self.bot, 'synced_reactions'):
            self.bot.synced_reactions.append((notif, msg))
        else:
            self.bot.synced_reactions = [(notif, msg)]

        if not self.bot.openai:
            return  # if OpenAI is not set up, skip the rest of the function

        # Manage chatgpt_summaries to prevent multiple summaries in the same channel within 10 min
        # Only summarize in specific servers
        if msg.guild.id not in [SP_SERVER_ID, JP_SERVER_ID]:
            return
        if not hasattr(self.bot, 'chatgpt_summaries'):
            # initialize the list with the channel ID of the message and the timestamp
            self.bot.chatgpt_summaries = [
                (msg.channel.id, msg.created_at.timestamp())]
        else:
            # look to see if there's already an entry for this channel
            for channel_id, timestamp in self.bot.chatgpt_summaries:
                # if it's old, remove it and break; else skip to avoid re-summarizing
                if msg.channel.id == channel_id:
                    if msg.created_at.timestamp() - timestamp > 60 * 10:
                        self.bot.chatgpt_summaries.remove(
                            (channel_id, timestamp))
                    else:
                        return
            # add a new timestamp record for the current staff ping
            self.bot.chatgpt_summaries.append(
                (msg.channel.id, msg.created_at.timestamp()))

        # Summarization instructions to pass to the AI
        instructions = (
            "Someone pinged staff about a potential incident in a Discord text channel. There's three possibilities:\n"
            "1) There's a singular issue in the channel. Identify that singular main issue, "
            "and do not explain anything else. Help staff understand what was happening in the channel that directly "
            "caused the staff ping.\n"
            "2) Someone mistakenly pinged staff. If there's no relevant issue in the channel, end your response.\n"
            "3) Multiple people pinged staff: you will see the first staff ping above you. Do not respond in this case."
            "You will receive up to 50 messages above the ping (most of the beginning messages are likely unrelated). "
            "Here are some instructions:\n"
            "- This summary will help mods quickly understand the situation, so keep it VERY concise.\n"
            "- Identify the troll or bad actor relevant to the staff ping and describe briefly what they did wrong.\n"
            "- If a problematic discussion or argument caused someone to ping staff, "
            "summarize it, focusing on who's driving the conflict.\n"
            "- Ignore non-problematic or unrelated messages, like greetings or unrelated discussions.\n"
            "- Summarize only one main topic of conflict in your answer\n\n"
            "Examples of the three cases above: \n"
            "1a) [Unrelated messages], [Alice starts spamming messages], [@staff ping], Your response:"
            "'**Alice** is spamming messages and disrupting conversation'\n"
            "1b) [Unrelated messages], [Bob and Charlie start arguing], [@staff ping], Your response: "
            "**Bob** and **Charlie** are arguing about a rule interpretation. In particular, **Bob** "
            "was being particularly aggressive in the discussion, while **Charlie** was trying to deescalate.\n"
            "2) [Unrelated messages], [Nothing particular problematic], [suddenly, @staff ping], Your response: "
            "I could not find any issues in the channel. The ping may have been erroneous.\n"
            "3) [Unrelated messages], [some problem], [@staff ping], [shortly after, a second @staff ping], "
            "Your response: Ignoring second staff ping."
        )

        # Build the list of messages to send to OpenAI
        messages = [{'role': 'system', 'content': instructions}]

        temporary_message_queue = []
        # Capture 50 messages above the ping
        async for message in msg.channel.history(limit=50, oldest_first=False):
            # skip blank or whitespace-only messages
            if not message.content.strip():
                continue
            to_add_message = {
                'role': 'user',
            }
            content_dict = {"content": (message.content or '')[
                :750], 'author': message.author.display_name}
            if message.attachments:
                content_dict['attachments'] = [
                    a.filename for a in message.attachments]
            if message.embeds:
                content_dict['embeds'] = [e.to_dict() for e in message.embeds]
            to_add_message['content'] = str(content_dict)
            temporary_message_queue.append(to_add_message)

        temporary_message_queue = temporary_message_queue[::-1]
        messages.extend(temporary_message_queue)

        # 8) Send the messages to OpenAI in a try-except to gracefully handle failures
        CHATGPT_LOG_ID = 1351956893119283270
        await hf.segment_send(CHATGPT_LOG_ID, messages)
        try:
            completion = await self.bot.openai.chat.completions.create(model="gpt-4o-mini", messages=messages)
            await hf.segment_send(CHATGPT_LOG_ID, completion)
        except Exception as e:
            # Log or handle the error if needed
            await utils.safe_reply(notif, f"Failed to summarize logs. Sorry!\n`{e}`")
            self.bot.chatgpt_summaries.remove(
                (msg.channel.id, msg.created_at.timestamp()))
            raise

        # 9) Check the AI's response
        response_text = completion.choices[0].message.content
        to_send = utils.split_text_into_segments(response_text, 2000)

        # If the AI specifically says 'No summary available', just skip sending further
        if to_send[0].strip().lower().startswith('no summary available'):
            self.bot.chatgpt_summaries.remove(
                (msg.channel.id, msg.created_at.timestamp()))
            return

        # Send the summary in chunks if necessary
        for segment in to_send:
            await hf.send_to_test_channel(segment)

        # Remove the channel from the summaries list to allow future summaries
        await asyncio.sleep(60)
        self.bot.chatgpt_summaries.remove(
            (msg.channel.id, msg.created_at.timestamp()))

    @on_message_function()
    async def ping_sesion_mod(self, msg: hf.RaiMessage):
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
            if isinstance(msg.reference.resolved, discord.Message):
                await msg.reference.resolved.reply(ping)
            else:
                await msg.reply(ping)
        else:
            await msg.reply(ping)

        if str(SESION_MOD_ROLE_ID) in msg.content:
            await self.mods_ping(msg)

    @on_message_function()
    async def super_watch(self, msg: hf.RaiMessage):
        """
        This function will send a message to the super_watch channel if a user is mentioned in a message
        """
        try:
            config = self.bot.db['super_watch'][str(msg.guild.id)]
        except KeyError:
            return

        if not hasattr(msg.author, "guild"):
            return  # idk why this should be an issue, but it returned an error once

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
            minutes_ago_created = int(
                ((discord.utils.utcnow() - msg.author.created_at).total_seconds()) // 60)
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
        emb = discord.Embed(description=desc, color=0x00FFFF,
                            timestamp=discord.utils.utcnow())
        emb.set_footer(text=f"#{msg.channel.name}")

        link = f"\n([Jump URL]({msg.jump_url})"
        if which == 'sw':
            if config['users'].get(str(msg.author.id), None):
                link += f" － [Entry Reason]({config['users'][str(msg.author.id)]})"
        link += ')'
        emb.add_field(name="Message:",
                      value=msg.content[:1024 - len(link)] + link)

        await utils.safe_send(self.bot.get_channel(config['channel']), embed=emb)

    @on_message_function()
    async def vader_sentiment_analysis(self, msg: hf.RaiMessage):
        if not msg.content:
            return

        if not self.bot.stats.get(str(msg.guild.id), {'enable': False})['enable']:
            return

        if msg.detected_lang != 'en' and msg.guild.id != RY_SERVER_ID:
            return

        to_calculate = msg.content
        show_result = False
        if msg.content.startswith(";sentiment "):
            if not re.search(r"^;sentiment (?:@.*|<?@?!?\d{17,22}>?)", msg.content):
                to_calculate = msg.content.replace(";sentiment ", "")
                show_result = True

        sentiment = self.sid.polarity_scores(to_calculate)
        # above returns a dict like {'neg': 0.0, 'neu': 1.0, 'pos': 0.0, 'compound': 0.0}

        if show_result:
            pos = sentiment['pos']
            neu = sentiment['neu']
            neg = sentiment['neg']
            await utils.safe_send(msg.channel, f"Your sentiment score for the above message:"
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

    # """Message counting"""

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

    @on_message_function()
    async def msg_count(self, msg: hf.RaiMessage):
        if str(msg.guild.id) not in self.bot.stats:
            return
        if not self.bot.stats[str(msg.guild.id)]['enable']:
            return

        config = self.bot.stats[str(msg.guild.id)]
        author = str(msg.author.id)
        channel = msg.channel

        date_str = discord.utils.utcnow().strftime("%Y%m%d")
        if date_str not in config['messages']:
            config['messages'][date_str] = {}
        today = config['messages'][date_str]

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
        today[author]['channels'][channel] = today[author]['channels'].get(
            channel, 0) + 1

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
        last_message_timestamp = self.bot.last_message[author].setdefault(
            channel, 0)
        utcnow_timestamp = discord.utils.utcnow().timestamp()
        # if msg.author.id == self.bot.owner_id:
        #     await hf.send_to_test_channel(last_message_timestamp, utcnow_timestamp, author, channel)
        if utcnow_timestamp - last_message_timestamp > 60:
            today[author]['activity'][channel] = today[author]['activity'].get(
                channel, 0) + 5
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
                today[author]['emoji'][emoji] = today[author]['emoji'].get(
                    emoji, 0) + 1
        if msg.detected_lang:  # language is detected in separate lang_check function
            today[author].setdefault('lang', {})
            today[author]['lang'][msg.detected_lang] = today[author]['lang'].get(
                msg.detected_lang, 0) + 1

    @on_message_function()
    async def uhc_check(self, msg: hf.RaiMessage):
        await hf.uhc_check(msg)

    # @on_message_function()
    # async def cn_lang_check(self, msg, check_hardcore_role=True):
    #     if msg.guild.id not in [CH_SERVER_ID, CL_SERVER_ID]:
    #         return
    #     content = re.sub("^(>>>|>) .*$\n?", "", msg.content, flags=re.M)  # removes lines that start with a quote
    #     if len(content) > 3:
    #         if check_hardcore_role:
    #             try:
    #                 role = msg.guild.get_role(self.bot.db['hardcore'][str(msg.guild.id)]['role'])
    #             except (KeyError, AttributeError):
    #                 return

    #             if not hasattr(msg.author, 'roles'):
    #                 return
    #             if role not in msg.author.roles:
    #                 return

    #         learning_eng = msg.guild.get_role(ENG_ROLE[msg.guild.id])  # this function is only called for two guilds

    #         ratio = utils.jpenratio(content)
    #         if ratio is not None:  # it might be "0" so I can't do "if ratio"
    #             if learning_eng in msg.author.roles:
    #                 if ratio < .55:
    #                     try:
    #                         await msg.delete()
    #                     except discord.NotFound:
    #                         pass
    #                     if len(content) > 30:
    #                         await hf.long_deleted_msg_notification(msg)
    #             else:
    #                 if ratio > .45:
    #                     try:
    #                         await msg.delete()
    #                     except discord.NotFound:
    #                         pass
    #                     if len(content) > 60:
    #                         await hf.long_deleted_msg_notification(msg)

    # @on_message_function()
    # async def chinese_server_hardcore_mode(self, msg: hf.RaiMessage):
    #     if msg.guild.id in [CH_SERVER_ID, CL_SERVER_ID]:
    #         try:
    #             if msg.channel.id in self.bot.db['forcehardcore']:
    #                 await self.cn_lang_check(msg, check_hardcore_role=False)

    #             else:
    #                 if isinstance(msg.channel, discord.Thread):
    #                     channel_id = msg.channel.parent.id
    #                 elif isinstance(msg.channel, discord.TextChannel):
    #                     channel_id = msg.channel.id
    #                 else:
    #                     return
    #                 config = self.bot.db['hardcore'][str(CH_SERVER_ID)]['ignore']
    #                 if '*' not in msg.content and channel_id not in config:
    #                     await self.cn_lang_check(msg)
    #         except KeyError:
    #             self.bot.db['forcehardcore'] = []

    # """Spanish server hardcore"""

    @on_message_function()
    async def spanish_server_hardcore(self, msg: hf.RaiMessage):
        if not msg.hardcore:  # this should be set in the lang_check function
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
            if msg.detected_lang == 'es':
                try:
                    await msg.delete()
                except discord.NotFound:
                    return
                if len(msg.content) > 30:
                    await hf.long_deleted_msg_notification(msg)
        else:  # learning Spanish, delete all English
            if 'holi' in msg.content.casefold():
                return
            if msg.detected_lang == 'en':
                try:
                    await msg.delete()
                except discord.NotFound:
                    return
                if len(msg.content) > 30:
                    await hf.long_deleted_msg_notification(msg)

    @on_message_function()
    async def spanish_server_language_switch(self, msg: hf.RaiMessage):
        if not msg.detected_lang:
            return

        if "*" in msg.content or msg.content.startswith(">"):
            return  # exempt messages with "*" and quotes

        ch = self.bot.get_channel(739127911650557993)
        if msg.channel != ch:
            return

        sp_nat_role = msg.guild.get_role(243854128424550401)
        if sp_nat_role in msg.author.roles:
            if msg.detected_lang == 'es':
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass

        else:
            if msg.detected_lang == 'en':
                try:
                    await msg.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass

    @on_message_function()
    async def delete_messages_in_pinned_posts(self, msg: hf.RaiMessage):
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

        await msg.get_ctx()
        if not hf.submod_check(msg.ctx):
            await msg.delete()
            try:
                await msg.author.send(msg.content)
                await msg.author.send("Please try to resend the above message in a new post. You can "
                                      "not send messages in the top post.")
            except (discord.Forbidden, discord.HTTPException):
                return

    @on_message_function(main_rai_copy_only=True)
    async def spanish_server_staff_ping_info_request(self, msg: hf.RaiMessage):
        """This module will watch for users who ping Spanish server staff role (642782671109488641) and
        if they didn't include any text with their ping explaining the issue, it will ask them to do so in
        the future."""
        if msg.guild.id != SP_SERVER_ID:
            return  # only watch for pings in the Spanish server
        if "<@&642782671109488641>" not in msg.content:
            return  # only watch for pings to the staff role
        if msg.channel.category.name == "STAFF TEAM":
            return  # exempt staff channels

        # remove the staff ping from the message for the next part
        new_content = msg.content.replace("<@&642782671109488641>", "")

        # if the message without the ping is less than 4 characters, it's likely just a ping with no text
        if len(new_content) < 4:
            await msg.reply("- Thank you for pinging staff. In the future, please also include a description of "
                            "the issue when pinging Staff so moderators who "
                            "arrive into the channel can more quickly understand what is happening.\n"
                            "- Gracias por enviar un ping al staff. En el futuro, por favor, incluye también una "
                            "descripción del problema cuando envíes un ping al "
                            "Staff para que los moderadores que lleguen al canal puedan entender más rápidamente "
                            "lo que está pasando.")

    @on_message_function(allow_message_types=[discord.MessageType.auto_moderation_action],
                         main_rai_copy_only=True)
    async def spanish_server_scam_message_ban(self, msg: hf.RaiMessage):
        """This command will ban users who say common spam messages from hacked accounts in the Spanish server"""
        if msg.guild.id != SP_SERVER_ID:
            return
        if msg.channel.id != 808077477703712788:
            return
        if msg.type != discord.MessageType.auto_moderation_action:
            print("not auto moderation action")
            return  # only check for auto moderation actions

        content = msg.embeds[0].description

        # check for spam messages, returns list like ['steamcommunity.com', 'steamcommunity.com', ...]
        # found_bad_url will be True if a steamcommunity.com link is found modified from the real URL
        # example: 50$ gift https://steamrconmmunity.com/s/104291095314
        found_bad_url = False
        url_domains = re.findall(
            r"(?:https?://)?(?:www.)?([\w-]+\.com)", content)
        for domain in url_domains:
            if 0 < LDist(domain, "steamcommunity.com") < 4:
                found_bad_url = True
                break

        # find examples of embedded fake links (these always come with an @everyone ping)
        # example: @everyone steam gift 50$ - [steamcommunity.com/gift-card/pay/50](https://u.to/Qm7iIQ )
        embedded_steam_links = re.search(
            r"\[steamcommunity\.com[\w/=\-]*]\([\w/:.\-]* ?\)", content)
        if embedded_steam_links and "@everyone" in content:
            found_bad_url = True

        if not found_bad_url:
            print(f"no bad url found in {content}")
            return

        # if they've sent more than 4 messages, don't ban them (it could be a mistake)
        recent_messages_count = hf.count_messages(msg.author.id, msg.guild)
        if recent_messages_count > 4 and msg.author.id != 414873201349361664:
            print(f"more than 4 messages: {recent_messages_count}")
            return

        appeal_instructions = """If your account was hacked, please do the following steps before appealing your ban:
1) Change your password.
2) Enable two-factor authentication: https://support.discord.com/hc/en-us/articles/219576828-Setting-up-Multi-Factor-Authentication
3) Remove all applications from your profile: <https://www.iorad.com/player/2100432/Discord---How-to-deauthorize-an-app->

Si tu cuenta ha sido hackeada, por favor sigue los siguientes pasos antes de apelar tu baneo:
1) Cambia tu contraseña.
2) Activa la autenticación de dos factores: https://support.discord.com/hc/es/articles/219576828-Configurando-la-Autenticación-de-múltiples-factores
3) Elimina todas las aplicaciones de tu perfil: <https://www.iorad.com/player/2100432/Discord---How-to-deauthorize-an-app->

**__Appeal link: https://discord.gg/pnHEGPah8X__**"""

        try:
            await msg.author.send(appeal_instructions)
        except (discord.Forbidden, discord.HTTPException):
            pass

        incidents_channel = msg.guild.get_channel(808077477703712788)
        await utils.safe_send(incidents_channel, "⚠️ Banning above user / sending instructions for appeal ⚠️")

        # replace dangerous URLs from message with placeholder text
        content = re.sub(r"([\w-]+)\.com", "URL_REMOVED.com", content)
        # change something like [url_1](url_2) to [url_1](URL_REMOVED)
        content = re.sub(r"\[([\w/:.\-]+)]\([\w/:.\-]* ?\)",
                         r"[\1](URL_REMOVED)", content)

        try:
            await msg.author.ban(reason=f"Automatic ban: Hacked account. ({content[:150]}...)")
        except (discord.Forbidden, discord.HTTPException) as e:
            await incidents_channel.send(f"Failed to ban {msg.author} for spam message: `{e}`")
            await incidents_channel.send(f";ban {msg.author.id} Hacked account: {content[:150]}...")

    @on_message_function()
    async def antispam_check(self, msg: hf.RaiMessage):
        """"""
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

        while spam_count < config['message_threshold']:
            try:
                await self.bot.wait_for('message', timeout=config['time_threshold'], check=check)
            except asyncio.TimeoutError:
                return
            else:
                spam_count += 1

        reason = f"Antispam: \nSent the message `{msg.content[:400]}` {config['message_threshold']} " \
            f"times in {config['time_threshold']} seconds."

        action: str = config['action']

        time_ago: timedelta = discord.utils.utcnow() - msg.author.joined_at
        if ban_threshold := config.get('ban_override', 0):
            if time_ago < timedelta(minutes=ban_threshold):
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
                # will remove at end of function
                self.bot.spammer_mute.append(spammer_mute_entry)

            try:
                # execute the 1h mute command
                await msg.get_ctx()
                msg.ctx.author = msg.guild.me
                mute_command: commands.Command = self.bot.get_command('mute')
                # noinspection PyTypeChecker
                await msg.ctx.invoke(mute_command, args=f"1h {str(msg.author.id)} {reason}")

                # notify in mod channel if it is set
                if str(msg.guild.id) in self.bot.db['mod_channel']:
                    mod_channel = self.bot.get_channel(
                        self.bot.db['mod_channel'][str(msg.ctx.guild.id)])
                    if msg.guild.id == SP_SERVER_ID:
                        mod_channel = msg.guild.get_channel_or_thread(
                            297877202538594304)  # incidents channel
                    if mod_channel:
                        await utils.safe_send(mod_channel, msg.author.id,
                                              embed=utils.red_embed(
                                                  f"Muted for 1h: {str(msg.author)} for {reason}\n"
                                                  f"[Jump URL]({msg.jump_url})"))

            # skip if something went wrong
            except (discord.Forbidden, discord.HTTPException):
                pass

            # remove from temporary list after all actions done
            self.bot.spammer_mute.remove(spammer_mute_entry)

        def purge_check(m):
            return m.author == msg.author and m.content == msg.content

        await msg.channel.purge(limit=50, check=purge_check)

    @on_message_function(main_rai_copy_only=True)
    async def sp_serv_other_language_detection(self, msg: hf.RaiMessage):
        """Detect if a message in Spanish server is in another language"""
        log_channel = self.bot.get_channel(1335631538716545054)
        if not log_channel:
            return
        if not msg.content:
            return
        if msg.guild != log_channel.guild:
            return
        if not self.bot.openai:
            return

        # skip voice channels
        if msg.channel.type == discord.ChannelType.voice:
            return

        # exempt channels that allow other languages
        if msg.channel.id == 817074401680818186:  # other-languages channel
            return
        if getattr(msg.channel, "parent", None):
            if msg.channel.parent.id == 1141761988012290179:  # languages-forum channel
                return

        # remove emojis and urls from message to convert only words
        stripped_content = utils.rem_emoji_url(msg).strip()

        # this removes duplicated characters. for example, oooooooomg, or hahahahaha
        # it works if it's two characters alternating as well
        no_duplicates = re.sub(r"(.)\1+", r"\1", stripped_content)

        # only check messages long enough to provide meaningful results
        if len(no_duplicates) < 10:
            return

        # ignore messages that have latin letters (i.e., not japanese for example), but no spaces
        # these messages are probably something like "lmaoooooo" or "jajajajaja"
        if re.search(r"[a-zA-Z]", stripped_content):
            if stripped_content.count(" ") == 0:
                return

        _confidence_levels_one = self.lingua_detector_eng_sp.compute_language_confidence_values(
            stripped_content)
        confidence_levels_two = self.lingua_detector_full.compute_language_confidence_values(
            stripped_content)
        # looks like:
        # [ConfidenceValue(language=Language.ITALIAN, value=0.09408047930759932),
        # ConfidenceValue(language=Language.PORTUGUESE, value=0.08835661566397494),
        # ConfidenceValue(language=Language.SPANISH, value=0.08731281497274661), ...]

        # construct string and send to channel
        if (confidence_levels_two[0].language not in [Language.ENGLISH, Language.SPANISH]
                and confidence_levels_two[0].value > 0.9):
            chatgpt_prompt = [{"role": "system",
                               "content": "Please check the language of the following messages. Respond either "
                                          "'en', 'es', 'both' (a mix of English and Spanish), "
                                          "or 'other' if it's another language "
                                          "or 'unknown' if it just looks like gibberish. "
                                          "It's ok if it has one or two "
                                          "words in another language as long as the main content of the message is "
                                          "English or Spanish.\n"
                                          "Some messages have phonetic pronunciations of words, ignore the "
                                          "phonetic pronunciations.\n"
                                          "Since it's an online chatroom, some messages will have gibberish "
                                          "('blpppp'). Ignore those."},
                              {"role": "user", "content": "Hello, this is English"},
                              {"role": "assistant", "content": "en"},
                              {"role": "user", "content": "entonces háblame en català"},
                              {"role": "assistant", "content": "es"},
                              {"role": "user", "content": "virtue - vérchiu\nreconciliation - riconsiliéishon\nseparate - sépareit"},
                              {"role": "assistant", "content": "en"},
                              {"role": "user", "content": "blppppp lets go"},
                              {"role": "assistant", "content": "en"},
                              {"role": "user",
                                  "content": "L AS M NO ALSKWLAK / A HAHAGAHA / asfasef"},
                              {"role": "assistant", "content": "unknown"},
                              {"role": "user", "content": stripped_content}]
            chatgpt_result = await self.bot.openai.chat.completions.create(model="gpt-4o-mini", messages=chatgpt_prompt)
            CHATGPT_LOG_ID = 1351956893119283270
            await hf.segment_send(CHATGPT_LOG_ID, chatgpt_prompt, chatgpt_result)
            chatgpt_result = chatgpt_result.choices[0].message.content
            if chatgpt_result != "other":
                return

            # check if the author of the message is someone who can see this log channel
            # if they can see the log channel, don't ping them
            is_staff_member = log_channel.permissions_for(
                msg.author).read_messages
            if is_staff_member:
                author_name = msg.author.name
            else:
                author_name = msg.author.mention

            s = f"__{author_name} in {msg.jump_url}__\n> "
            s += msg.content.replace('\n', '\n> ')
            s += (f"\nSuspected language: {confidence_levels_two[0].language.name.capitalize()} "
                  f"({round(confidence_levels_two[0].value, 3)})")
            if msg.created_at.second % 10 in [0]:
                # randomly for messages that happen on seconds ending in "0" (1/10 chance), add extra information
                s += "\n__Information on below emojis__"
                s += "\n- ⚠️ - Format a warning to send to the user"
                s += "\n- ℹ️ - Format a friendlier modbot warning to send to the channel"
                s += "\n- ❌ - Delete this log (it was a mistaken detection)"
            sent_msg = await log_channel.send(s)
        else:
            return

        try:
            await sent_msg.add_reaction("⚠️")
            await sent_msg.add_reaction("ℹ️")
            await sent_msg.add_reaction("❌")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Check for ⚠️ ℹ️ ❌ reactions to messages in 1335631538716545054"""
        if payload.user_id == self.bot.user.id:
            return
        if payload.channel_id != 1335631538716545054:
            return

        other_language_logging_channel = self.bot.get_channel(
            1335631538716545054)
        if not other_language_logging_channel:
            return

        try:
            msg = await other_language_logging_channel.fetch_message(payload.message_id)
            source_msg_search = re.search(r"by <@!?(\d{17,22})> in (https://discord.com/channels/\d+/(\d+)/(\d+))",
                                          msg.content)
            try:
                channel_id = int(source_msg_search.group(3))
                source_channel = msg.guild.get_channel(channel_id)
                source_msg = await source_channel.fetch_message(int(source_msg_search.group(4)))
            except (AttributeError, ValueError, discord.NotFound):
                return

        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        if str(payload.emoji) == "⚠️":
            to_send = await self.format_rai_warning(source_msg)
            if to_send:
                await other_language_logging_channel.send(to_send)
        elif str(payload.emoji) == "ℹ️":
            to_send = await self.format_modbot_warning(source_msg)
            if to_send:
                await other_language_logging_channel.send(to_send)
        elif str(payload.emoji) == "❌":
            try:
                await msg.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def format_rai_warning(self, msg: discord.Message) -> str:
        """Read the content of the message and format a warning to send to the user"""
        acceptable_channel_one = self.bot.get_channel(817074401680818186)
        acceptable_channel_two = self.bot.get_channel(1141761988012290179)
        english = f"Please only use English or Spanish in this server. If you need to use another language, " \
            f"please use {acceptable_channel_one.mention} or {acceptable_channel_two.mention}."
        spanish = f"Por favor, solo usa inglés o español en este servidor. Si necesitas usar otro idioma, " \
            f"por favor usa {acceptable_channel_one.mention} o {acceptable_channel_two.mention}."

        english_native_role = msg.guild.get_role(243853718758359040)
        spanish_native_role = msg.guild.get_role(243854128424550401)
        if english_native_role in msg.author.roles:
            s = f";warn {msg.author.mention} {english}\n"
        elif spanish_native_role in msg.author.roles:
            s = f";warn {msg.author.mention} {spanish}\n"
        else:
            s = f";warn {msg.author.mention}\n- {english}\n- {spanish}\n"

        for line in msg.content.split('\n'):
            s += "> " + line + '\n'

        s += msg.jump_url

        return s

    async def format_modbot_warning(self, msg: discord.Message) -> str:
        """Read the content of the message and format a friendlier modbot warning to send to the channel.
        Modbot warning will be sent to the channel instead of the user (syntax: "_send channel_id msg")."""
        acceptable_channel_one = self.bot.get_channel(817074401680818186)
        acceptable_channel_two = self.bot.get_channel(1141761988012290179)
        english = f"Please only use English or Spanish in this server. If you need to use another language, " \
            f"please use {acceptable_channel_one.mention} or {acceptable_channel_two.mention}."
        spanish = f"Por favor, solo usa inglés o español en este servidor. Si necesitas usar otro idioma, " \
            f"por favor usa {acceptable_channel_one.mention} o {acceptable_channel_two.mention}."

        return f"_send {msg.channel.id} ℹ️\n- {english}\n- {spanish}"

    # @on_message_function()
    # async def chatgpt_new_user_moderation(self, msg: hf.RaiMessage):
    #     """This function will moderate new users in the chatgpt channel"""
    #     # https://platform.openai.com/docs/guides/moderation
    #     CHATGPT_LOG_ID = 1351956893119283270  # ID for channel for logs
    #     if msg.guild.id != SP_SERVER_ID:
    #         return
    #     if not self.bot.message_queue:
    #         return  # if the message queue is completely empty
    #     if not self.bot.openai:
    #         return
    #
    #     # if the user has sent more than 10 messages in the last month, don't moderate them
    #     messages_in_last_month = hf.count_messages(msg.author.id, msg.guild)
    #     if messages_in_last_month > 10:
    #         return
    #
    #     # get the list of messages the bot has seen
    #     cached_messages = self.bot.message_queue.find_by_author(msg.author.id)
    #     if not cached_messages:
    #         # the queue should at least have the current message
    #         await asyncio.sleep(0.1)
    #         cached_messages: list[hf.MiniMessage] = self.bot.message_queue.find_by_author(
    #             msg.author.id)
    #         if not cached_messages:
    #             return
    #
    #     messages = []
    #     message_contents = ""
    #     attachment_url = ""
    #     for message in cached_messages:
    #         if message.content:
    #             message_contents += f"[{message.created_at}]: {message.content}\n"
    #         for attachment in message.attachments:
    #             attachment_url = attachment['url']
    #     messages.append({"type": "text", "text": message_contents})
    #     if attachment_url:
    #         messages.append(
    #             {"type": "image_url", "image_url": {"url": attachment_url}})
    #     try:
    #         moderation_result = await self.bot.openai.moderations.create(model="omni-moderation-latest", input=messages)
    #     except openai.BadRequestError as e:
    #         # send to chatgpt logs channel
    #         await hf.segment_send(1351956893119283270, messages)
    #         moderation_result = None
    #         ignore_strings = ['invalid_image_format', 'image_url_unavailable', 'file_too_large', 'Failed to download']
    #         for i_string in ignore_strings:
    #             if i_string in str(e):
    #                 for m in messages:
    #                     if m['type'] == 'image_url':
    #                         messages.remove(m)
    #                         moderation_result = await self.bot.openai.moderations.create(
    #                             model="omni-moderation-latest", input=messages
    #                         )
    #         if not moderation_result:
    #             raise
    #     except Exception as e:
    #         await hf.segment_send(CHATGPT_LOG_ID, f"ERROR: `{e}`\n{messages}")
    #         raise
    #     # example response:
    #     # {
    #     #   "id": "modr-0d9740456c391e43c445bf0f010940c7",
    #     #   "model": "omni-moderation-latest",
    #     #   "results": [
    #     #     {
    #     #       "flagged": true,
    #     #       "categories": {
    #     #         "harassment": true,
    #     #         "harassment/threatening": true,
    #     #         "sexual": false,
    #     #         "hate": false,
    #     #         "hate/threatening": false,
    #     #         "illicit": false,
    #     #         "illicit/violent": false,
    #     #         "self-harm/intent": false,
    #     #         "self-harm/instructions": false,
    #     #         "self-harm": false,
    #     #         "sexual/minors": false,
    #     #         "violence": true,
    #     #         "violence/graphic": true
    #     #       },
    #     #       "category_scores": {
    #     #         "harassment": 0.8189693396524255,
    #     #         "harassment/threatening": 0.804985420696006,
    #     #         "sexual": 1.573112165348997e-6,
    #     #         "hate": 0.007562942636942845,
    #     #         "hate/threatening": 0.004208854591835476,
    #     #         "illicit": 0.030535955153511665,
    #     #         "illicit/violent": 0.008925306722380033,
    #     #         "self-harm/intent": 0.00023023930975076432,
    #     #         "self-harm/instructions": 0.0002293869201073356,
    #     #         "self-harm": 0.012598046106750154,
    #     #         "sexual/minors": 2.212566909570261e-8,
    #     #         "violence": 0.9999992735124786,
    #     #         "violence/graphic": 0.843064871157054
    #     #       },
    #     #       "category_applied_input_types": {
    #     #         "harassment": [
    #     #           "text"
    #     #         ],
    #     #         "harassment/threatening": [
    #     #           "text"
    #     #         ],
    #     #         "sexual": [
    #     #           "text",
    #     #           "image"
    #     #         ],
    #     #         "hate": [
    #     #           "text"
    #     #         ],
    #     #         "hate/threatening": [
    #     #           "text"
    #     #         ],
    #     #         "illicit": [
    #     #           "text"
    #     #         ],
    #     #         "illicit/violent": [
    #     #           "text"
    #     #         ],
    #     #         "self-harm/intent": [
    #     #           "text",
    #     #           "image"
    #     #         ],
    #     #         "self-harm/instructions": [
    #     #           "text",
    #     #           "image"
    #     #         ],
    #     #         "self-harm": [
    #     #           "text",
    #     #           "image"
    #     #         ],
    #     #         "sexual/minors": [
    #     #           "text"
    #     #         ],
    #     #         "violence": [
    #     #           "text",
    #     #           "image"
    #     #         ],
    #     #         "violence/graphic": [
    #     #           "text",
    #     #           "image"
    #     #         ]
    #     #       }
    #     #     }
    #     #   ]
    #     # }
    #     result = moderation_result.results[0]
    #     if not result.flagged:
    #         return
    #     await hf.segment_send(CHATGPT_LOG_ID, moderation_result)
    #
    #     # get flagged categories, when iterating, "category" is tuple of (str, bool) example: ('harassment', False)
    #     # categories['harassment'] for example returns TypeError: 'Categories' object is not subscriptable
    #     # need to do getattr(categories, 'harassment')
    #     flagged_categories = [category[0]
    #                           for category in result.categories if category[1]]
    #
    #     s = f"__ChatGPT moderation result__\nby {msg.author.mention} in {msg.jump_url}\n"
    #     s += "Flagged categories:\n"
    #     s += "Category scores:\n"
    #     over_80 = False
    #     for category, score in result.category_scores:
    #         if category in flagged_categories:
    #             s += f"- {category}: {score}\n"
    #             if score > 0.8:
    #                 over_80 = True
    #     s += f"Message content:\n>>> {message_contents}\n"
    #
    #     if over_80:
    #         watch_log_channel = self.bot.get_channel(704323978596188180)
    #         await utils.safe_send(watch_log_channel, s)

    @on_message_function()
    async def translate_other_lang_channel(self, msg: hf.RaiMessage):
        """Translate messages in other_languages channel in Spanish server"""
        other_languages_channel = self.bot.get_channel(817074401680818186)
        other_languages_forum = self.bot.get_channel(1141761988012290179)
        other_language_log_channel = self.bot.get_channel(1351961859070103637)
        if isinstance(msg.channel, discord.Thread):
            if msg.channel.parent != other_languages_forum:
                return
        elif msg.channel != other_languages_channel:
            return
        content = utils.rem_emoji_url(msg.content).strip()
        if not content:
            return
        if not other_language_log_channel:
            return

        # don't log for staff who can see the channel (because it'll ping them)
        is_staff_member = other_language_log_channel.permissions_for(
            msg.author).read_messages

        trans_task = utils.asyncio_task(lambda: GoogleTranslator(
            source='auto', target='en').translate(content))
        trans_task_2 = utils.asyncio_task(lambda: GoogleTranslator(
            source='auto', target='es').translate(content))
        try:
            translated = await trans_task
            translated_2 = await trans_task_2
        except requests.ConnectionError:
            return
        if not translated or not translated_2:
            return
        eng_dist = LDist(re.sub(r'\W', '', translated),
                         re.sub('\W', '', content))
        if eng_dist < 3:
            return
        if LDist(re.sub(r'\W', '', translated_2), re.sub('\W', '', content)) < 3:
            return
        s = (f"{msg.author.mention if not is_staff_member else msg.author.name} "
             f"in {msg.jump_url}\n")
        nl = '\n'  # python 3.10 does not allow backslahes in f-strings
        s += f"> {content.replace(nl, f'{nl}> ')}\n"
        s += f"> {translated.replace(nl, f'{nl}> ')}"
        try:
            await other_language_log_channel.send(s)
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(Message(bot))
