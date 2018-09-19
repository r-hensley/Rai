# -*- coding: utf8 -*-
import discord
import asyncio
from discord.ext.commands import Bot
from discord.ext import commands
import platform
import sys, traceback
import json

from datetime import datetime,timedelta
from pytz import reference

import os
dir_path = os.path.dirname(os.path.realpath(__file__))

#sys.stdout = open(dir_path+f'/log/{datetime.utcnow().strftime("%y%m%d_%H%M")}.log', 'a')
#sys.stderr = open(dir_path+f'/log/{datetime.utcnow().strftime("%y%m%d_%H%M")}.log', 'a')

import logging
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(
    filename=f'{dir_path}/log/{datetime.utcnow().strftime("%y%m%d_%H%M")}.log',encoding='utf-8',mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

tStart = datetime.now()

initial_extensions = ['cogs.main', 'cogs.owner', 'cogs.welcome', 'cogs.math']

bot = Bot(description="Bot by Ryry013#9234", command_prefix=";", owner_id=202995638860906496)


@bot.event
async def on_ready():
    # await asyncio.sleep(1)
    for extension in initial_extensions:
        try:  # in on_ready because if not I get tons of errors from on_message before bot loads
            bot.load_extension(extension)
            print('Loaded {}'.format(extension))
        except Exception as e:
            print('Failed to load extension {}.'.format(extension), file=sys.stderr)
            traceback.print_exc()

    print("Bot loaded")
    
    bot.ryryServ = bot.get_guild(275146036178059265)
    bot.testChan = bot.get_channel(304110816607862785)
    bot.spamChan = bot.get_channel(275879535977955330)
    bot.nadLog = bot.get_channel(451211431006830593)
    
    bot.jpServ = bot.get_guild(189571157446492161)
    bot.jpEverything = bot.get_channel(277384105245802497)
    bot.jpJHO = bot.get_channel(189571157446492161)
    bot.jpJHO2 = bot.get_channel(326263874770829313)
    
    bot.spanServ = bot.get_guild(243838819743432704)
    bot.spanSP = bot.get_channel(277511392972636161)

    bot.invitesOld = await bot.jpServ.invites() # for use in welcome cog for checking invites
    bot.waited = str(bot.spanServ.get_member(116275390695079945).status)=='offline' #checks nadeko, for use in welcome cog with checking nadeko online/offline
    bot.selfMute = False

    bot.currentReportRoomUser = None
    bot.reportRoom = bot.get_channel(485391894356951050)
    bot.reportRoomWaitingList = []

    with open(f"{dir_path}/database.json", "r") as read_file:
        bot.db = json.load(read_file)
    bot.ID = bot.db["ID"]

    tFinish = datetime.now()
    await bot.testChan.send('Bot loaded (time: {})'.format(tFinish-tStart))

def getAPIKey(filename):
    with open(filename) as f:
        return f.read()


bot.run(getAPIKey(dir_path+'/BasicBotAPIKey.txt'))
input("press key to exit")
