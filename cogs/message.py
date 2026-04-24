import asyncio
import re
import string
import time
import traceback
import urllib
from datetime import timedelta, datetime, timezone
from functools import wraps
from typing import Optional, Callable
from urllib.error import HTTPError

import discord
from discord.ext import commands
from emoji import is_emoji
from lingua import Language, LanguageDetectorBuilder

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from Levenshtein import distance as LDist
from deep_translator import GoogleTranslator
from deep_translator.exceptions import RequestError, TranslationNotFound
import requests
from socket import gaierror

from Rai import Rai
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

# Spanish server hardcore role IDs
SP_HARDCORE_ROLE_IDS = (526089127611990046, 1475913986561278024, 1475914271610110014)
on_message_functions = []


def should_execute_task(allow_bots, allow_self, allow_message_types, self, msg):
    """
    Determines if the task should execute based on message properties.
    """
    # if not allow_dms and msg.channel.type == discord.ChannelType.private:
    #     return False
    if not allow_bots and msg.author.bot:
        return False
    if not allow_self and msg.author.id == self.bot.user.id:
        return False
    if msg.type not in (allow_message_types or []) + [discord.MessageType.default, discord.MessageType.reply]:
        return False
    return True


def on_message_function(allow_bots: bool = False,
                        allow_self: bool = False,
                        allow_message_types: Optional[list[discord.MessageType]] = None,
                        time_threshold: float = 5.) -> Callable:
    def decorator(func: Callable):
        # wrapper just to turn function into an asyncio task coroutine
        @wraps(func)  # Ensures the function retains its original name and docstring
        # needs to be async to work with asyncio.gather()
        async def wrapper(*args, **kwargs):
            if not should_execute_task(allow_bots, allow_self, allow_message_types, *args):
                return lambda *a, **kw: None  # No-op lambda for skipped tasks

            # time_task() is a wrapper that returns an uncalled async function definition
            # this is what asyncio_task needs, you're supposed to give it a function to call later
            task = utils.asyncio_task(time_task(func, *args, time_threshold=time_threshold),
                                      task_name=f"on_message.{func.__name__}")
            return task

        # Replace `func` with `wrapper` in the registered functions
        if wrapper.__name__ not in [f['func'].__name__ for f in on_message_functions]:
            on_message_functions.append({
                'func': wrapper,  # Use the wrapper instead of the original function
                'allow_bots': allow_bots,
                'allow_self': allow_self,
            })

        return wrapper

    return decorator


def log_time(t_in, description: str):
    new_time = time.perf_counter()
    diff = new_time - t_in
    print(f"Elapsed time: {diff:.2f} seconds ({description})")
    return new_time


def time_task(func, *args, time_threshold: float = 0.5):
    @wraps(func)
    async def time_task_internal():
        t1 = time.perf_counter()
        result = await func(*args)
        t2 = time.perf_counter()
        diff = t2 - t1
        if diff > time_threshold:
            print(
                f"on_message function {func.__name__} took {diff:.2f} seconds to run.")
        return result

    return time_task_internal


def sanitize_scam_content(content: str) -> str:
    content = re.sub(r"([\w-]+)\.com", "URL_REMOVED.com", content)
    content = re.sub(r"\[([\w/:.\-]+)]\([\w/:.\-]* ?\)", r"[\1](URL_REMOVED)", content)
    return content


def extract_scam_message_and_rule(content: str) -> tuple[str, str]:
    rule_match = re.search("Rule:\\s*([^\\u2022\\n]+)", content)
    rule = rule_match.group(1).strip() if rule_match else "Unknown AutoMod rule"

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    keyword_line_index = next((i for i, line in enumerate(lines) if "Keyword:" in line), None)

    if keyword_line_index is not None and keyword_line_index > 0:
        message_text = lines[keyword_line_index - 1]
    elif len(lines) >= 2:
        message_text = lines[1]
    else:
        message_text = content.strip()

    return message_text, rule


def extract_automod_keyword(content: str) -> str:
    keyword_match = re.search("Keyword:\\s*([^\\u2022\\n]+)", content)
    if not keyword_match:
        return ""

    return keyword_match.group(1).strip().strip("*")


def parse_automod_timeout_duration(message: discord.Message) -> timedelta:
    if not message.embeds:
        return timedelta(0)
    
    embed = message.embeds[0]
    if not embed.fields:
        return timedelta(0)
    
    timeout_duration_seconds = 0
    for field in embed.fields:
        if field.name == 'timeout_duration':
            timeout_duration_seconds = int(field.value)
    
    return timedelta(seconds=timeout_duration_seconds)


