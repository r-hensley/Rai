# -*- coding: utf8 -*-
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
          "for tracebacks and "
          ", put channel IDs in those.\n"
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

max_messages = 10000

def prefix(bot: commands.Bot, msg: discord.Message) -> str:
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
                         help_command=None, intents=intents, max_messages=max_messages)
        self.max_messages: int = max_messages
        self.db: dict = {}
        self.stats: dict = {}
        self.language_detection: bool = False
        self.t_start = t_start
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

    async def setup_hook(self):
        utils.load_db(self, 'db')
        utils.load_db(self, 'stats')
        
        hf.setup(bot=self, loop=asyncio.get_event_loop())  # this is to define here.bot in the hf file
        utils.setup(bot=self, loop=asyncio.get_event_loop())

        initial_extensions = ['cogs.main', 'cogs.admin', 'cogs.channel_mods', 'cogs.general', 'cogs.logger',
                              'cogs.math', 'cogs.owner', 'cogs.questions', 'cogs.reports', 'cogs.stats', 'cogs.submod',
                              'cogs.events', 'cogs.interactions', 'cogs.clubs', 'cogs.jpserv', 'cogs.message',
                              'cogs.dictionary']

        # cogs.background is loaded in main.py
        for extension in initial_extensions:
            try:
                print(f"Loaded {extension}")
                await self.load_extension(extension)
            except Exception:
                print(f'Failed to load {extension}', file=sys.stderr)
                traceback.print_exc()
                raise
            
        if os.getenv("OWNER_ID") == "202995638860906496":
            await self.load_extension('cogs.rl.rl')

        await create_database_tables()

        


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
