# -*- coding: utf8 -*-
import discord
import asyncio
from discord.ext.commands import Bot
from discord.ext import commands
import platform
import sys, traceback
import json
from cogs.utils import helper_functions as hf


from datetime import datetime, timedelta
from pytz import reference

import os
dir_path = os.path.dirname(os.path.realpath(__file__))
print(os.stat(f'{dir_path}/stats.json'))
print(os.stat(f"{dir_path}/db.json"))
# import logging
# logger = logging.getLogger('discord')
# logger.setLevel(logging.INFO)
# handler = logging.FileHandler(
#     filename=f'{dir_path}/log/{datetime.utcnow().strftime("%y%m%d_%H%M")}.log',
#     encoding='utf-8',
#     mode='a')
# handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
# logger.addHandler(handler)

t_start = datetime.now()


def prefix(bot, msg):
    if bot.user.name == "Rai":
        default = ';'
    else:
        default = 'r;'
    if msg.guild:
        return bot.db['prefix'].get(str(msg.guild.id), default)
    else:
        return default


class Rai(Bot):
    def __init__(self):
        super().__init__(description="Bot by Ryry013#9234", command_prefix=prefix, owner_id=202995638860906496)
        self.bg_task = self.loop.create_task(self.background_tasks())
        self.last_error = datetime.utcnow()
        self.num_of_errors = 0
        print('starting loading of jsons')
        with open(f"{dir_path}/db.json", "r") as read_file1:
            read_file1.seek(0)
            self.db = json.load(read_file1)
        with open(f"{dir_path}/stats.json", "r") as read_file2:
            read_file2.seek(0)
            self.stats = json.load(read_file2)

        date = datetime.today().strftime("%d%m%Y%H%M")
        with open(f"{dir_path}/database_backups/database_{date}.json", "w") as write_file:
            json.dump(self.db, write_file)
        with open(f"{dir_path}/database_backups/stats_{date}.json", "w") as write_file:
            json.dump(self.stats, write_file)

        initial_extensions = ['cogs.admin', 'cogs.channel_mods', 'cogs.general', 'cogs.jpserv', 'cogs.logger',
                              'cogs.math', 'cogs.owner', 'cogs.questions', 'cogs.reports', 'cogs.stats', 'cogs.submod']
        for extension in initial_extensions:
            try:  # in on_ready because if not I get tons of errors from on_message before bot loads
                self.load_extension(extension)
                print('Loaded {}'.format(extension))
            except Exception as e:
                print('Failed to load extension {}.'.format(extension), file=sys.stderr)
                traceback.print_exc()
                raise

    async def on_ready(self):
        self.ryry = self.get_user(202995638860906496)
        self.ryryServ = self.get_guild(275146036178059265)
        self.testChan = self.get_channel(304110816607862785)
        self.spamChan = self.get_channel(275879535977955330)
        self.nadLog = self.get_channel(451211431006830593)

        self.jpServ = self.get_guild(189571157446492161)
        self.jpEverything = self.get_channel(277384105245802497)
        self.jpJHO = self.get_channel(189571157446492161)
        self.jpJHO2 = self.get_channel(326263874770829313)

        self.spanServ = self.get_guild(243838819743432704)
        self.spanSP = self.get_channel(277511392972636161)

        #  if self.user.name == "Rai":
            #  self.waited = str(self.spanServ.get_member(116275390695079945).status) == 'offline'  # checks nadeko
        self.selfMute = False


        print("Bot loaded")

        t_finish = datetime.now()
        await self.testChan.send('Bot loaded (time: {})'.format(t_finish - t_start))
        await self.change_presence(activity=discord.Game(';help | Questions⇛Ping/DM me'))

    async def background_tasks(self):
        await self.wait_until_ready()
        if bot.user.name != "Rai":
            return
        try:
            await self.wait_until_ready()
            counter = 4  # counts minutes (x4: 360, x24: 1440)
            channel = self.get_channel(304110816607862785)
            msg = await channel.send("Starting background tasks")
            ctx = await self.get_context(msg)
            while not self.is_closed():
                counter += 1
                x = datetime.utcnow()

                if x.hour == 0 and x.minute == 0:
                    counter = 0
                    date = datetime.today().strftime("%Y%m%d-%H.%M")
                    with open(f"{dir_path}/database_backups/database_{date}.json", "w") as write_file:
                        json.dump(self.db, write_file)
                    with open(f"{dir_path}/database_backups/stats_{date}.json", "w") as write_file:
                        json.dump(self.stats, write_file)
                    await ctx.invoke(self.get_command("_delete_old_stats_days"))

                await hf.dump_json()

                if counter % 5 == 0:
                    await ctx.invoke(self.get_command("_unban_users"))
                    await ctx.invoke(self.get_command("_unmute_users"))
                    await ctx.invoke(self.get_command("_check_desync_voice"))
                await asyncio.sleep(60)
        except Exception as error:
            error = getattr(error, 'original', error)
            print(f'Error in background task:', file=sys.stderr)
            traceback.print_tb(error.__traceback__)
            print(f'{error.__class__.__name__}: {error}', file=sys.stderr)
            channel = self.get_channel(554572239836545074)
            exc = ''.join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
            traceback_text = f'```py\n{exc}\n```'
            await channel.send(f'<@202995638860906496> Error in background task:\n{traceback_text}')
            self.num_of_errors += 1
            if (datetime.utcnow() - self.last_error).seconds > 5 and self.num_of_errors < 20:
                self.last_error = datetime.utcnow()
                self.bg_task = self.loop.create_task(self.background_tasks())
            else:
                await channel.send(f"❗❗❗❗ STOPPING BACKGROUND TASKS ❗❗❗❗\n"
                                   f"❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗❗")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            # parsing or conversion failure is encountered on an argument to pass into a command.
            await ctx.send(f"Failed to find the object you tried to look up.  Please try again")
            return

        elif isinstance(error, discord.Forbidden):
            try:
                await ctx.author.send("Rai lacked permissions to do something there")
            except discord.Forbidden:
                pass

        # elif isinstance(error, commands.BotMissingPermissions):
        #     msg = f"To do that command, Rai is missing the following permissions: `{'`, `'.join(error.missing_perms)}`"
        #     try:
        #         await ctx.send(msg)
        #     except discord.Forbidden:
        #         try:
        #             await ctx.author.send(msg)
        #         except discord.Forbidden:
        #             pass
        #     return

        elif isinstance(error, commands.CommandInvokeError):
            command = ctx.command.qualified_name
            try:
                await ctx.send(f"I couldn't execute the command.  I probably have a bug.  "
                               f"This has been reported to Ryan.")
            except discord.Forbidden:
                await ctx.author.send(f"I tried doing something but I lack permissions to send messages.  "
                                      f"I probably have a bug.  This has been reported to Ryan.")
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
            if str(ctx.guild.id) in self.db['modsonly']:
                if self.db['modsonly'][str(ctx.guild.id)]['enable']:
                    if not hf.admin_check(ctx):
                        return

            if ctx.command.cog.qualified_name in ['Admin', 'Logger'] and \
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
            #try:
            #   if str(ctx.guild.id) in self.db['mod_role']:
            #        await ctx.send("You lack permissions to do that.")
            #    else:
            #        await ctx.send(f"You lack the permissions to do that.  If you are a mod, try using "
            #                       f"`{self.db['prefix'].get(str(ctx.guild.id), ';')}set_mod_role <role name>`")
            #except discord.Forbidden:
            #    await ctx.author.send(f"I tried doing something but I lack permissions to send messages.")
            #return

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
            await ctx.send(f"I tried to do something I'm not allowed to do, so I couldn't complete your command :(")

        elif isinstance(error, commands.MissingPermissions):
            await ctx.send(f"To do that command, you are missing the following permissions: "
                           f"`{'`, `'.join(error.missing_perms)}`")
            return

        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send('This command cannot be used in private messages.')
            return

        elif isinstance(error, commands.NotOwner):
            await ctx.send(f"Only Ryan can do that.")
            return

        print(datetime.now())
        error = getattr(error, 'original', error)
        qualified_name = getattr(ctx.command, 'qualified_name', ctx.command.name)
        print(f'Error in {qualified_name}:', file=sys.stderr)
        traceback.print_tb(error.__traceback__)
        print(f'{error.__class__.__name__}: {error}', file=sys.stderr)

        e = discord.Embed(title='Command Error', colour=0xcc3366)
        e.add_field(name='Name', value=qualified_name)
        e.add_field(name='Command', value=ctx.message.content[:1000])
        e.add_field(name='Author', value=f'{ctx.author} (ID: {ctx.author.id})')

        fmt = f'Channel: {ctx.channel} (ID: {ctx.channel.id})'
        if ctx.guild:
            fmt = f'{fmt}\nGuild: {ctx.guild} (ID: {ctx.guild.id})'

        e.add_field(name='Location', value=fmt, inline=False)

        exc = ''.join(traceback.format_exception(type(error), error, error.__traceback__, chain=False))
        traceback_text = f'{ctx.message.jump_url}\n```py\n{exc}```'
        e.timestamp = datetime.utcnow()
        await self.get_channel(554572239836545074).send(traceback_text, embed=e)
        print('')


bot = Rai()
with open(f"{dir_path}/APIKey.txt") as f:
    bot.run(f.read() + 'k')