SCAM_APPEAL_INSTRUCTIONS = \
"""**You've been banned from the Spanish-English Language Exchange.**

If your account was hacked, please do the following steps before appealing your ban:
1. Change your password.
2. Enable two-factor authentication: <https://support.discord.com/hc/en-us/articles/219576828-Setting-up-Multi-Factor-Authentication>
3. Remove all applications from your profile: <https://www.iorad.com/player/2100432/Discord---How-to-deauthorize-an-app->

Si tu cuenta ha sido hackeada, por favor sigue los siguientes pasos antes de apelar tu baneo:
1. Cambia tu contraseña.
2. Activa la autenticación de dos factores: <https://support.discord.com/hc/es/articles/219576828-Configurando-la-Autenticación-de-múltiples-factores>
3. Elimina todas las aplicaciones de tu perfil: <https://www.iorad.com/player/2100432/Discord---How-to-deauthorize-an-app->

**__ Appeal link: https://discord.gg/pnHEGPah8X __**"""


def scam_ban_reason(content: str) -> str:
    sanitized_content = sanitize_scam_content(content)
    return f"Automatic ban: Hacked account. ({sanitized_content[:150]}...)"


class ScamBanPromptView(utils.RaiView):
    def __init__(self,
                 bot: Rai,
                 target: discord.Member,
                 ban_reason: str,
                 content: str):
        super().__init__(timeout=24 * 60 * 60)
        self.bot = bot
        self.target = target
        self.ban_reason = ban_reason
        self.content = content
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if hf.trial_helper_check(interaction):
            return True

        await interaction.response.send_message(
            "Only Spanish server trial staff or above can use this button.",
            ephemeral=True
        )
        return False

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Ban User", style=discord.ButtonStyle.danger)
    async def ban_user(self, interaction: discord.Interaction, _: discord.ui.Button):
        silent = True
        try:
            await self.target.send(SCAM_APPEAL_INSTRUCTIONS)
            silent = False
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            await interaction.guild.ban(self.target, reason=self.ban_reason)
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.response.send_message(
                f"I couldn't ban {self.target.mention}: `{e}`",
                ephemeral=True
            )
            return

        hf.add_to_modlog(None, [self.target, interaction.guild], 'Ban', self.ban_reason, silent, None)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=(f"Banned {self.target.mention}.\n"
                     f"Reason: `{self.ban_reason[:400]}`\n"
                     f"-# Incident handled by {interaction.user.mention}"),
            view=self
        )
        self.stop()

    @discord.ui.button(label="False Alarm", style=discord.ButtonStyle.secondary)
    async def false_alarm(self, interaction: discord.Interaction, _: discord.ui.Button):
        try:
            await self.target.edit(
                timed_out_until=None,
                reason="False alarm on AutoMod scam timeout"
            )
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.response.send_message(
                f"I couldn't remove the timeout from {self.target.mention}: `{e}`",
                ephemeral=True
            )
            return

        guild_modlog = self.bot.db['modlog'].setdefault(str(interaction.guild.id), {'channel': None})
        user_modlog = guild_modlog.setdefault(str(self.target.id), [])
        for i in range(len(user_modlog) - 1, -1, -1):
            entry = user_modlog[i]
            if entry['type'] != 'AutoMod Timeout':
                continue
            # self.content is the reported message content
            # entry['reason'] is the stored content in the database
            # however, the stored content has the automod keyword bolded like **keyword**
            if self.content in re.sub(r'\*\*(.*?)\*\*', r'\1', entry['reason']):
                del user_modlog[i]
                break

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=f"Marked as false alarm. I've removed the timeout from {self.target.mention} "
                    f"and deleted that modlog entry.\n"
                    f"-# Incident handled by {interaction.user.mention}",
            view=self
        )
        self.stop()


async def handle_scam_timeout_followup(bot: Rai, msg: hf.RaiMessage, content: str, ban_reason: str,
                                       timeout_duration: timedelta) -> None:
    if timeout_duration <= timedelta(minutes=5):
        return

    prompt_text = (
        "Shall I ban the above user with the following ban reason?\n"
        f"`{ban_reason[:400]}`\n"
        f"-# I'll send instructions on how to appeal the ban as well."
    )
    view = ScamBanPromptView(bot, msg.author, ban_reason, content)
    prompt_msg = await msg.reply(prompt_text, view=view, mention_author=False)
    view.message = prompt_msg


