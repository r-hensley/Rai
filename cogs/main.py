import logging, logging.handlers
import json
import sys
import os
import traceback

import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime
from .utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils


# class IgnoreRateLimitFilter(logging.Filter):
#     def filter(self, record):
#         logging.warning("TEST")
#         if "We are being rate limited" in record.getMessage():
#             print("Ignoring: We are being rate limited.")
#             return False
#         if "Shard ID None has successfully RESUMED" in record.getMessage():
#             print("Ignoring: Shard has successfully RESUMED.")
#             return False
#         return True


# logging.basicConfig(level=logging.WARNING)
# logger = logging.getLogger('discord')
# logger.setLevel(logging.INFO)
# handler = logging.FileHandler(
#     filename=f'{dir_path}/log/{discord.utils.utcnow().strftime("%y%m%d_%H%M")}.log',
#     encoding='utf-8',
#     mode='a')
# handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
# logger.addHandler(handler)

# Get the logger for "discord.http"
# logger = logging.getLogger('discord.http')

# logger = logging.getLogger('discord')
# logger.setLevel(logging.WARNING)
# logging.getLogger('discord.http').setLevel(logging.INFO)
#
# handler = logging.handlers.RotatingFileHandler(
#     filename='discord.log',
#     encoding='utf-8',
#     maxBytes=32 * 1024 * 1024,  # 32 MiB
#     backupCount=5,  # Rotate through 5 files
# )
#
# dt_fmt = '%Y-%m-%d %H:%M:%S'
# formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
# handler.setFormatter(formatter)
# logger.addHandler(handler)
#
# # Add the filter to the logger
# logger.addFilter(IgnoreRateLimitFilter())

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
JP_SERV_ID = 189571157446492161
SPAN_SERV_ID = 243838819743432704
M_SERVER = 257984339025985546
NADEKO_ID = 116275390695079945
SPAN_WELCOME_CHAN_ID = 243838819743432704
JP_SERV_JHO_ID = 189571157446492161
BANS_CHANNEL_ID = 329576845949534208
ABELIAN_ID = 414873201349361664

TRACEBACK_LOGGING_CHANNEL = int(os.getenv("TRACEBACK_LOGGING_CHANNEL"))
BOT_TEST_CHANNEL = int(os.getenv("BOT_TEST_CHANNEL"))


