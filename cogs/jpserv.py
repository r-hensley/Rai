import discord
from discord.ext import commands
import os
import json
from datetime import date, datetime, timedelta
from .utils import helper_functions as hf
from copy import deepcopy

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__))).replace('\\', '/')


class Jpserv(commands.Cog):
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

    @commands.command()
    @hf.is_admin()
    async def swap(self, ctx):
        jpJHO = bot.get_channel(189571157446492161)
        jpJHO2 = bot.get_channel(326263874770829313)
        if jpJHO.position == 4:
            await jpJHO.edit(position=5, name='just_hanging_out_2')
            await jpJHO2.edit(position=4, name='just_hanging_out')
        else:
            await jpJHO.edit(position=4, name='just_hanging_out')
            await jpJHO2.edit(position=5, name='just_hanging_out_2')

    @commands.group(invoke_without_command=True, aliases=['uhc'])
    async def ultrahardcore(self, ctx, member: discord.Member = None):
        """Irreversible hardcore mode.  Must talk to an admin to have this undone."""
        role = ctx.guild.get_role(486851965121331200)
        config = self.bot.db['ultraHardcore']['users']
        if member:  # if you specified someone else's ID, then remove UHC from them
            if hf.admin_check(ctx) and ctx.author.id != member.id:
                if config[str(member.id)][0]:
                    config[str(member.id)][0] = False
                else:
                    await ctx.send("That user is not in UHC mode.")
                    return
                await hf.dump_json()
                try:
                    await member.remove_roles(role)
                except discord.errors.Forbidden:
                    await ctx.send("I couldn't remove the ultra hardcore role")
                await ctx.send(f'Undid ultra hardcore mode for {member.name}')
            else:
                await cxt.send("You can not remove UHC.  Ask a mod/admin to help you.")
        else:
            await ctx.send(f"This is ultra hardcore mode.  It means you must speak in the language you are learning "
                           f"(for example, if you are learning Japanese, any messages in English will be deleted). "
                           f"This can not be undone unless you ask a mod to remove it for you.  \n\n"
                           f"To enable ultra hardcore mode, type `;uhc on` or `;uhc enable`.  ")

    @ultrahardcore.command(aliases=['enable'])
    async def on(self, ctx):
        role = ctx.guild.get_role(486851965121331200)
        config = self.bot.db['ultraHardcore']['users']
        if ctx.author.id in config['users']:  # if not enabled
            user = config['users'][str(ctx.author.id)]
            if user['on']:
                await ctx.send("You're already in ultra hardcore mode.")
                return
            else:
                user['on'] = True
        else:
            config['users'][str(ctx.author.id)] = [True, date.today().strftime("%Y/%m/%d"), 0]

        await hf.dump_json()
        try:
            await ctx.author.add_roles(role)
        except discord.errors.Forbidden:
            await ctx.send("I couldn't add the ultra hardcore role")
        await ctx.send(f"{ctx.author.name} has chosen to enable ultra hardcore mode.  It works the same as "
                       "normal hardcore mode except that you can't undo it and asterisks don't change "
                       "anything.  Talk to a mod to undo this.")

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
        if ctx.author.id in self.bot.db['ultraHardcore'][str(ctx.guild.id)]:
            await ctx.send(f"{ctx.author.mention} is currently using ultra hardcore mode.  In this mode, they can't "
                           f"speak their native language, and they also cannot undo this mode themselves.")
        else:
            await ctx.send(f"{ctx.author.mention} is currently NOT using hardcore mode, so I don't know why "
                           f"they're trying to use this command.  But, ultra hardcore mode means a user can't speak "
                           f"any English, and can't undo this mode themselves no matter what.")

    @ultrahardcore.command(aliases=['lb'])
    async def leaderboard(self, ctx):
        """Shows a leaderboard of who has had UHC on for the longest"""
        time_dict = deepcopy(self.bot.db['ultraHardcore']['users'])
        for i in time_dict:
            if time_dict[i][0]:
                time_dict[i][2] += (datetime.today() - datetime.strptime(time_dict[i][1], "%Y/%m/%d")).days

        # {('243703909166612480', [True, '2019/02/14', 124]),
        # ('219617844973797376', [False, '2018/11/30', 122]), ...}

        to_sort = [[i[0], i[1][0], i[1][2]] for i in list(time_dict.items())]
        # to_sort: [['243703909166612480', True, 162], ['219617844973797376', False, 122], ...]
        sorted_dict = sorted(to_sort, key=lambda x: x[2], reverse=True)
        print(sorted_dict)
        leaderboard = f"Leaderboard for UHC (number of days each user has had it on) " \
                      f"(note, no users are actually pinged)\n" \
                      f"Bold = This user currently has UHC enabled.\n\n"
        for i in sorted_dict:
            user = ctx.guild.get_member(int(i[0]))
            if i[2] < 10 and not i[1]:
                continue
            if user:
                if user.nick:
                    nickname = user.name
                    username = f" ({user.name})"
                else:
                    nickname = user.name
                    username = ''
            else:
                nickname = i[0]
            if i[1] and user:
                leaderboard += f"**{i[2]}: {user.mention}{username}**\n"
            else:
                leaderboard += f"{i[2]}: {user.mention}{username}\n"
        msg = await ctx.send("Calculating")
        await msg.edit(content=leaderboard)

    @ultrahardcore.command()
    @hf.is_admin()
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
        await hf.dump_json()

def setup(bot):
    bot.add_cog(Jpserv(bot))
