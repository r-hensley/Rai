import discord
from discord.ext import commands
from .utils import helper_functions as hf
import asyncio
from datetime import datetime, timedelta, date
from .utils import helper_functions as hf
import re
from textblob import TextBlob as tb
import textblob
import requests
import json
from Levenshtein import distance as LDist
import string

import os
dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Submod(commands.Cog):
    """Help"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel':
            await hf.safe_send(ctx, "Please set a mod channel using `;set_mod_channel`.")
            return
        return hf.submod_check(ctx)

    @commands.group(aliases=['warnlog', 'ml', 'wl'], invoke_without_command=True)
    @hf.is_submod()
    async def modlog(self, ctx, id):
        """View modlog of a user"""
        if str(ctx.guild.id) not in ctx.bot.db['modlog']:
            return
        config = ctx.bot.db['modlog'][str(ctx.guild.id)]
        member = await hf.member_converter(ctx, id)
        if member:
            name = f"{member.name}#{member.discriminator} ({member.id})"
            user_id = str(member.id)
        else:
            return  # member_converter prints the "user not found"
        if user_id not in config:
            em = hf.red_embed(f"{name} was not found in the modlog.")
            await hf.safe_send(ctx, embed=em)
            return
        config = config[user_id]
        emb = hf.green_embed(f"Modlog for {name}")
        for entry in config[-25:]:
            name = f"{config.index(entry)}) {entry['type']}"
            if entry['silent']:
                name += " (silent)"
            value = f"{entry['date']}\n"
            if entry['length']:
                value += f"*For {entry['length']}*\n"
            if entry['reason']:
                value += f"__Reason__: {entry['reason']}\n"
            value += f"[Jump URL]({entry['jump_url']})\n⠀"  # invisible character at end of this line
            emb.add_field(name=name,
                          value=value[:1024],
                          inline=False)
        await hf.safe_send(ctx, embed=emb)

    @modlog.command(name='delete', aliases=['del'])
    @hf.is_admin()
    async def modlog_delete(self, ctx, user, index):
        """Delete a modlog entry.  Do `;modlog delete user -all` to clear all warnings from a user.
        Alias: `;ml del`"""
        if str(ctx.guild.id) not in ctx.bot.db['modlog']:
            return
        config = ctx.bot.db['modlog'][str(ctx.guild.id)]
        member = await hf.member_converter(ctx, user)
        if member:
            user_id = str(member.id)
        else:
            user_id = user
        if user_id not in config:
            await hf.safe_send(ctx, "That user was not found in the modlog")
            return
        config = config[user_id]
        if index in ['-a', '-all']:
            del config
            await hf.safe_send(ctx, embed=hf.red_embed(f"Deleted all modlog entries for <@{user_id}>."))
        else:
            try:
                del config[int(index)]
            except IndexError:
                await hf.safe_send(ctx, "I couldn't find that log ID, try doing `;modlog` on the user.")
                return
            await ctx.message.add_reaction('✅')

    @modlog.command(name="edit", aliases=['reason'])
    @hf.is_admin()
    async def modlog_edit(self, ctx, user, index: int, *, reason):
        """Edit the reason for a selected modlog.  Example: `;ml edit ryry 2 trolling in voice channels`."""
        if str(ctx.guild.id) not in ctx.bot.db['modlog']:
            return
        config = ctx.bot.db['modlog'][str(ctx.guild.id)]
        member = await hf.member_converter(ctx, user)
        if member:
            user_id = str(member.id)
        else:
            user_id = user
        if user_id not in config:
            await hf.safe_send(ctx, "That user was not found in the modlog")
            return
        config = config[user_id]
        old_reason = config[index]['reason']
        config[index]['reason'] = reason
        await hf.safe_send(ctx, embed=hf.green_embed(f"Changed the reason for entry #{index} from "
                                                     f"```{old_reason}```to```{reason}```"))

    @commands.command()
    @hf.is_admin()
    async def reason(self, ctx, user, index: int, *, reason):
        """Shortcut for `;modlog reason`"""
        await ctx.invoke(self.modlog_edit, user, index, reason=reason)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    async def ban(self, ctx, *, args):
        """Bans a user.  Usage: `;ban [time #d#h] <user> [reason]`  Example: `;ban @Ryry013 being mean` or \
        `;ban 2d3h @Abelian posting invite links`.  If crossposting is enabled, you can add `-s` into the reason to \
        make this ban not crosspost."""
        args = args.split()
        if not args:
            await hf.safe_send(ctx, ctx.command.help)
            return
        timed_ban = re.findall('^\d+d\d+h$|^\d+d$|^\d+h$', args[0])
        if timed_ban:
            if re.findall('^\d+d\d+h$', args[0]):  # format: #d#h
                length = timed_ban[0][:-1].split('d')
                length = [length[0], length[1]]
            elif re.findall('^\d+d$', args[0]):  # format: #d
                length = [timed_ban[0][:-1], '0']
            else:  # format: #h
                length = ['0', timed_ban[0][:-1]]
            unban_time = datetime.utcnow() + timedelta(days=int(length[0]), hours=int(length[1]))
            target = await hf.member_converter(ctx, args[1])
            reason = ' '.join(args[2:])
            time_string = unban_time.strftime("%Y/%m/%d %H:%M UTC")
        else:
            target = await hf.member_converter(ctx, args[0])
            length = []
            time_string = None
            reason = ' '.join(args[1:])
        if not target:
            return
        if not reason:
            reason = '(no reason given)'

        if ctx.guild.id == 243838819743432704:  # spanish server
            for _ in ['_']:  # i could do just '_' but I like the robot head
                if ctx.guild.get_role(258819531193974784) in ctx.author.roles:  # helpers
                    if datetime.utcnow() - target.joined_at < timedelta(minutes=60):
                        break
                if hf.admin_check(ctx):
                    break
                raise commands.MissingPermissions('ban_members')
        else:
            if not hf.admin_check(ctx):
                raise commands.MissingPermissions('ban_members')

        em = discord.Embed(title=f"You've been banned from {ctx.guild.name}")
        if length:
            em.description = f"You will be unbanned automatically at {time_string} " \
                             f"(in {length[0]} days and {length[1]} hours)"
        else:
            em.description = "This ban is indefinite."
        if reason != '(no reason given)':
            if '-silent' in reason or '-s' in reason:
                reason = reason.replace('-silent ', '').replace('-s ', '')
                reason = '⁣' + reason  # no width space = silent
            if '-c' in reason:
                reason = '⠀' + reason  # invisible space = crosspost
            em.add_field(name="Reason:", value=reason)
        await hf.safe_send(ctx, f"You are about to ban {target.mention}: ", embed=em)
        msg2 = f"Do you wish to continue?  Type `yes` to ban, `send` to ban and send the above notification " \
               f"to the user, or `no` to cancel."

        if ctx.author in self.bot.get_guild(257984339025985546).members:
            try:
                if 'crosspost' in self.bot.db['bans'][str(ctx.guild.id)]:
                    if not reason.startswith('⁣') and str(ctx.guild.id) in self.bot.db['bans']:  # no width space
                        if self.bot.db['bans'][str(ctx.guild.id)]['crosspost']:
                            msg2 += "\n(To not crosspost this, cancel the ban and put `-s` or `-silent` in the reason)"
                    if not reason.startswith('⠀') and str(ctx.guild.id) in self.bot.db['bans']:  # invisible space
                        if not self.bot.db['bans'][str(ctx.guild.id)]['crosspost']:
                            msg2 += "\n(To specifically crosspost this message, " \
                                    "cancel the ban and put `-c` in the reason)"
            except KeyError:
                pass
        msg2 = await hf.safe_send(ctx, msg2)
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=40.0,
                                          check=lambda x: x.author == ctx.author and
                                                          x.content.casefold() in ['yes', 'no', 'send'])
        except asyncio.TimeoutError:
            await hf.safe_send(ctx, f"Timed out.  Canceling ban.")
            return
        content = msg.content.casefold()
        if content == 'no':
            await hf.safe_send(ctx, f"Canceling ban")
            await msg2.delete()
            return
        text = f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** {reason}"
        if reason.startswith('⁣'):
            text = '⁣' + text
        if reason.startswith('⠀'):
            text = '⠀' + text
        if content == 'send':
            try:
                await target.send(embed=em)
            except discord.Forbidden:
                await hf.safe_send(ctx, "The target user has PMs disabled so I didn't send the notification.")
        try:
            await target.ban(reason=text, delete_message_days=0)
        except discord.Forbidden:
            await hf.safe_send(ctx, f"I couldn't ban that user.  They're probably above me in the role list.")
            return
        if length:
            config = self.bot.db['bans'].setdefault(str(ctx.guild.id),
                                                    {'enable': False, 'channel': None, 'timed_bans': {}})
            timed_bans = config.setdefault('timed_bans', {})
            timed_bans[str(target.id)] = time_string
        await hf.safe_send(ctx, f"Successfully banned")

    @commands.command()
    @hf.is_admin()
    async def set_submod_role(self, ctx, *, role_name):
        """Set the submod role for your server.  Type the exact name of the role like `;set_submod_role Mods`."""
        config = hf.database_toggle(ctx, self.bot.db['submod_role'])
        if 'enable' in config:
            del (config['enable'])
        submod_role = discord.utils.find(lambda role: role.name == role_name, ctx.guild.roles)
        if not submod_role:
            await hf.safe_send(ctx, "The role with that name was not found")
            return None
        config['id'] = submod_role.id
        await hf.safe_send(ctx, f"Set the submod role to {submod_role.name} ({submod_role.id})")

    @commands.command(aliases=['setsubmodchannel'])
    @hf.is_admin()
    async def set_submod_channel(self, ctx, channel_id=None):
        """Sets the channel for submods"""
        if not channel_id:
            channel_id = ctx.channel.id
        self.bot.db['submod_channel'][str(ctx.guild.id)] = channel_id
        await hf.safe_send(ctx, f"Set the submod channel for this server as {ctx.channel.mention}.")


def setup(bot):
    bot.add_cog(Submod(bot))