class Message(commands.Cog):
    def __init__(self, bot: Rai):
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
        if not msg_in.guild:
            # RaiMessage assumes all messages are in a guild
            return
        
        rai_message = hf.RaiMessage(msg_in)

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
                time_task(self.lang_check, rai_message, time_threshold=5))
            rai_message.detected_lang, rai_message.hardcore = await lang_check_task
            # will add slight delay as we wait for this

            # run all tasks in a batch
            await asyncio.gather(*(task(self, rai_message) for task in self.all_tasks))
        except Exception as e:
            # to avoid infinite loops: if Rai throws an error, log it and continue
            if rai_message.author.id == self.bot.user.id:  # pyright: ignore[reportOptionalMemberAccess]
                print(
                    f"Exception in message sent by bot {rai_message.author.name}:\n", e)
                traceback.print_exc()
            else:
                raise

    async def lang_check(self, msg: hf.RaiMessage) -> tuple[str | None, bool | None]:
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
            if stripped_msg[0] not in '=;>' and len(stripped_msg) > 15:
                if isinstance(msg.channel, discord.Thread):
                    channel_id = msg.channel.parent.id  # pyright: ignore[reportOptionalMemberAccess]
                elif isinstance(msg.channel, (discord.TextChannel, discord.VoiceChannel)):
                    channel_id = msg.channel.id
                else:
                    return None, False

                # check for unregistered DB
                if str(SP_SERVER_ID) not in self.bot.db['hardcore']:
                    return None, False

                # check if ignored channel
                if channel_id in self.bot.db['hardcore'][str(SP_SERVER_ID)]['ignore']:
                    pass

                # check if ignored category
                elif getattr(msg.channel.category, 'id', 0) in self.bot.db['hardcore'][str(SP_SERVER_ID)]['ignore']:
                    pass

                # else, process hardcore roles
                else:
                    hardcore_role = msg.guild.get_role(SP_HARDCORE_ROLE_IDS[0])
                    super_hardcore_role = msg.guild.get_role(SP_HARDCORE_ROLE_IDS[1])
                    ultra_hardcore_role = msg.guild.get_role(SP_HARDCORE_ROLE_IDS[2])
                    all_roles = [hardcore_role, super_hardcore_role, ultra_hardcore_role]
                    for r in all_roles:
                        if r in msg.author.roles:
                            check_lang = True
                            hardcore = True
                            break

        if str(msg.guild.id) in self.bot.stats:
            if len(stripped_msg) > 15 and self.bot.stats[str(msg.guild.id)].get('enable', None):
                check_lang = True

        # make exception for a reply starting with "> "... it's probably someone correcting someone else
        if msg.reference and msg.content.startswith("> "):
            check_lang = False

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

    @on_message_function()
    async def test_long_function(self, msg: hf.RaiMessage):
        # only work on messages from bot owner
        if msg.author.id != self.bot.owner_id:
            return
        if msg.channel.id != 1330798440052949024:
            return
        time.sleep(5)

    @on_message_function()
    async def test_async_wait(self, msg: hf.RaiMessage):
        # only work on messages from bot owner
        if msg.author.id != self.bot.owner_id:
            return
        if msg.channel.id != 1331494671620509699:
            return
        await asyncio.sleep(5)

    @on_message_function(allow_bots=True)
    async def log_bot_messages(self, msg: hf.RaiMessage):
        if not getattr(self.bot, "bot_message_queue", None):
            self.bot.bot_message_queue = hf.MessageQueue(maxlen=100)
        if msg.author.bot:
            self.bot.bot_message_queue.add_message(msg)

    @on_message_function(allow_bots=True)
    async def replace_tatsumaki_posts(self, msg: hf.RaiMessage):
        if msg.content in ['t!serverinfo', 't!server', 't!sinfo', '.serverinfo', '.sinfo']:
            if msg.guild.id in [JP_SERVER_ID, SP_SERVER_ID, RY_SERVER_ID]:
                await msg.get_ctx()
                serverinfo: commands.Command = self.bot.get_command(
                    "serverinfo")
                # noinspection PyTypeChecker
                await msg.ctx.invoke(serverinfo)

    @on_message_function(allow_bots=True)
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

        # if it's the first message of the thread, ignore all the text past "Recent reports:"
        if msg.id == msg.channel.id:
            content = content.split("**__Recent reports:__**")[0]

        # if it's NOT the first message, then ignore the >>> <@ID>: portion of the message
        else:
            content = re.sub(r">>> <@!?\d{17,22}>: ", "", content)

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

    @on_message_function()
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

    @on_message_function()
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

    @on_message_function()
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

    @on_message_function()
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
            ai_cog = self.bot.get_cog("AI")
            if ai_cog:
                await ai_cog.mods_ping(msg)

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
        user_id = str(msg.author.id)
        user_sentiment = config.get(user_id)

        if isinstance(user_sentiment, list):
            user_sentiment = {
                'count': len(user_sentiment),
                'sum': float(sum(user_sentiment)),
            }
        elif not isinstance(user_sentiment, dict):
            user_sentiment = {'count': 0, 'sum': 0.0}

        count = max(int(user_sentiment.get('count', 0)), 0)
        total = float(user_sentiment.get('sum', 0.0))

        if count < 1000:
            count += 1
            total += sentiment
        else:
            count = 1000
            total = total - (total / 1000) + sentiment

        config[user_id] = {'count': count, 'sum': total}

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
    async def no_filter_hc(self, msg: hf.RaiMessage):
        if msg.channel.id == 193966083886153729:
            jpRole = msg.guild.get_role(196765998706196480)
            enRole = msg.guild.get_role(197100137665921024)
            if jpRole in msg.author.roles and enRole in msg.author.roles:
                return
            ratio = utils.jpenratio(msg.content.casefold())
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

    @on_message_function()
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

    @on_message_function(allow_message_types=[discord.MessageType.auto_moderation_action])
    async def spanish_server_scam_message_ban(self, msg: hf.RaiMessage):
        """This command will ban users who say common spam messages from hacked accounts in the Spanish server"""
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

        ban_reason = scam_ban_reason(content)
        timeout_duration = parse_automod_timeout_duration(msg)

        if not found_bad_url:
            if timeout_duration > timedelta(minutes=5):
                await handle_scam_timeout_followup(self.bot, msg, content, ban_reason,
                                                   timeout_duration)
            else:
                print(f"no bad url found in {content}")
            return

        # if they've sent more than 4 messages, don't ban them (it could be a mistake)
        recent_messages_count = hf.count_messages(msg.author.id, msg.guild)
        if recent_messages_count > 4 and msg.author.id != 414873201349361664:
            print(f"more than 4 messages: {recent_messages_count}")
            if timeout_duration > timedelta(minutes=5):
                await handle_scam_timeout_followup(self.bot, msg, content, ban_reason,
                                                   timeout_duration)
            return

        try:
            await msg.author.send(SCAM_APPEAL_INSTRUCTIONS)
        except (discord.Forbidden, discord.HTTPException):
            pass

        incidents_channel = msg.guild.get_channel(808077477703712788)
        await utils.safe_send(incidents_channel, "⚠️ Banning above user / sending instructions for appeal ⚠️")

        try:
            await msg.author.ban(reason=ban_reason)
        except (discord.Forbidden, discord.HTTPException) as e:
            await incidents_channel.send(f"Failed to ban {msg.author} for spam message: `{e}`")
            await incidents_channel.send(f";ban {msg.author.id} Hacked account: {content[:150]}...")
            if timeout_duration > timedelta(minutes=5):
                await handle_scam_timeout_followup(self.bot, msg, content, ban_reason,
                                                   timeout_duration)

    @on_message_function(time_threshold=10.5)
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
        seen_channel_ids = {msg.channel.id}
        matched_messages = [msg]

        def normalize_url(url: str) -> str:
            if not url:
                return ""
            split_url = urllib.parse.urlsplit(url)
            return split_url.path or url

        def message_signature(message: hf.RaiMessage) -> tuple:
            attachments = tuple(
                (
                    getattr(attachment, "id", None),
                    getattr(attachment, "filename", ""),
                    normalize_url(getattr(attachment, "url", "")),
                    normalize_url(getattr(attachment, "proxy_url", "")),
                )
                for attachment in getattr(message, "attachments", [])
            )
            embeds = tuple(
                normalize_url(getattr(embed, "url", ""))
                for embed in getattr(message, "embeds", [])
            )
            return (
                getattr(message.guild, "id", None),
                getattr(message.author, "id", None),
                message.content,
                attachments,
                embeds,
            )

        target_signature = message_signature(msg)

        def check(m):
            return message_signature(m) == target_signature and m.channel.id not in seen_channel_ids

        while spam_count < config['message_threshold']:
            try:
                matched_msg = await self.bot.wait_for('message', timeout=config['time_threshold'], check=check)
            except asyncio.TimeoutError:
                return
            else:
                matched_messages.append(matched_msg)
                if matched_msg.channel.id not in seen_channel_ids:
                    seen_channel_ids.add(matched_msg.channel.id)
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
                            808077477703712788)  # incidents channel
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

        for matched_msg in matched_messages:
            try:
                await matched_msg.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
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
        if not acceptable_channel_one or not acceptable_channel_two:
            raise Exception("The channels in this command have become invalid, fix this command.")
        english = f"Please only use English or Spanish in this server. If you need to use another language, " \
            f"please use {acceptable_channel_one.mention} or {acceptable_channel_two.mention}."
        spanish = f"Por favor, solo usa inglés o español en este servidor. Si necesitas usar otro idioma, " \
            f"por favor usa {acceptable_channel_one.mention} o {acceptable_channel_two.mention}."

        return f"_send {msg.channel.id} ℹ️\n- {english}\n- {spanish}"

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
        assert type(msg.author) == discord.Member
        is_staff_member = other_language_log_channel.permissions_for(
            msg.author).read_messages

        trans_task = utils.asyncio_task(lambda: GoogleTranslator(
            source='auto', target='en').translate(content))
        trans_task_2 = utils.asyncio_task(lambda: GoogleTranslator(
            source='auto', target='es').translate(content))
        try:
            translated = await trans_task
            translated_2 = await trans_task_2
        except (gaierror, requests.exceptions.RequestException, RequestError, TranslationNotFound):
            return
        if not translated or not translated_2:
            return
        eng_dist = LDist(re.sub(r'\W', '', translated),
                         re.sub(r'\W', '', content))
        if eng_dist < 3:
            return
        if LDist(re.sub(r'\W', '', translated_2),
                 re.sub(r'\W', '', content)) < 3:
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
        
    async def _get_selfmute_expiry_for_member(
        self,
        member: discord.Member,
    ) -> Optional[datetime]:
        """Return the datetime when this member's self-mute/timeout expires, or None."""
        guild_id = str(member.guild.id)
        user_id = str(member.id)

        # 1) Check Rai's selfmute DB
        try:
            guild_cfg = self.bot.db['selfmute'][guild_id]
            user_cfg = guild_cfg.get(user_id)
            
            # confirm user is actually muted currently
            if not member.is_timed_out():
                del user_cfg  # remove selfmute entry if not muted
                return
            
            if user_cfg:
                unmute_time = user_cfg.get('time')
                if isinstance(unmute_time, int):
                    # stored as unix timestamp
                    return datetime.fromtimestamp(
                        unmute_time, tz=timezone.utc
                    )
                else:
                    # stored as string timestamp (older format)
                        return datetime.strptime(
                            unmute_time, "%Y/%m/%d %H:%M UTC"
                        ).replace(tzinfo=timezone.utc)
        except KeyError:
            # guild or selfmute entry missing
            pass
        except Exception:
            # be defensive, don't crash on bad data
            pass

        return None

    @on_message_function()
    async def selfmute_mention_notifier(self, msg: hf.RaiMessage):
        """
        If someone mentions a self-muted user, notify in-channel that the user is self-muted
        and when their self-mute/timeout expires.
        """
        # Only in guilds
        if not msg.guild or msg.author.bot:
            return
        
        # Only in certain guilds
        if msg.guild.id not in [JP_SERVER_ID, SP_SERVER_ID, CH_SERVER_ID]:
            return

        # Collect unique mentioned members
        mentioned_members: set[discord.Member | discord.User] = set(msg.mentions)
        if not mentioned_members:
            return

        now = discord.utils.utcnow()

        for mentioned in mentioned_members:
            if not isinstance(mentioned, discord.Member):
                return
            
            expiry = await self._get_selfmute_expiry_for_member(mentioned)
            if not expiry:
                continue  # not self-muted / no timeout

            # If somehow expiry is in the past, skip
            if expiry <= now:
                continue

            # Format as Discord timestamp so it shows both absolute and relative time
            ts = int(expiry.timestamp())
            # Example: "expires at <t:...> (<t:...:R>)"
            text = (
                f"{mentioned.mention} is currently self-muted and may not respond. "
                f"Their self-mute expires at <t:{ts}> (<t:{ts}:R>)."
            )

            try:
                await utils.safe_reply(msg, text, mention_author=False,
                                      allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.HTTPException):
                # If we can't speak in channel, just fail silently
                pass


async def setup(bot):
    await bot.add_cog(Message(bot))