class Main(commands.Cog):
    """Main bot-central functions (error-handling, etc.)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.on_error = self.on_error

    def cog_load(self):
        self.logging_setup()

    @commands.Cog.listener()
    async def on_ready(self):
        # if not self.stats:
        #     hf.load_stats(self)

        await hf.load_language_detection_model()
        self.bot.language_detection = True

        try:
            AppInfo = await self.bot.application_info()
            self.bot.owner_id = AppInfo.owner.id
        except discord.HTTPException:
            pass

        test_channel = self.bot.get_channel(BOT_TEST_CHANNEL)

        if test_channel:
            ctxmsg = await test_channel.send("Almost done!")
            self.bot.ctx = await self.bot.get_context(ctxmsg)
            sync: commands.Command = self.bot.get_command("sync")
            await self.bot.ctx.invoke(sync)
        else:
            ctxmsg = self.bot.ctx = None

        try:  # in on_ready because there are many tasks in here that require a loaded bot
            await self.bot.load_extension('cogs.background')
            print('Loaded cogs.background')
        except Exception:
            print('Failed to load extension cogs.background.', file=sys.stderr)
            traceback.print_exc()

        print(f"Bot loaded (discord.py version {discord.__version__})")

        t_finish = datetime.now()

        if ctxmsg:
            await ctxmsg.edit(content=f'Bot loaded (time: {t_finish - self.bot.t_start})')

        await self.bot.change_presence(activity=discord.Game(';help for help'))

        if not self.database_backups.is_running():
            print("Starting database backups")
            self.database_backups.start()

        # build MessageQueue
        if not hasattr(self.bot, "message_queue"):
            self.bot.message_queue = hf.MessageQueue(maxlen=100000)

    def logging_setup(self):
        class IgnoreRateLimitFilter(logging.Filter):
            def filter(self, record):
                if "We are being rate limited" in record.getMessage():
                    print("Ignoring: We are being rate limited.")
                    return False
                if "Shard ID None has successfully RESUMED" in record.getMessage():
                    print("Ignoring: Shard has successfully RESUMED.")
                    return False
                return True
            
        class IgnoreAsyncioSSLHandshakeError(logging.Filter):
            def filter(self, record):
                # ignore these three logs:
                # DEBUG:asyncio:<asyncio.sslproto.SSLProtocol object at 0x0000017D8B142D70> starts SSL handshake
                # DEBUG:asyncio:<asyncio.sslproto.SSLProtocol object at 0x0000017D8B142D70>: SSL handshake took 31.0 ms
                # DEBUG:asyncio:<asyncio.TransportSocket fd=2628, family=AddressFamily.AF_INET,
                #   type=SocketKind.SOCK_STREAM, proto=6, laddr=('10.110.118.58', 60112),
                #   raddr=('162.159.135.232', 443)> connected to None:None:
                #   (<asyncio.sslproto._SSLProtocolTransport object at 0x0000017D8B959F60>,
                #   <aiohttp.client_proto.ResponseHandler object at 0x0000017D8B959E40>)
                ignored_strings = ["starts SSL handshake", "SSL handshake took", "connected to None:None",
                                   "received EOF", "address info discord.com", "address info gateway"]
                for string in ignored_strings:
                    if string in record.getMessage():
                        return False
                return True

        # Order of logging levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
        logger = logging.getLogger('discord')
        logger.setLevel(logging.WARNING)
        logger_http = logging.getLogger('discord.http')
        logger_http.setLevel(logging.INFO)
        logger_asyncio = logging.getLogger('asyncio')
        logger_asyncio.setLevel(logging.DEBUG)
        logger_root = logging.getLogger('root')
        logger_root.setLevel(logging.DEBUG)
        self.bot.loop.set_debug(True)

        handler = logging.handlers.RotatingFileHandler(
            filename=f"{dir_path}/log/{discord.utils.utcnow().strftime('%y%m%d_%H%M')}.log",
            encoding='utf-8',
            maxBytes=32 * 1024 * 1024,  # 32 MiB
            backupCount=5,  # Rotate through 5 files
        )

        dt_fmt = '%Y-%m-%d %H:%M:%S'
        formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
        handler.setFormatter(formatter)
        
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.close()
                logger.removeHandler(handler)
        logger.addHandler(handler)
    
        # example using colors for console logging
        # from: https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output
        # class CustomFormatter(logging.Formatter):
        #
        #     grey = "\x1b[38;20m"
        #     yellow = "\x1b[33;20m"
        #     red = "\x1b[31;20m"
        #     bold_red = "\x1b[31;1m"
        #     reset = "\x1b[0m"
        #     format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
        #
        #     FORMATS = {
        #         logging.DEBUG: grey + format + reset,
        #         logging.INFO: grey + format + reset,
        #         logging.WARNING: bold_red + format + reset,
        #         logging.ERROR: red + format + reset,
        #         logging.CRITICAL: bold_red + format + reset
        #     }
        #
        #     def format(self, record):
        #         log_fmt = self.FORMATS.get(record.levelno)
        #         formatter = logging.Formatter(log_fmt)
        #         return formatter.format(record)
        #
        # asyncio_handler = logging.StreamHandler()
        # asyncio_handler.setLevel(logging.DEBUG)
        # asyncio_handler.setFormatter(CustomFormatter())
        # logger_asyncio.addHandler(asyncio_handler)  # add logic to clean old handlers if used

        for logger_filter in logger_http.filters[:]:
            logger_http.removeFilter(logger_filter)
            
        for logger_filter in logger_asyncio.filters[:]:
            logger_asyncio.removeFilter(logger_filter)

        # Add the filter to the logger
        logger_http.addFilter(IgnoreRateLimitFilter())
        logger_asyncio.addFilter(IgnoreAsyncioSSLHandshakeError())

    @tasks.loop(hours=24)
    async def database_backups(self):
        date = datetime.today().strftime("%Y%m%d-%H.%M")
        with open(f"{dir_path}/database_backups/database_{date}.json", "w") as write_file:
            json.dump(self.bot.db, write_file)
        with open(f"{dir_path}/database_backups/stats_{date}.json", "w") as write_file:
            json.dump(self.bot.stats, write_file)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.BadArgument):
            # parsing or conversion failure is encountered on an argument to pass into a command.
            await ctx.send("Failed to find the object you tried to look up.  Please try again")
            return

        elif isinstance(error, commands.MaxConcurrencyReached):
            if ctx.author == self.bot.user:
                pass
            else:
                await ctx.send("You're sending that command too many times. Please wait a bit.")
                return

        elif isinstance(error, discord.DiscordServerError):
            try:
                await asyncio.sleep(5)
                await ctx.send("There was a discord server error. Please try again.")
            except discord.DiscordServerError:
                return

        elif isinstance(error, commands.NoPrivateMessage):
            try:
                await ctx.author.send("You can only use this in a guild.")
                return
            except discord.Forbidden:
                pass

        elif isinstance(error, discord.Forbidden):
            try:
                await ctx.author.send("Rai lacked permissions to do something there")
            except discord.Forbidden:
                pass

        elif isinstance(error, commands.BotMissingPermissions):
            msg = f"To do that command, Rai is missing the following permissions: " \
                  f"`{'`, `'.join(error.missing_permissions)}`"
            if 'send_messages' in msg and isinstance(ctx.channel, discord.Thread):
                msg += "\n\nThis may be an error due to me lacking the permission to send messages in the " \
                       "parent channel to this thread. Try granting me the missing permissions in the parent " \
                       "channel as well."
            try:
                await ctx.send(msg)
            except discord.Forbidden:
                try:
                    await ctx.author.send(msg)
                except discord.Forbidden:
                    pass
            return

        elif isinstance(error, commands.CommandInvokeError):
            try:
                await ctx.send("I couldn't execute the command. I probably have a bug.  "
                               "This has been reported to the bot owner.")
            except discord.Forbidden:
                try:
                    await ctx.author.send("I tried doing something but I lack permissions to send messages.  "
                                          "I probably have a bug. This has been reported to the bot owner.")
                except (discord.Forbidden, discord.HTTPException):
                    pass
            pass

        elif isinstance(error, commands.CommandNotFound):
            # no command under that name is found
            return

        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"This command is on cooldown.  Try again in {round(error.retry_after)} seconds.")
            return

        elif isinstance(error, commands.CheckFailure):
            # the predicates in Command.checks have failed.
            if ctx.command.name == 'global_blacklist':
                return
            if ctx.guild:
                if str(ctx.guild.id) in self.bot.db['modsonly']:
                    if self.bot.db['modsonly'][str(ctx.guild.id)]['enable']:
                        if not hf.admin_check(ctx):
                            return

                # prevent users from using stats commands in spanish server learning channels, supress warnings
                if getattr(ctx.channel.category, "id", None) in [685446008129585176, 685445852009201674]:
                    return

            if ctx.command.name == "reply":
                # prevent erroneous command errors for server in which the "Nostradamus" bot is present
                if 567855500939493395 in [m.id for m in ctx.guild.members]:
                    return

            if ctx.command.cog.qualified_name in ['Admin', 'Logger', 'ChannelMods', 'Submod'] and \
                    (str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel'):
                try:
                    await ctx.send(
                        "Please set a mod channel or logging channel for Rai to send important error messages to"
                        " by typing `;set_mod_channel` in some channel.")
                except discord.Forbidden:
                    try:
                        await ctx.author.send("Rai lacks permission to send messages in that channel.")
                    except discord.Forbidden:
                        pass
                return
            try:
                if not ctx.guild:
                    raise discord.Forbidden
                if str(ctx.guild.id) in self.bot.db['mod_role']:
                    await ctx.send("You lack permissions to do that.")
                else:
                    await ctx.send(f"You lack the permissions to do that.  If you are a mod, try using "
                                   f"`{self.bot.db['prefix'].get(str(ctx.guild.id), ';')}set_mod_role <role name>`")
            except discord.Forbidden:
                await ctx.author.send("I tried doing something but I lack permissions to send messages.")
            return

        elif isinstance(error, commands.MissingRequiredArgument):
            # parsing a command and a parameter that is required is not encountered
            msg = f"You're missing a required argument ({error.param}).  " \
                  f"Try running `;help {ctx.command.qualified_name}`"
            if error.param.name in ['args', 'kwargs']:
                msg = msg.replace(f" ({error.param})", '')
            try:
                await ctx.send(msg)
            except discord.Forbidden:
                pass
            return

        elif isinstance(error, discord.Forbidden):
            await ctx.send("I tried to do something I'm not allowed to do, so I couldn't complete your command :(")

        elif isinstance(error, commands.MissingPermissions):
            error_str = f"To do that command, you are missing the following permissions: " \
                        f"`{'`, `'.join(error.missing_permissions)}`"
            await ctx.send(error_str)
            return

        elif isinstance(error, commands.NotOwner):
            await ctx.send("Only the bot owner can do that.")
            return

        qualified_name = getattr(ctx.command, 'qualified_name', ctx.command.name)
        e = discord.Embed(title='Command Error', colour=0xcc3366)
        e.add_field(name='Name', value=qualified_name)
        e.add_field(name='Command', value=ctx.message.content[:1000])
        e.add_field(name='Author', value=f'{ctx.author} (ID: {ctx.author.id})')

        fmt = f'Channel: {ctx.channel} (ID: {ctx.channel.id})'
        if ctx.guild:
            fmt = f'{fmt}\nGuild: {ctx.guild} (ID: {ctx.guild.id})'
        e.add_field(name='Location', value=fmt, inline=False)

        await utils.send_error_embed(self.bot, ctx, error, e)

    async def on_error(self, event, *args, **kwargs):
        e = discord.Embed(title='Event Error', colour=0xa32952)
        e.add_field(name='Event', value=str(event)[:1024])
        e.timestamp = discord.utils.utcnow()

        args_str = ['```py']
        jump_url = ''
        for index, arg in enumerate(args):
            args_str.append(f'[{index}]: {arg!r}')
            if isinstance(arg, discord.Message):
                e.add_field(name="Author", value=f'{arg.author} (ID: {arg.author.id})'[:1024])
                fmt = f'Channel: {arg.channel} (ID: {arg.channel.id})'
                if arg.guild:
                    fmt = f'{fmt}\nGuild: {arg.guild} (ID: {arg.guild.id})'
                e.add_field(name='Location', value=fmt[:1024], inline=False)
                jump_url = arg.jump_url
        joined_args_str = '\n'.join(args_str)
        joined_args_str = joined_args_str[:1021] + '```'
        e.add_field(name='Args', value=joined_args_str[:1024], inline=False)
        
        message_content = f'{traceback.format_exc()}'
        message_content_list = hf.split_text_into_segments(message_content, 1900)
        traceback_channel = self.bot.get_channel(TRACEBACK_LOGGING_CHANNEL)
        try:
            if len(message_content_list) > 1:
                for index, segment in enumerate(message_content_list):
                    if index == 0:
                        await traceback_channel.send(f"{jump_url}\n```py\n{segment}```")
                    elif index != len(message_content_list) - 1:
                        await traceback_channel.send(f"```py\n{segment}```")
                    else:
                        await traceback_channel.send(f"```py\n{segment}```", embed=e)
            else:
                await traceback_channel.send(f"{jump_url}\n```py\n{message_content}```", embed=e)
        except AttributeError:
            pass  # Set ID of TRACEBACK_LOGGING_CHANNEL at top of this file to a channel in your testing server
        traceback.print_exc()


async def setup(bot):
    await bot.add_cog(Main(bot))
