import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
from pytz import reference
import time
import sys
import os
from .utils import characters
import re
import json

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__))).replace('\\', '/')


class Jpserv:
    """Modules unique for the Japanese server"""

    def __init__(self, bot):
        self.bot = bot

    async def __local_check(self, ctx):
        return ctx.guild.id == 189571157446492161 or ctx.guild.id == 275146036178059265
        # these commands are only useable on Japanese server or my testing server

    def is_admin():
        async def pred(ctx):
            return ctx.channel.permissions_for(ctx.author).administrator

        return commands.check(pred)

    def dump_json(self):
        with open(f'{dir_path}/database2.json', 'w') as write_file:
            json.dump(self.bot.db, write_file)
            write_file.flush()
            os.fsync(write_file.fileno())
        os.remove(f'{dir_path}/database.json')
        os.rename(f'{dir_path}/database2.json', f'{dir_path}/database.json')

    @commands.command()
    @is_admin()
    async def swap(self, ctx):
        if self.bot.jpJHO.permissions_for(ctx.author).administrator:
            if self.bot.jpJHO.position == 4:
                await self.bot.jpJHO.edit(position=5, name='just_hanging_out_2')
                await self.bot.jpJHO2.edit(position=4, name='just_hanging_out')
            else:
                await self.bot.jpJHO.edit(position=4, name='just_hanging_out')
                await self.bot.jpJHO2.edit(position=5, name='just_hanging_out_2')

    @commands.group(invoke_without_command=True, aliases=['uhc'])
    async def ultrahardcore(self, ctx, member: discord.Member = None):
        """Irreversible hardcore mode.  Must talk to an admin to have this undone."""
        role = ctx.guild.get_role(486851965121331200)
        if not member:  # if no ID specified in command
            if ctx.author.id not in self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])]:  # if not enabled
                self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])].append(ctx.author.id)
                self.dump_json()
                try:
                    await ctx.author.add_roles(role)
                except discord.errors.Forbidden:
                    await ctx.send("I couldn't add the ultra hardcore role")
                await ctx.send(f"{ctx.author.name} has chosen to enable ultra hardcore mode.  It works the same as "
                               "normal hardcore mode except that you can't undo it and asterisks don't change "
                               "anything.  Talk to a mod to undo this.")
            else:  # already enabled
                await ctx.send("You're already in ultra hardcore mode.")
        else:  # if you specified someone else's ID, then remove UHC from them
            if self.bot.jpJHO.permissions_for(ctx.author).administrator:
                if ctx.author.id != member.id:
                    self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])].remove(member.id)
                    self.dump_json()
                    try:
                        await member.remove_roles(role)
                    except discord.errors.Forbidden:
                        await ctx.send("I couldn't remove the ultra hardcore role")
                    await ctx.send(f'Undid ultra hardcore mode for {member.name}')

    @ultrahardcore.command()
    async def list(self, ctx):
        """Lists the people currently in ultra hardcore mode"""
        string = 'The members in ultra hardcore mode right now are '
        guild = self.bot.get_guild(189571157446492161)
        members = []

        for member_id in self.bot.db['ultraHardcore'][str(guild.id)]:
            member = guild.get_member(int(member_id))
            if member is not None:  # in case a member leaves
                members.append(str(member))
            else:
                self.bot.db['ultraHardcore'][str(guild.id)].remove(member_id)
                await ctx.send(f'Removed <@{member_id}> from the list, as they seem to have left the server')

        await ctx.send(string + ', '.join(members))

    @ultrahardcore.command()
    async def explanation(self, ctx):
        """Explains ultra hardcore mode for those who are using it and can't explain it"""
        await ctx.send("This user is currently using ultra hardcore mode.  In this mode, they can't speak any English, "
                       'and they also cannot undo this mode themselves.')

    @ultrahardcore.command()
    async def ignore(self, ctx):
        config = self.bot.db['ultraHardcore']
        try:
            if ctx.channel.id not in config['ignore']:
                config['ignore'].append(ctx.channel.id)
                await ctx.send(f"Added {ctx.channel.name} to list of ignored channels for UHC")
            else:
                config['ignore'].remove(ctx.channel.id)
                await ctx.send(f"Removed {ctx.channel.name} from list of ignored channels for UHC")
        except KeyError:
            config['ignore'] = [ctx.channel.id]
            await ctx.send(f"Added {ctx.channel.name} to list of ignored channels for UHC")
        self.dump_json()

def setup(bot):
    bot.add_cog(Jpserv(bot))
