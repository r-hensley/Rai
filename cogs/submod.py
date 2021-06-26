import discord
from discord.ext import commands
from .utils import helper_functions as hf
import asyncio
from datetime import datetime, timedelta
import re

import os
dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

SP_SERV = 243838819743432704
JP_SERVER_ID = 189571157446492161

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

    @commands.command()
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    @hf.is_submod()
    async def ban(self, ctx, *, args):
        """Bans a user.  Usage: `;ban [time #d#h] <user> [reason]`
        Examples:   `;ban @Ryry013 being mean`   `;ban 2d3h @Abelian posting invite links`.
        On a certain Spanish server, helpers can ban users within an hour of their joining the server."""
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
            try:
                if re.search('^<@!?\d{17,22}>$', args[0]):
                    user_id = int(args[0].replace('<@', '').replace('!', '').replace('>', ''))
                    target = await self.bot.fetch_user(user_id)
                elif re.search('^\d{17,22}$', args[0]):
                    user_id = int(args[0])
                    target = await self.bot.fetch_user(user_id)
                else:
                    return
            except discord.NotFound:
                return
            except ValueError:
                await hf.safe_send("I couldn't find the user. Please try again.")
                return

            id_to_member_dict = {m.id: m for m in self.bot.recently_removed_members[str(ctx.guild.id)]}
            if user_id in id_to_member_dict:  # target is an ID
                target = id_to_member_dict[user_id]
                
        if not reason:
            reason = '(no reason given)'

        text = f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** XX"
        new_text = text.replace("XX", reason)
        if len(new_text) > 512:
            await hf.safe_send(ctx, "Discord only allows bans with a length of 512 characters. With my included "
                                    f"author tag, you are allowed {513 - len(text)} characters. Please reduce the "
                                    f"length of your ban message. ")
            return

        # this memorial exists to forever remember the robot head, may you rest in peace ['_']
        # this comment exists to wonder what the hell the robot head was...
        if hasattr(target, "joined_at"):  # will be false if the user is not in the server
            joined_at = datetime.utcnow() - target.joined_at
        else:
            joined_at = timedelta(minutes=61)  # arbitrarily bigger than 60 to fail the conditional

        if not (ctx.guild.id == 243838819743432704 and
                ctx.guild.get_role(258819531193974784) in ctx.author.roles and
                joined_at < timedelta(minutes=60)) and not \
                hf.admin_check(ctx):
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
        msg2 = f"Do you wish to continue?  Options:\n" \
               f"⠀・ `Yes` Silently ban the user\n" \
               f"⠀・ `Send` Ban the user and send them the above notification\n" \
               f"⠀・ `No` Cancel the ban\n"

        if ctx.author in self.bot.get_guild(257984339025985546).members:
            try:
                if 'crosspost' in self.bot.db['bans'][str(ctx.guild.id)]:
                    if not reason.startswith('⁣') and str(ctx.guild.id) in self.bot.db['bans']:  # no width space
                        if self.bot.db['bans'][str(ctx.guild.id)]['crosspost']:
                            crosspost_check = 1  # to cancel crosspost
                            msg2 += "⠀・ `Yes/Send -s` Do not crosspost this ban"
                    if not reason.startswith('⠀') and str(ctx.guild.id) in self.bot.db['bans']:  # invisible space
                        if not self.bot.db['bans'][str(ctx.guild.id)]['crosspost']:
                            crosspost_check = 2  # to specially crosspost
                            msg2 += "⠀・ `Yes/Send -c` Specially crosspost this ban"
            except KeyError:
                pass
        msg2 = await hf.safe_send(ctx, msg2)
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=40.0,
                                          check=lambda x: x.author == ctx.author and
                                                          x.content.casefold()[:4] in ['yes', 'yes ', 'no', 'send'])
        except asyncio.TimeoutError:
            try:
                await msg2.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
            await hf.safe_send(ctx, f"Timed out.  Canceling ban.")
            return
        content = msg.content.casefold()
        if content == 'no':
            try:
                await msg2.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
            await hf.safe_send(ctx, f"Canceling ban")
            return

        try:
            await msg2.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        text = text.replace("XX", reason)

        if content.endswith('-s'):  # these will be parsed in the on_member_ban event in logger.py
            text = '⁣' + text
        if content.endswith('-c'):
            text = '⠀' + text
        if content.startswith('send'):
            try:
                await target.send(embed=em)
            except discord.Forbidden:
                await hf.safe_send(ctx, "The target user has PMs disabled so I didn't send the notification.")
        try:
            if hasattr(target, 'ban'):  # if the user is in the server
                await target.ban(reason=text, delete_message_days=0)
            else:  # if the user is not in the server
                await ctx.guild.ban(target, reason=text, delete_message_days=0)
        except discord.Forbidden:
            await hf.safe_send(ctx, f"I couldn't ban that user. They're probably above me in the role list.")
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

    @commands.command()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    @commands.max_concurrency(1, commands.BucketType.member)
    @hf.is_submod()
    async def mute(self, ctx, *, args):
        """Mutes a user.  Syntax: `;mute <time> <member> [reason]`.  Example: `;mute 1d2h Abelian`."""
        args = args.split()

        try:
            last_modlog = self.bot.db['modlog'][str(ctx.guild.id)][str(ctx.author.id)][-1]
            event_time = datetime.strptime(last_modlog['date'], "%Y/%m/%d %H:%M UTC")
            if (datetime.utcnow() - event_time).total_seconds() < 70 and last_modlog['type'] == "Mute":
                if last_modlog['reason'].startswith("Antispam"):
                    return  # Prevents multiple mute calls for spammed text
        except KeyError:
            pass

        async def set_channel_overrides(role):
            failed_channels = []
            for channel in ctx.guild.voice_channels:
                if role not in channel.overwrites:
                    try:
                        await channel.set_permissions(role, speak=False)
                    except discord.Forbidden:
                        failed_channels.append(channel.name)
            for channel in ctx.guild.text_channels:
                if role not in channel.overwrites:
                    try:
                        await channel.set_permissions(role, send_messages=False, add_reactions=False,
                                                      attach_files=False)
                    except discord.Forbidden:
                        failed_channels.append(channel.name)
            return failed_channels

        if str(ctx.guild.id) not in self.bot.db['mutes']:
            await hf.safe_send(ctx, "Doing first-time setup of mute module.  I will create a `rai-mute` role, "
                                    "add then a permission override for it to every channel to prevent communication")
            role = await ctx.guild.create_role(name='rai-mute', reason="For use with ;mute command")
            config = self.bot.db['mutes'][str(ctx.guild.id)] = {'role': role.id, 'timed_mutes': {}}
            failed_channels = await set_channel_overrides(role)
            if failed_channels:
                await hf.safe_send(ctx,
                                   f"Couldn't add the role permission to {' ,'.join(failed_channels)}.  If a muted "
                                   f"member joins this (these) channel(s), they'll be able to type/speak.")
        else:
            config = self.bot.db['mutes'][str(ctx.guild.id)]
            role = ctx.guild.get_role(config['role'])
            await set_channel_overrides(role)

        re_result = None
        time_string: str = None
        target: discord.Member = None
        time: str = None
        new_args = args.copy()
        for arg in args:
            if not re_result:
                re_result = re.search('<?@?!?([0-9]{17,22})>?', arg)
                if re_result:
                    user_id = int(re_result.group(1))
                    target = ctx.guild.get_member(user_id)
                    new_args.remove(arg)
                    continue

            if not time_string:
                time_string, length = hf.parse_time(arg)  # time_string = "%Y/%m/%d %H:%M UTC"
                if time_string:  # length = a list: [days, hours]
                    time = arg
                    new_args.remove(arg)
                    continue

        args = new_args

        if not target:
            await hf.safe_send(ctx, "I could not find the user.  For warns and mutes, please use either an ID "
                                    "or a mention to the user (this is to prevent mistaking people).")
            return

        reason = ' '.join(args)
        silent = False
        if reason:
            if '-s' in reason or '-n' in reason:
                if ctx.guild.id == JP_SERVER_ID:
                    await hf.safe_send(ctx, "Maybe you meant to use Ciri?")
                reason = reason.replace(' -s', '').replace('-s ', '').replace('-s', '')
                silent = True

        if role in target.roles:
            await hf.safe_send(ctx, "This user is already muted (already has the mute role)")
            return
        await target.add_roles(role, reason=f"Muted by {ctx.author.name} in {ctx.channel.name}")

        if target.voice:  # if they're in a channel, move them out then in to trigger the mute
            voice_state = target.voice
            try:
                if ctx.guild.afk_channel:
                    try:
                        await target.move_to(ctx.guild.afk_channel)
                        await target.move_to(voice_state.channel)
                    except discord.HTTPException:
                        pass
                else:
                    for channel in ctx.guild.voice_channels:
                        if not channel.members:
                            try:
                                await target.move_to(channel)
                                await target.move_to(voice_state.channel)
                            except discord.HTTPException:
                                pass
                            break
            except discord.Forbidden:
                await hf.safe_send(ctx, "This user is in voice, but Rai lacks the permission to move users. If you "
                                        "give Rai this permission, then it'll move the user to the AFK channel and "
                                        "back to force the mute into effect. Otherwise, Discord's implementation of "
                                        "the mute won't take effect until the next time the user connects to a "
                                        "new voice channel.")
                pass

        if time_string:
            config['timed_mutes'][str(target.id)] = time_string

        notif_text = f"**{str(target)}** ({target.id}) has been **muted** from text and voice chat.\n"
        if time_string:
            notif_text = f"{notif_text[:-1]} for {time}."
        if reason:
            notif_text += f"\nReason: {reason}"
        emb = hf.red_embed(notif_text)
        if silent:
            emb.description += " (The user was not notified of this)"
        await hf.safe_send(ctx, embed=emb)

        modlog_config = hf.add_to_modlog(ctx, target, 'Mute', reason, silent, time)
        modlog_channel = self.bot.get_channel(modlog_config['channel'])

        emb = hf.red_embed(f"You have been muted on {ctx.guild.name} server")
        emb.color = discord.Color(int('ff8800', 16))  # embed
        if time_string:
            emb.add_field(name="Length", value=f"{time} (will be unmuted on {time_string})", inline=False)
        else:
            emb.add_field(name="Length", value="Indefinite", inline=False)
        if reason:
            emb.add_field(name="Reason", value=reason)
        if not silent:
            try:
                await target.send(embed=emb)
            except discord.Forbidden:
                await hf.safe_send(ctx, "This user has DMs disabled so I couldn't send the notification.  Canceling...")
                return

        emb.insert_field_at(0, name="User", value=f"{target.name} ({target.id})", inline=False)
        emb.description = "Mute"
        emb.add_field(name="Jump URL", value=ctx.message.jump_url, inline=False)
        emb.set_footer(text=f"Muted by {ctx.author.name} ({ctx.author.id})")
        try:
            if modlog_channel:
                if modlog_channel != ctx.channel:
                    await hf.safe_send(modlog_channel, embed=emb)
        except AttributeError:
            await hf.safe_send(ctx, embed=emb)

    @commands.command()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    @hf.is_submod()
    async def unmute(self, ctx, target_in, guild=None):
        """Unmutes a user

        Usage: `;unmute <user>`"""
        if isinstance(guild, str):
            guild = None
        if not guild:
            guild = ctx.guild
            target: discord.Member = await hf.member_converter(ctx, target_in)
        else:
            guild = self.bot.get_guild(int(guild))
            target: discord.Member = guild.get_member(int(target_in))
        config = self.bot.db['mutes'][str(guild.id)]
        role = guild.get_role(config['role'])

        voice_role = None
        if str(ctx.guild.id) in self.bot.db['voice_mutes']:
            voice_role = guild.get_role(self.bot.db['voice_mutes'][str(ctx.guild.id)]['role'])

        failed = False
        if target:
            target_id = target.id
            try:
                await target.remove_roles(role)
                failed = False
            except discord.HTTPException:
                pass

            if voice_role:
                try:
                    await target.remove_roles(voice_role)
                except discord.HTTPException:
                    pass

        else:
            if ctx.author == ctx.bot.user:
                target_id = target_in
            else:
                return

        if str(target_id) in config['timed_mutes']:
            del config['timed_mutes'][str(target_id)]

        if ctx.author != ctx.bot.user:
            emb = discord.Embed(description=f"**{target.name}#{target.discriminator}** has been unmuted.",
                                color=discord.Color(int('00ffaa', 16)))
            await hf.safe_send(ctx, embed=emb)

        if not failed:
            return True

    @commands.command(aliases=['w'])
    @hf.is_submod()
    async def warn(self, ctx, user, *, reason="None"):
        """Log a mod incident"""
        re_result = re.search('^<?@?!?([0-9]{17,22})>?$', user)
        if re_result:
            id = int(re_result.group(1))
            user = ctx.guild.get_member(id)
            if not user:
                reason += " -s"
                try:
                    user = await self.bot.fetch_user(id)
                except discord.NotFound:
                    user = None
        else:
            user = None
        if not user:
            await hf.safe_send(ctx, "I could not find the user.  For warns and mutes, please use either an ID or "
                                    "a mention to the user (this is to prevent mistaking people).")
            return
        emb = hf.red_embed(f"Warned on {ctx.guild.name} server")
        silent = False
        if '-s' in reason:
            silent = True
            reason = reason.replace(' -s', '').replace('-s ', '').replace('-s', '')
            emb.description = "Log *(This incident was not sent to the user)*"
        emb.color = discord.Color(int('ffff00', 16))  # embed ff8800
        emb.add_field(name="User", value=f"{user.name} ({user.id})", inline=False)
        emb.add_field(name="Reason", value=reason, inline=False)
        if not silent:
            try:
                await hf.safe_send(user, embed=emb)
            except discord.Forbidden:
                await hf.safe_send(ctx, "I could not send the message, maybe the user has DMs disabled. Canceling "
                                        "warn (consider using the -s tag to not send a message).")
                return
        if not emb.description:
            emb.description = "Warning"
        emb.add_field(name="Jump URL", value=ctx.message.jump_url, inline=False)
        footer_text = f"Warned by {ctx.author.name} ({ctx.author.id})"
        if silent:
            footer_text = "Logged by" + footer_text[9:]
        emb.set_footer(text=footer_text)
        config = hf.add_to_modlog(ctx, user, 'Warning', reason, silent)
        modlog_channel = self.bot.get_channel(config['channel'])
        try:
            num_of_entries = len(self.bot.db['modlog'][str(ctx.guild.id)][str(user.id)])
            if num_of_entries > 1:
                emb.add_field(name="Total number of modlog entries", value=num_of_entries)
        except KeyError:
            pass
        if modlog_channel:
            if modlog_channel != ctx.channel:
                await hf.safe_send(modlog_channel, embed=emb)
        await hf.safe_send(ctx, embed=emb)

    @commands.command(aliases=["cleanup", "bclr"])
    @commands.bot_has_permissions(manage_messages=True)
    @hf.is_submod()
    async def botclear(self, ctx, num_of_messages=10):
        """Usage: `;botclear num[default:10]`

        Deletes all bot messages in the last `num` messages.

        Defaults to 10, so just `;botclear` searches last ten messages."""
        try:
            num_of_messages = int(num_of_messages)
        except ValueError:
            await hf.safe_send(ctx, "Please input an integer number of messages")
            return
        if num_of_messages > 50:
            num_of_messages = 50
            await hf.safe_send(ctx, "Setting number of messages to the maximum of `50`.", delete_after=3)

        await ctx.channel.purge(limit=num_of_messages, check=lambda m: m.author.bot and m.content[0:7] != "Setting",
                                after=datetime.utcnow() - timedelta(minutes=60))
        try:
            await ctx.message.add_reaction('✅')
            await asyncio.sleep(1)
            await ctx.message.delete()
        except discord.Forbidden:
            pass


def setup(bot):
    bot.add_cog(Submod(bot))
