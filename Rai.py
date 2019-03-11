# -*- coding: utf8 -*-
import discord
import asyncio
from discord.ext.commands import Bot
from discord.ext import commands
import platform
import sys, traceback
import json

from datetime import datetime, timedelta
from pytz import reference

import os
dir_path = os.path.dirname(os.path.realpath(__file__))

# import logging
# logger = logging.getLogger('discord')
# logger.setLevel(logging.INFO)
# handler = logging.FileHandler(
#     filename=f'{dir_path}/log/{datetime.utcnow().strftime("%y%m%d_%H%M")}.log',
#     encoding='utf-8',
#     mode='a')
# handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
# logger.addHandler(handler)

tStart = datetime.now()

initial_extensions = ['cogs.main', 'cogs.admin', 'cogs.owner', 'cogs.math', 'cogs.logger', 'cogs.jpserv']

with open(f"{dir_path}/db.json", "r") as read_file:
    db = json.load(read_file)


def prefix(bot, msg):
    if msg.guild:
        return db['prefix'].get(str(msg.guild.id), ';')
    else:
        return ';'


bot = Bot(description="Bot by Ryry013#9234", command_prefix=prefix, owner_id=202995638860906496)


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

    bot.ryry = bot.get_user(202995638860906496)
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

    # bot.invitesOld = await bot.jpServ.invites() # for use in welcome cog for checking invites
    bot.waited = str(bot.spanServ.get_member(116275390695079945).status) == 'offline' #checks nadeko, for use in welcome cog with checking nadeko online/offline
    bot.selfMute = False

    bot.db = db
    bot.ID = bot.db["ID"]
    date = datetime.today().strftime("%d%m%Y%H%M")
    with open(f"{dir_path}/database_backups/database_{date}.json", "w") as write_file:
        json.dump(bot.db, write_file)

    # with open(f"{dir_path}/messages.json", "r") as read_file:
    #     bot.messages = json.load(read_file)
    #
    # with open(f"{dir_path}/super_watch.json", "r") as read_file:
    #     bot.super_watch = json.load(read_file)

    tFinish = datetime.now()
    await bot.testChan.send('Bot loaded (time: {})'.format(tFinish-tStart))
    await bot.change_presence(activity=discord.Game(';help'))
    sys.stderr.flush()
    sys.stdout.flush()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.author.send('This command cannot be used in private messages.')
    # elif isinstance(error, commands.CommandInvokeError):
    #     command = ctx.command.qualified_name
    #     await ctx.send(f"You inputted the syntax for that command wrong.  Check `;help {command}`")
    #     print(f'Error in {command}:', file=sys.stderr)
    #     traceback.print_tb(error.original.__traceback__)
    #     print(f'{error.original.__class__.__name__}: {error.original}', file=sys.stderr)
    elif isinstance(error, commands.errors.CheckFailure):
        await ctx.send(f"You lack the permissions to do that.  Try using "
                       f"`{bot.db['prefix'].get(str(ctx.guild.id), ';')}set_mod_role <role name>`")
    elif isinstance(error, commands.CommandNotFound):
        print(f">>Command not found \n{ctx.message.content[:30]}<<")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"You're missing a required argument.  Try running `;help {ctx.command.qualified_name}`")
    else:
        error = getattr(error, 'original', error)
        qualified_name = getattr(ctx.command, 'qualified_name', ctx.command.name)
        print(f'Error in {qualified_name}:', file=sys.stderr)
        traceback.print_tb(error.__traceback__)
        print(f'{error.__class__.__name__}: {error}', file=sys.stderr)

        e = discord.Embed(title='Command Error', colour=0xcc3366)
        e.add_field(name='Name', value=qualified_name)
        e.add_field(name='Author', value=f'{ctx.author} (ID: {ctx.author.id})')

        fmt = f'Channel: {ctx.channel} (ID: {ctx.channel.id})'
        if ctx.guild:
            fmt = f'{fmt}\nGuild: {ctx.guild} (ID: {ctx.guild.id})'

        e.add_field(name='Location', value=fmt, inline=False)

        exc = ''.join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
        traceback_text = f'```py\n{exc}\n```'
        e.timestamp = datetime.utcnow()
        await bot.get_channel(554572239836545074).send(traceback_text, embed=e)



def getAPIKey(filename):
    with open(filename) as f:
        return f.read()


key = getAPIKey(dir_path+'/APIKey.txt') + 'k'
bot.run(key)
input("press key to exit")
