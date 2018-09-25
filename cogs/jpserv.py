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

dir_path = os.path.dirname(os.path.realpath(__file__))


class Jpserv:
    """Modules unique for the Japanese server"""

    def __init__(self, bot):
        self.bot = bot
        self._url = re.compile("""
                    # protocol identifier
                    (?:(?:https?|ftp)://)
                    # user:pass authentication
                    (?:\S+(?::\S*)?@)?
                    (?:
                      # IP address exclusion
                      # private & local networks
                      (?!(?:10|127)(?:\.\d{1,3}){3})
                      (?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})
                      (?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})
                      # IP address dotted notation octets
                      # excludes loopback network 0.0.0.0
                      # excludes reserved space >= 224.0.0.0
                      # excludes network & broacast addresses
                      # (first & last IP address of each class)
                      (?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])
                      (?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}
                      (?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))
                    |
                      # host name
                      (?:(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)
                      # domain name
                      (?:\.(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)*
                      # TLD identifier
                      (?:\.(?:[a-z\u00a1-\uffff]{2,}))
                      # TLD may end with dot
                      \.?
                    )
                    # port number
                    (?::\d{2,5})?
                    # resource path
                    (?:[/?#]\S*)?
                """, re.VERBOSE | re.I)

        self._emoji = re.compile(r'<a?:[A-Za-z0-9\_]+:[0-9]{17,20}>')

    async def __local_check(self, ctx):
        return ctx.guild.id == 189571157446492161 or ctx.guild.id == 275146036178059265
        # these commands are only useable on Japanese server or my testing server

    def is_admin():
        async def pred(ctx):
            return ctx.channel.permissions_for(ctx.author).administrator

        return commands.check(pred)

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
        for i in ctx.guild.roles:
            if i.id == 486851965121331200:
                role = i
                break
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
        await ctx.send('I am currently using ultra hardcore mode.  In this mode, I can not speak any English, '
                       'and I also can not undo this mode easily.')

    async def on_message(self, msg):
        """Ultra Hardcore"""
        if msg.author.id in self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])]:
            jpServ = self.bot.get_guild(self.bot.ID["jpServ"])
            engRole = next(role for role in jpServ.roles if role.id == 197100137665921024)
            jpRole = next(role for role in jpServ.roles if role.id == 196765998706196480)
            ratio = characters.jpenratio(msg)

            if msg.guild == jpServ:
                # if I delete a long message
                async def msg_user():
                    try:
                        notification = 'I may have deleted a message of yours that was long.  Here it was:'
                        if len(msg.content) < 2000 - len(notification):
                            await msg.author.send(notification + '\n' + msg.content)
                        else:
                            await msg.author.send(notification)
                            await msg.author.send(msg.content)
                    except discord.errors.Forbidden:
                        await msg.channel.send(f"<@{msg.author.id}> I deleted an important looking message of yours "
                                               f"but you seem to have DMs disabled so I couldn't send it to you.")
                        notification = "I deleted someone's message but they had DMs disabled"
                        me = self.bot.get_user(self.bot.owner_id)
                        if len(msg.content) < 2000 - len(notification):
                            await me.send(notification + '\n' + msg.content)
                        else:
                            await me.send(notification)
                            await me.send(msg.content)

                # allow Kotoba bot commands
                if msg.content[0:2] == 'k!':  # because K33's bot deletes results if you delete your msg
                    if msg.content.count(' ') == 0:  # if people abuse this, they must use no spaces
                        return  # please don't abuse this

                # delete the messages
                if ratio is not None:
                    msg_content = msg.content
                    if jpRole in msg.author.roles:
                        if ratio < .55:
                            await msg.delete()
                            if len(msg_content) > 60:
                                await msg_user()
                    else:
                        if ratio > .45:
                            await msg.delete()
                            if len(msg_content) > 60:
                                await msg_user()


def setup(bot):
    bot.add_cog(Jpserv(bot))
