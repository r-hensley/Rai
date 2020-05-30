import discord
from discord.ext import commands
from .utils import helper_functions as hf
import asyncio
from datetime import datetime, timedelta
import re

import os
dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

SP_SERV = 243838819743432704

def any_channel_mod_check(ctx):
    if ctx.guild.id != SP_SERV:
        return
    if hf.submod_check(ctx):
        return True
    chmd_config = ctx.bot.db['channel_mods'][str(SP_SERV)]
    for ch_id in chmd_config:
        if ctx.author.id in chmd_config[ch_id]:
            return True

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
        return True

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
            try:
                user = await self.bot.fetch_user(int(id))
                name = f"{user.name}#{user.discriminator} ({user.id})"
                user_id = id
            except discord.NotFound:
                name = user_id = id
            except discord.HTTPException:
                await hf.safe_send(ctx, "Your ID was not properly formatted. Try again.")
                return
            except ValueError:
                await hf.safe_send(ctx, "I couldn't find the user you were looking for. If they left the server, "
                                        "use an ID")
                return
        if user_id not in config:
            em = hf.red_embed(f"{name} was not found in the modlog.")
            await hf.safe_send(ctx, embed=em)
            return
        config = config[user_id]
        emb = hf.green_embed(f"Modlog for {name}")
        list_length = len(config[-25:])  # this is to prevent the invisible character on the last entry
        index = 1
        for entry in config[-25:]:
            name = f"{config.index(entry) + 1}) {entry['type']}"
            if entry['silent']:
                name += " (silent)"
            value = f"{entry['date']}\n"
            if entry['length']:
                value += f"*For {entry['length']}*\n"
            if entry['reason']:
                value += f"__Reason__: {entry['reason']}\n"
            if entry['jump_url']:
                value += f"[Jump URL]({entry['jump_url']})\n"
            if index < list_length:
                value += "⠀"  # invisible character to guarantee the empty new line
                index += 1
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
                del config[int(index) - 1]
            except IndexError:
                await hf.safe_send(ctx, "I couldn't find that log ID, try doing `;modlog` on the user.")
                return
            except ValueError:
                await hf.safe_send(ctx, "Sorry I couldn't  understand what you were trying to do")
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
        old_reason = config[index - 1]['reason']
        config[index - 1]['reason'] = reason
        await hf.safe_send(ctx, embed=hf.green_embed(f"Changed the reason for entry #{index} from "
                                                     f"```{old_reason}```to```{reason}```"))

    @commands.command()
    @hf.is_admin()
    async def reason(self, ctx, user, index: int, *, reason):
        """Shortcut for `;modlog reason`"""
        await ctx.invoke(self.modlog_edit, user, index, reason=reason)

    @commands.command()
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    @hf.is_submod()
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

        text = f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** XX"
        new_text = text.replace("XX", reason)
        if len(new_text) > 512:
            await hf.safe_send(ctx, "Discord only allows bans with a length of 512 characters. With my included "
                                    f"author tag, you are allowed {513 - len(text)} characters. Please reduce the "
                                    f"length of your ban message. ")
            return

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
        silent = False
        if reason != '(no reason given)':
            if '-silent' in reason or '-s' in reason:
                silent = True
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

        text = text.replace("XX", reason)

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

        if length:
            length_str = f"{length[0]}d{length[1]}h"
        else:
            length_str = None
        if reason.startswith("*by*"):
            reason = reason.replace(f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** ", '')
        hf.add_to_modlog(ctx, target, 'Ban', reason, silent, length_str)

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

    @commands.command(aliases=['staff'])
    @commands.check(any_channel_mod_check)
    async def staffrole(self, ctx):
        """You can add/remove the staff role from yourself with this"""
        staffrole = ctx.guild.get_role(642782671109488641)
        if staffrole in ctx.author.roles:
            await ctx.author.remove_roles(staffrole)
            await hf.safe_send(ctx, "I've removed the staff role from you")
        else:
            await ctx.author.add_roles(staffrole)
            await hf.safe_send(ctx, "I've given you the staff role.")

    @commands.command()
    @commands.check(any_channel_mod_check)
    async def staffping(self, ctx):
        """Subscribe yourself to staff ping notifications in your DM for when the staff role is pinged on this server"""
        subscribed_users = self.bot.db['staff_ping'][str(ctx.guild.id)]
        if ctx.author.id in subscribed_users:
            subscribed_users.remove(ctx.author.id)
            await hf.safe_send(ctx, "You will no longer receive notifications for staff pings.")
        else:
            subscribed_users.append(ctx.author.id)
            await hf.safe_send(ctx, "You will receive notifications for staff pings.")

    @commands.command(aliases=['r', 't', 'tag'])
    @commands.check(any_channel_mod_check)
    async def role(self, ctx, *, args):
        """Assigns a role to a user. Type `;role <user> <english/spanish/other/e/s/o/none/fe/fs>`. You can specify\
        multiple languages, fluent languages, or "None" to take away roles. Username must not have spaces.

        If you don't specify a user, then it will find the last user in the channel without a role. *If you do this,\
        you can only specify one role!*

        Examples: `;role @Ryry013 e`   `;role spanish`   `;r Ryry013 e o fs`   `;r Ryry013 none`"""
        if ctx.guild.id != SP_SERV:
            return
        english = ctx.guild.get_role(243853718758359040)
        spanish = ctx.guild.get_role(243854128424550401)
        other = ctx.guild.get_role(247020385730691073)
        fluentenglish = ctx.guild.get_role(267367044037476362)
        fluentspanish = ctx.guild.get_role(267368304333553664)
        learningenglish = ctx.guild.get_role(247021017740869632)
        learningspanish = ctx.guild.get_role(297415063302832128)
        language_roles = [english, spanish, other]
        all_roles = [english, spanish, other, fluentenglish, fluentspanish, learningenglish, learningspanish]
        langs_dict = {'e': english, 's': spanish, 'o': other, 'i': english, 'en': english, 'ne': english, 'ol': other,
                      'english': english, 'spanish': spanish, 'other': other, 'sn': spanish, 'ns': spanish,
                      'inglés': english, 'español': spanish, 'ingles': english, 'espanol': spanish, 'otro': other,
                      'fe': fluentenglish, 'fs': fluentspanish, 'none': None, 'n': None,
                      'le': learningenglish, 'ls': learningspanish}

        args = args.split()
        if len(args) > 1:  # ;r ryry013 english
            user = await hf.member_converter(ctx, args[0])
            if not user:
                return
            langs = [lang.casefold() for lang in args[1:]]

        elif len(args) == 1:  # something like ;r english
            if args[0].casefold() in ['none', 'n']:
                await hf.safe_send(ctx, "You can't use `none` and not specify a name.")
                return
            langs = [args[0].casefold()]

            user = None  # if it goes through 10 messages and finds no users without a role, it'll default here
            async for message in ctx.channel.history(limit=10):
                found = None
                for role in language_roles:  # check if they already have a role
                    if role in message.author.roles:
                        found = True
                if not found:
                    user = message.author
            if not user:
                await hf.safe_send(ctx, "I couldn't find any users in the last ten messages without a native role.")
                return

        else:  # no args
            await hf.safe_send(ctx, "Gimme something at least! Run `;help role`")
            return

        langs = [lang.casefold() for lang in langs]
        if 'none' in langs or 'n' in langs:
            none = True
            if len(langs) > 1:
                await hf.safe_send(ctx, "If you specify `none`, please don't specify other languages too. "
                                        "That's confusing!")
                return
        else:
            none = False

        for lang in langs:
            if lang not in langs_dict:
                await hf.safe_send(ctx, "I couldn't tell which language you're trying to assign. Type `;r help`")
                return
        if not user:
            await hf.safe_send(ctx, "I couldn't tell who you wanted to assign the role to. `;r <name> <lang>`")
            return

        # right now, user=a member object, lansg=a list of strings the user typed o/e/s/other/english/spanish/etc
        langs = [langs_dict[lang] for lang in langs]  # now langs is a list of role objects
        removed = []
        for role in all_roles:
            if role in user.roles:
                removed.append(role)
        if removed:
            await user.remove_roles(*removed)
        if not none:
            await user.add_roles(*langs)

        if none and not removed:
            await hf.safe_send(ctx, "There were no roles to remove!")
        elif none and removed:
            await hf.safe_send(ctx, f"I've removed the roles of {', '.join([r.mention for r in removed])} from "
                                    f"{user.display_name}.")
        elif removed:
            await hf.safe_send(ctx, f"I assigned {', '.join([r.mention for r in langs])} instead of "
                                    f"{', '.join([r.mention for r in removed])} to {user.display_name}.")
        else:
            await hf.safe_send(ctx, f"I assigned {', '.join([r.mention for r in langs])} to {user.display_name}.")


def setup(bot):
    bot.add_cog(Submod(bot))
