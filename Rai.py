# -*- coding: utf8 -*-
import logging
import asyncio
import sys
import traceback
import json
import os
from datetime import datetime

from dotenv import load_dotenv

import discord
from discord.ext.commands import Bot
from discord.ext import commands, tasks

from cogs.utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils
from cogs.database import create_database_tables

logging.basicConfig(level=logging.WARNING)
# logger = logging.getLogger('discord')
# logger.setLevel(logging.INFO)
# handler = logging.FileHandler(
#     filename=f'{dir_path}/log/{discord.utils.utcnow().strftime("%y%m%d_%H%M")}.log',
#     encoding='utf-8',
#     mode='a')
# handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
# logger.addHandler(handler)

# noinspection lines to fix pycharm error saying Intents doesn't have members and Intents is read-only
intents = discord.Intents.default()
# noinspection PyUnresolvedReferences,PyDunderSlots
intents.members = True
# noinspection PyUnresolvedReferences,PyDunderSlots
intents.message_content = True
dir_path = os.path.dirname(os.path.realpath(__file__))

try:
    with open(f"{dir_path}/.env", 'r') as f:
        pass
except FileNotFoundError:
    txt = """BOT_TOKEN=\nTRACEBACK_LOGGING_CHANNEL=\nBOT_TEST_CHANNEL=\nOWNER_ID=\nGCSE_API="""
    with open(f'{dir_path}/.env', 'w') as f:
        f.write(txt)
    print("I've created a .env file for you, go in there and put your bot token in the file, as well as a channel "
          "for tracebacks and logging, put channel IDs in those.\n"
          "There is also a spot for your GCSE api key if you have one, \n"
          "but if you don't you can leave that blank.")
    exit()

# Credentials
load_dotenv(f'{dir_path}/.env')

if not os.getenv("BOT_TOKEN"):
    raise discord.LoginFailure("You need to add your bot token to the .env file in your bot folder.")
if not os.getenv("TRACEBACK_LOGGING_CHANNEL") or not os.getenv("BOT_TEST_CHANNEL"):
    raise discord.LoginFailure("Add the IDs for a logging channel and a tracebacks channel into the .env file "
                               "in your bot folder.")

# Change these two values to channel IDs in your testing server if you are forking the bot
TRACEBACK_LOGGING_CHANNEL = int(os.getenv("TRACEBACK_LOGGING_CHANNEL"))
BOT_TEST_CHANNEL = int(os.getenv("BOT_TEST_CHANNEL"))

t_start = datetime.now()


def prefix(bot, msg):
    if bot.user.name == "Rai":
        default = ';'
    else:
        default = 'r;'
    if msg.guild:
        if 'prefix' not in bot.db:
            bot.db['prefix'] = {}
        return bot.db['prefix'].get(str(msg.guild.id), default)
    else:
        return default


class Rai(Bot):
    def __init__(self):
        super().__init__(description="Bot by Ryry013#9234", command_prefix=prefix,
                         help_command=None, intents=intents, max_messages=10000)
        self.db = {}
        self.stats = {}
        self.language_detection = False
        print('starting loading of jsons')

        # Create json files if they don't exist
        if not os.path.exists(f"{dir_path}/db.json"):
            db = open(f"{dir_path}/db.json", 'w')
            new_db = {'ultraHardcore': {}, 'hardcore': {}, 'welcome_message': {}, 'roles': {}, 'ID': {},
                      'mod_channel': {}, 'mod_role': {}, 'deletes': {}, 'nicknames': {}, 'edits': {},
                      'leaves': {}, 'reactions': {}, 'captcha': {}, 'bans': {}, 'kicks': {}, 'welcomes': {},
                      'auto_bans': {}, 'global_blacklist': {}, 'super_voicewatch': {}, 'report': {},
                      'super_watch': {}, 'prefix': {}, 'questions': {}, 'mutes': {}, 'submod_role': {},
                      'colors': {}, 'submod_channel': {}, 'SAR': {}, 'channel_mod': {}, 'channel_mods': {},
                      'modlog': {}, 'dbtest': {}, 'modsonly': {}, 'voice_mutes': {},
                      'selfmute': {}, 'voicemod': {}, 'staff_ping': {}, 'voice': {}, 'new_user_watch': {},
                      'reactionroles': {}, 'pmbot': {}, 'joins': {}, 'timed_voice_role': {}, 'banlog': {},
                      'bansub': {}, 'forcehardcore': [], 'wordfilter': {}, 'ignored_servers': [], 'antispam': {},
                      'lovehug': {}, 'rawmangas': {}, 'risk': {}, 'guildstats': {}, 'bannedservers': [],
                      'spvoice': [], 'spam_links': [], 'voice_lock': {}, "helper_role": {}, "helper_channel": {},
                      'channels': {}}
            # A lot of these are unnecessary now but I'll fix that later when I make a new database
            print("Creating default values for database.")
            json.dump(new_db, db)
            db.close()
        if not os.path.exists(f"{dir_path}/stats.json"):
            db = open(f"{dir_path}/stats.json", 'w')
            print("Creating new stats database.")
            json.dump({}, db)
            db.close()

    async def on_ready(self):
        # if not self.stats:
        #     hf.load_stats(self)

        await hf.load_language_detection_model()
        self.language_detection = True

        try:
            AppInfo = await self.application_info()
            self.owner_id = AppInfo.owner.id
        except discord.HTTPException:
            pass

        test_channel = self.get_channel(BOT_TEST_CHANNEL)

        if test_channel:
            ctxmsg = await test_channel.send("Almost done!")
            self.ctx = await self.get_context(ctxmsg)
            sync: commands.Command = self.get_command("sync")
            await self.ctx.invoke(sync)
        else:
            ctxmsg = self.ctx = None

        try:  # in on_ready because there are many tasks in here that require a loaded bot
            await self.load_extension('cogs.background')
            print('Loaded cogs.background')
        except Exception:
            print('Failed to load extension cogs.background.', file=sys.stderr)
            traceback.print_exc()

        print(f"Bot loaded (discord.py version {discord.__version__})")

        t_finish = datetime.now()

        if ctxmsg:
            ctxmsg = await ctxmsg.edit(content=f'Bot loaded (time: {t_finish - t_start})')

        await self.change_presence(activity=discord.Game(';help for help'))

        if not self.database_backups.is_running():
            print("Starting database backups")
            self.database_backups.start()

    async def setup_hook(self):
        utils.load_db(self, 'db')
        utils.load_db(self, 'stats')

        initial_extensions = ['cogs.admin', 'cogs.channel_mods', 'cogs.general', 'cogs.jpserv', 'cogs.logger',
                              'cogs.math', 'cogs.owner', 'cogs.questions', 'cogs.reports', 'cogs.stats', 'cogs.submod',
                              'cogs.events', 'cogs.interactions', 'cogs.clubs']

        for extension in initial_extensions:
            try:
                print(f"Loaded {extension}")
                await self.load_extension(extension)
            except Exception:
                print(f'Failed to load {extension}', file=sys.stderr)
                traceback.print_exc()
                raise

        await create_database_tables()

        hf.setup(bot=self, loop=asyncio.get_event_loop())  # this is to define here.bot in the hf file
        utils.setup(bot=self, loop=asyncio.get_event_loop())

    @tasks.loop(hours=24)
    async def database_backups(self):
        date = datetime.today().strftime("%Y%m%d-%H.%M")
        with open(f"{dir_path}/database_backups/database_{date}.json", "w") as write_file:
            json.dump(self.db, write_file)
        with open(f"{dir_path}/database_backups/stats_{date}.json", "w") as write_file:
            json.dump(self.stats, write_file)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            # parsing or conversion failure is encountered on an argument to pass into a command.
            await ctx.send("Failed to find the object you tried to look up.  Please try again")
            return

        elif isinstance(error, commands.MaxConcurrencyReached):
            if ctx.author == self.user:
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
                await ctx.send("I couldn't execute the command.  I probably have a bug.  "
                               "This has been reported to the bot owner.")
            except discord.Forbidden:
                await ctx.author.send("I tried doing something but I lack permissions to send messages.  "
                                      "I probably have a bug.  This has been reported to the bot owner.")
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
                if str(ctx.guild.id) in self.db['modsonly']:
                    if self.db['modsonly'][str(ctx.guild.id)]['enable']:
                        if not hf.admin_check(ctx):
                            return

                # prevent users from using stats commands in spanish server learning channels, supress warnings
                if getattr(ctx.channel.category, "id", None) in [685446008129585176, 685445852009201674]:
                    return

            if ctx.command.cog.qualified_name in ['Admin', 'Logger', 'ChannelMods', 'Submod'] and \
                    (str(ctx.guild.id) not in self.db['mod_channel'] and ctx.command.name != 'set_mod_channel'):
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
                if str(ctx.guild.id) in self.db['mod_role']:
                    await ctx.send("You lack permissions to do that.")
                else:
                    await ctx.send(f"You lack the permissions to do that.  If you are a mod, try using "
                                   f"`{self.db['prefix'].get(str(ctx.guild.id), ';')}set_mod_role <role name>`")
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

        await utils.send_error_embed(self, ctx, error, e)

    async def on_error(self, event, *args, **kwargs):
        e = discord.Embed(title='Event Error', colour=0xa32952)
        e.add_field(name='Event', value=event)
        e.description = f'```py\n{traceback.format_exc()}\n```'
        e.timestamp = discord.utils.utcnow()

        args_str = ['```py']
        jump_url = ''
        for index, arg in enumerate(args):
            args_str.append(f'[{index}]: {arg!r}')
            if type(arg) == discord.Message:
                e.add_field(name="Author", value=f'{arg.author} (ID: {arg.author.id})')
                fmt = f'Channel: {arg.channel} (ID: {arg.channel.id})'
                if arg.guild:
                    fmt = f'{fmt}\nGuild: {arg.guild} (ID: {arg.guild.id})'
                e.add_field(name='Location', value=fmt, inline=False)
                jump_url = arg.jump_url
        args_str.append('```')
        e.add_field(name='Args', value='\n'.join(args_str), inline=False)
        try:
            await self.get_channel(TRACEBACK_LOGGING_CHANNEL).send(jump_url, embed=e)
        except AttributeError:
            pass  # Set ID of TRACEBACK_LOGGING_CHANNEL at top of this file to a channel in your testing server
        traceback.print_exc()


def run_bot():
    bot = Rai()

    key = os.getenv("BOT_TOKEN")

    if len(key) == 58:
        # A little bit of a deterrent from my token instantly being used if the .env file gets leaked somehow
        if "Rai Test" in os.path.basename(dir_path) and os.getenv("OWNER_ID") == "202995638860906496":
            bot.run(key + 'M')  # Rai Test
        elif "Rai" == os.path.basename(dir_path) and os.getenv("OWNER_ID") == "202995638860906496":
            try:
                bot.run(key + 'k')  # Rai
            except discord.LoginFailure:
                bot = Rai()
                bot.run(key + 'M')  # Rai test anyway
        else:
            bot.run(key)

    else:
        # For forked copies of Rai by other people, just run the bot normally:
        bot.run(key)  # For other people forking Rai bot


def main():
    run_bot()


if __name__ == '__main__':
    main()
