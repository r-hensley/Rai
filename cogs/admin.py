import discord
from discord.ext import commands
import json
import urllib.request
from .utils import helper_functions as hf
import asyncio
import re
from datetime import datetime, timedelta
import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Admin(commands.Cog):
    """Stuff for admins"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return hf.admin_check(ctx)

    @commands.command(hidden=True)
    async def crosspost(self, ctx):
        """Makes Rai crosspost all your ban audits"""
        if str(ctx.guild.id) in self.bot.db['bans']:
            config = self.bot.db['bans'][str(ctx.guild.id)]
            try:
                config['crosspost'] = not config['crosspost']
            except KeyError:
                config['crosspost'] = True
        else:
            config = self.bot.db['bans'][str(ctx.guild.id)] = {'enable': False, 'channel': None, 'crosspost': True}
        if config['crosspost']:
            await ctx.send(f"Rai will now crosspost ban logs")
        else:
            await ctx.send(f"Rai won't crosspost ban logs anymore")
        await hf.dump_json()

    @commands.group(invoke_without_command=True)
    async def stats(self, ctx):
        """Enable/disable keeping of statistics for users (`;u`)"""
        guild = str(ctx.guild.id)
        if guild in self.bot.db['stats']:
            self.bot.db['stats'][guild]['enable'] = not self.bot.db['stats'][guild]['enable']
        else:
            self.bot.db['stats'][guild] = {'enable': True,
                                           'messages': {},
                                           'hidden': [],
                                           'voice':
                                               {'in_voice': {},
                                                'total_time': {}}
                                           }
        await ctx.send(f"Logging of stats is now set to {self.bot.db['stats'][guild]['enable']}.")
        await hf.dump_json()

    @stats.command()
    async def hide(self, ctx):
        """Hides the current channel from being shown in user stat pages"""
        try:
            config = self.bot.db['stats'][str(ctx.guild.id)]['hidden']
        except KeyError:
            return
        channel = str(ctx.channel.id)
        if channel in config:
            config.remove(channel)
            await ctx.send(f"Removed this channel from the list of hidden channels.  It will now be shown when "
                           f"someone calls their stats page.")
        else:
            config.append(channel)
            await ctx.send(f"Hid this channel.  When someone calls their stats page, it will not be shown.")
        await hf.dump_json()

    @commands.command()
    @hf.is_admin()
    @commands.bot_has_permissions(ban_members=True)
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, *args):
        """Bans a user.  Usage: `;ban [time #d#h] <user> [-s] [reason]`  Example: `;ban @Ryry013 being mean` or
        `;ban 2d3h @Abelian -s posting invite links`"""
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
        em = discord.Embed(title=f"You've been banned from {ctx.guild.name}")
        if length:
            em.description = f"You will be unbanned automatically at {time_string} " \
                             f"(in {length[0]} days and {length[1]} hours)"
        else:
            em.description = "This ban is indefinite."
        if reason != '(no reason given)':
            if '-silent' in reason or '-s' in reason:
                reason = reason.replace('-silent ', '').replace('-s ', '')
                reason = '⁣' + reason
            em.add_field(name="Reason:", value=reason)
        await ctx.send("You are about to perform the following action: ", embed=em)
        msg2 = f"Do you wish to continue?  Type `yes` to ban, `send` to ban and send the above notification " \
               f"to the user, or `no` to cancel."
        if ctx.author in self.bot.get_guild(257984339025985546).members and not reason.startswith('⁣'):
            try:
                if self.bot.db['bans'][str(ctx.guild.id)]['crosspost']:
                    msg2 += "\n(To not crosspost this, cancel the ban and put `-s` or `-silent` before the reason)"
            except KeyError:
                pass
        msg2 = await ctx.send(msg2)
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=40.0,
                                          check=lambda x: x.author == ctx.author and
                                                          x.content.casefold() in ['yes', 'no', 'send'])
        except asyncio.TimeoutError:
            await ctx.send(f"Timed out.  Canceling ban.")
            return
        content = msg.content.casefold()
        if content == 'no':
            await ctx.send(f"Canceling ban")
            await msg2.delete()
            return
        text = f"*by* {ctx.author.mention} ({ctx.author.name})\n**Reason:** {reason}"
        if reason.startswith('⁣'):
            text = '⁣' + text
        if content == 'send':
            await target.send(embed=em)
        try:
            await target.ban(reason=text)
        except discord.Forbidden:
            await ctx.send(f"I couldn't ban that user.  They're probably above me in the role list.")
            return
        if length:
            config = self.bot.db['bans'].setdefault(str(ctx.guild.id),
                                                    {'enable': False, 'channel': None, 'timed_bans': {}})
            timed_bans = config.setdefault('timed_bans', {})
            timed_bans[str(target.id)] = time_string
            await hf.dump_json()
        await ctx.send(f"Successfully banned")

    @commands.command(hidden=True)
    async def post_rules(self, ctx):
        """Posts the rules page on the Chinese/Spanish server"""
        if ctx.channel.id in [511097200030384158, 450170164059701268]:  # chinese server
            download_link = 'https://docs.google.com/document/u/0/export?format=txt' \
                            '&id=159L5Z1UEv7tJs_RurM1-GkoZeYAxTpvF5D4n6enqMuE' \
                            '&token=AC4w5VjkHYH7R7lINNiyXXfX29PlhW8qfg%3A1541923812297' \
                            '&includes_info_params=true'
            channel = 0
        elif ctx.channel.id in [243859172268048385, 513222365581410314]:  # english rules
            download_link = 'https://docs.google.com/document/export?format=txt' \
                            '&id=1kOML72CfGMtdSl2tNNtFdQiAOGMCN2kZedVvIHQIrw8' \
                            '&token=AC4w5Vjrirj8E-5sNyCUvJOAEoQqTGJLcA%3A1542430650712' \
                            '&includes_info_params=true'
            channel = 1
        elif ctx.channel.id in [499544213466120192, 513222453313667082]:  # spanish rules
            download_link = 'https://docs.google.com/document/export?format=txt' \
                            '&id=12Ydx_5M6KuO5NCfUrSD1P_eseR6VJDVAgMfOntJYRkM' \
                            '&token=AC4w5ViCHzxJBaDe7nEOyBL75Tud06QVow%3A1542432513956' \
                            '&includes_info_params=true'
            channel = 2
        else:
            return

        async for message in ctx.channel.history(limit=30):
            try:
                await message.delete()
            except discord.errors.NotFound:
                pass
        rules = urllib.request.urlopen(download_link).read().decode('utf-8-sig')
        rules = rules.replace('__', '').replace('{und}',
                                                '__')  # google uses '__' page breaks so this gets around that
        rules = rules.split('########')
        for page in rules:
            # print([page[:30]])
            if page[0:6] == '!image':
                url = page.split(' ')[1].replace('\r', '').replace('\n', '')
                with open('image', 'wb') as f:
                    urllib.request.urlretrieve(url, "image_file.png")
                msg = await ctx.send(file=discord.File('image_file.png'))
            elif page[:30].replace('\r', '').replace('\n', '').startswith('!lang'):
                # print('lang', [page])
                spanishnative = self.bot.get_emoji(524733330525257729)
                englishnative = self.bot.get_emoji(524733316193058817)
                othernative = self.bot.get_emoji(524733977991315477)
                fluentspanish = self.bot.get_emoji(524732626674909205)
                fluentenglish = self.bot.get_emoji(524732533775007744)
                mods = self.bot.get_emoji(524733987092955138)
                post = page.replace('{spanishnative}', str(spanishnative)). \
                    replace('{englishnative}', str(englishnative)). \
                    replace('{othernative}', str(othernative)). \
                    replace('{fluentspanish}', str(fluentspanish)). \
                    replace('{fluentenglish}', str(fluentenglish)). \
                    replace('{mods}', str(mods))
                msg = await ctx.send(post[7:])
            elif page[:30].replace('\r', '').replace('\n', '').startswith('!roles'):
                # print('roles', [page])
                if channel == 0:  # chinese
                    emoji = self.bot.get_emoji(358529029579603969)  # blobflags
                    post = page[8:].replace('{emoji}', str(emoji))
                    msg = await ctx.send(post)
                    self.bot.db['roles'][str(ctx.guild.id)]['message'] = msg.id
                    await msg.add_reaction("🔥")  # hardcore
                    await msg.add_reaction("📝")  # correct me
                    await msg.add_reaction("🗣")  # debate
                    await msg.add_reaction("🖋")  # handwriting
                    await msg.add_reaction("🎙")  # VC all
                elif channel == 1 or channel == 2:  # english/spanish
                    emoji = self.bot.get_emoji(513211476790738954)
                    post = page.replace('{table}', str(emoji))
                    msg = await ctx.send(post[8:])
                    await msg.add_reaction("🎨")
                    await msg.add_reaction("🐱")
                    await msg.add_reaction("🐶")
                    await msg.add_reaction("🎮")
                    await msg.add_reaction(emoji)  # table
                    await msg.add_reaction('🔥')
                    await msg.add_reaction("👪")
                    await msg.add_reaction("🎥")
                    await msg.add_reaction("🎵")
                    await msg.add_reaction("❗")
                    await msg.add_reaction("👚")
                    await msg.add_reaction("💻")
                    await msg.add_reaction("📔")
                    await msg.add_reaction("✏")
                    await msg.add_reaction('📆')
                    if channel == 1:
                        self.bot.db['roles'][str(ctx.guild.id)]['message1'] = msg.id
                    elif channel == 2:
                        self.bot.db['roles'][str(ctx.guild.id)]['message2'] = msg.id
                else:
                    await ctx.send(f"Something went wrong")
                    return
            else:
                msg = await ctx.send(page)
            if '<@ &' in msg.content:
                await msg.edit(content=msg.content.replace('<@ &', '<@&'))

    @commands.group(invoke_without_command=True, hidden=True)
    async def hardcore(self, ctx):
        msg = await ctx.send("Hardcore mode: if you have the `Learning English` role, you can not use any kind of "
                             "Chinese in  your messages.  Otherwise, your messages must consist of Chinese.  If you"
                             " wish to correct a learner, attach a `*` to your message, and it will not be deleted.  "
                             "\n\nUse the below reaction to enable/disable hardcore mode.")
        try:
            self.bot.db['hardcore'][str(ctx.guild.id)]['message'] = msg.id
        except KeyError:
            role = await ctx.guild.create_role(name='🔥Hardcore🔥')
            self.bot.db['hardcore'][str(ctx.guild.id)] = {'message': msg.id, 'role': role.id}
        await msg.add_reaction("🔥")
        await hf.dump_json()

    @hardcore.command()
    async def ignore(self, ctx):
        config = self.bot.db['hardcore']["266695661670367232"]
        try:
            if ctx.channel.id not in config['ignore']:
                config['ignore'].append(ctx.channel.id)
                await ctx.send(f"Added {ctx.channel.name} to list of ignored channels for hardcore mode")
            else:
                config['ignore'].remove(ctx.channel.id)
                await ctx.send(f"Removed {ctx.channel.name} from list of ignored channels for hardcore mode")
        except KeyError:
            config['ignore'] = [ctx.channel.id]
            await ctx.send(f"Added {ctx.channel.name} to list of ignored channels for hardcore mode")
        await hf.dump_json()

    @commands.group(invoke_without_command=True)
    async def captcha(self, ctx):
        """Sets up a checkmark requirement to enter a server"""
        await ctx.send('This module sets up a requirement to enter a server based on a user pushing a checkmark.  '
                       '\n1) First, do `;captcha toggle` to setup the module'
                       '\n2) Then, do `;captcha set_channel` in the channel you want to activate it in.'
                       '\n3) Then, do `;captcha set_role <role name>` '
                       'to set the role you wish to add upon them captchaing.'
                       '\n4) Finally, do `;captcha post_message` to post the message people will react to.')

    @captcha.command()
    @commands.bot_has_permissions(manage_roles=True)
    async def toggle(self, ctx):
        guild = str(ctx.guild.id)
        if guild in self.bot.db['captcha']:
            guild_config = self.bot.db['captcha'][guild]
            if guild_config['enable']:
                guild_config['enable'] = False
                await ctx.send('Captcha module disabled')
            else:
                guild_config['enable'] = True
                await ctx.send('Captcha module enabled')
        else:
            self.bot.db['captcha'][guild] = {'enable': True, 'channel': '', 'role': ''}
            await ctx.send('Captcha module setup and enabled.')
        await hf.dump_json()

    @captcha.command(name="set_channel")
    async def captcha_set_channel(self, ctx):
        guild = str(ctx.guild.id)
        if guild not in self.bot.db['captcha']:
            await self.toggle
        guild_config = self.bot.db['captcha'][guild]
        guild_config['channel'] = ctx.channel.id
        await ctx.send(f'Captcha channel set to {ctx.channel.name}')
        await hf.dump_json()

    @captcha.command(name="set_role")
    async def captcha_set_role(self, ctx, *, role_input: str = None):
        if not role_input:
            instr_msg = await ctx.send(f"Please input the exact name of the role new users will receive")
            try:
                reply_msg = await self.bot.wait_for('message',
                                                    timeout=20.0,
                                                    check=lambda x: x.author == ctx.author)
                await instr_msg.delete()
                await reply_msg.delete()
            except asyncio.TimeoutError:
                await ctx.send("Module timed out")
                await instr_msg.delete()
                return
        guild = str(ctx.guild.id)
        if guild not in self.bot.db['captcha']:
            await self.toggle
        guild_config = self.bot.db['captcha'][guild]
        role = discord.utils.find(lambda role: role.name == role_input, ctx.guild.roles)
        if not role:
            await ctx.send('Failed to find a role.  Please type the name of the role after the command, like '
                           '`;captcha set_role New User`')
        else:
            guild_config['role'] = role.id
            await ctx.send(f'Set role to {role.name} ({role.id})')
        await hf.dump_json()

    @captcha.command(name="post_message")
    async def captcha_post_message(self, ctx):
        guild = str(ctx.guild.id)
        if guild in self.bot.db['captcha']:
            guild_config = self.bot.db['captcha'][guild]
            if guild_config['enable']:
                msg = await ctx.send('Please react with the checkmark to enter the server')
                guild_config['message'] = msg.id
                await hf.dump_json()
                await msg.add_reaction('✅')

    @commands.command(aliases=['purge', 'prune'])
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx, num=None, *args):
        """Deletes messages from a channel, ;clear <num_of_messages> [<user> <after_message_id>]"""
        if len(num) == 18:
            args = ('0', int(num))
            num = 100
        if 100 < int(num):
            msg = await ctx.send(f"You're trying to delete the last {num} messages.  Please type `y` to confirm this.")
            try:
                await self.bot.wait_for('message', timeout=10,
                                        check=lambda m: m.author == ctx.author and m.content == 'y')
            except asyncio.TimeoutError:
                await msg.edit(content="Canceling channel prune", delete_after=5.0)
        try:
            await ctx.message.delete()
        except discord.errors.NotFound:
            pass
        if args:
            if args[0] == '0':
                user = None
            if args[0] != '0':
                user = await hf.member_converter(ctx, args[0])
                if not user:
                    return
            try:
                msg = await ctx.channel.fetch_message(args[1])
            except discord.errors.NotFound:  # invaid message ID given
                await ctx.send('Message not found')
                return
            except IndexError:  # no message ID given
                print('>>No message ID found<<')
                msg = None
                pass
        else:
            user = None
            msg = None

        try:
            if not user and not msg:
                await ctx.channel.purge(limit=int(num))
            if user and not msg:
                await ctx.channel.purge(limit=int(num), check=lambda m: m.author == user)
            if not user and msg:
                await ctx.channel.purge(limit=int(num), after=msg)
                try:
                    await msg.delete()
                except discord.errors.NotFound:
                    pass
            if user and msg:
                await ctx.channel.purge(limit=int(num), check=lambda m: m.author == user, after=msg)
                try:
                    await msg.delete()
                except discord.errors.NotFound:
                    pass
        except TypeError:
            pass
        except ValueError:
            await ctx.send('You must put a number after the command, like `;await clear 5`')
            return

    @commands.command()
    @commands.bot_has_permissions(ban_members=True)
    async def auto_bans(self, ctx):
        """Auto bans for amazingsexdating/users who join with invite link names"""
        config = hf.database_toggle(ctx, self.bot.db['auto_bans'])
        if config['enable']:
            await ctx.send('Enabled the auto bans module.  I will now automatically ban all users who join with '
                           'a discord invite link username or who join and immediately send an amazingsexdating link')
        else:
            await ctx.send('Disabled the auto bans module.  I will no longer auto ban users who join with a '
                           'discord invite link username or who spam a link to amazingsexdating.')
        await hf.dump_json()

    @commands.command()
    async def set_submod_role(self, ctx, role_name):
        """Set the submod role for your server.  Type the exact name of the role like `;set_submod_role Mods`."""
        config = hf.database_toggle(ctx, self.bot.db['submod_role'])
        if 'enable' in config:
            del (config['enable'])
        submod_role = discord.utils.find(lambda role: role.name == role_name, ctx.guild.roles)
        if not submod_role:
            await ctx.send("The role with that name was not found")
            return None
        config['id'] = submod_role.id
        await ctx.send(f"Set the submod role to {submod_role.name} ({submod_role.id})")
        await hf.dump_json()

    @commands.command()
    async def set_mod_role(self, ctx, role_name):
        """Set the mod role for your server.  Type the exact name of the role like `;set_mod_role Mods`."""
        config = hf.database_toggle(ctx, self.bot.db['mod_role'])
        if 'enable' in config:
            del (config['enable'])
        mod_role = discord.utils.find(lambda role: role.name == role_name, ctx.guild.roles)
        if not mod_role:
            await ctx.send("The role with that name was not found")
            return None
        config['id'] = mod_role.id
        await ctx.send(f"Set the mod role to {mod_role.name} ({mod_role.id})")
        await hf.dump_json()

    @commands.command(aliases=['setmodchannel'])
    async def set_mod_channel(self, ctx):
        """Sets the mod channel for your server.  Run this command in the mod channel."""
        self.bot.db['mod_channel'][str(ctx.guild.id)] = ctx.channel.id
        await ctx.send(f"Set the mod channel for this server as {ctx.channel.name}.")
        await hf.dump_json()

    @commands.command()
    async def readd_roles(self, ctx):
        """Automatically readd roles to users who left the server and then rejoin."""
        config = hf.database_toggle(ctx, self.bot.db['readd_roles'])
        if config['enable']:
            if not ctx.me.guild_permissions.manage_roles:
                await ctx.send("I lack permission to manage roles.  Please fix that before enabling this")
                hf.database_toggle(ctx, self.bot.db['readd_roles'])
                return
            await ctx.send(f"I will readd roles to people who have previously left the server")
        else:
            await ctx.send("I will NOT readd roles to people who have previously left the server")
        if 'users' not in config:
            config['users'] = {}
        await hf.dump_json()

    @commands.group(invoke_without_command=True, aliases=['svw', 'supervoicewatch'], hidden=True)
    async def super_voicewatch(self, ctx):
        """Log everytime chosen users join/leave the voice channels.  This sets the super voice watch log channel"""
        if str(ctx.guild.id) not in self.bot.db['mod_channel']:
            await ctx.send("Before using this, you have to set your mod channel using `;set_mod_channel` in the "
                           "channel you want to designate.")
            return
        config = self.bot.db['super_voicewatch'].setdefault(str(ctx.guild.id), {"users": [], "channel": ctx.channel.id})
        config['channel'] = ctx.channel.id
        await hf.dump_json()
        await ctx.send(f"I've set the log channel for super voice watch to {ctx.channel.mention}\n\n"
                       "**About svw:** Puts a message in the mod channel every time someone on the super watchlist "
                       "joins a voice channel.  Use `;super_voicewatch add USER` or `'super_voicewatch remove USER` to "
                       "manipulate the list.  Type `;super_voicewatch list` to see a full list.  Alias: `;svw`")

    @super_voicewatch.command(name="add")
    async def voicewatch_add(self, ctx, member: discord.Member):
        """Add a member to super voice watch"""
        if str(ctx.guild.id) not in self.bot.db['mod_channel']:
            await ctx.send("Before using this, you have to set your mod channel using `;set_mod_channel` in the "
                           "channel you want to designate.")
            return
        config = self.bot.db['super_voicewatch'].setdefault(str(ctx.guild.id), {'users': [], 'channel': ctx.channel.id})
        config['users'].append(member.id)
        await ctx.send(f"Added `{member.name} ({member.id})` to the super voice watchlist.")
        await hf.dump_json()

    @super_voicewatch.command(name="remove")
    async def voicewatch_remove(self, ctx, member: discord.Member):
        """Remove a user from super voice watch"""
        config = self.bot.db['super_voicewatch'].setdefault(str(ctx.guild.id), {'users': [], 'channel': ctx.channel.id})
        try:
            config['users'].remove(member.id)
        except ValueError:
            await ctx.send("That user was not in the watchlist.")
            return
        await ctx.send(f"Removed `{member.name} ({member.id})` from the super voice watchlist.")
        await hf.dump_json()

    @super_voicewatch.command(name="list")
    async def super_voicewatch_list(self, ctx):
        """Lists the users in super voice watch"""
        string = ''
        try:
            config = self.bot.db['super_voicewatch'][str(ctx.guild.id)]
        except KeyError:
            await ctx.send("Voice watchlist not set-up yet on this server.  Run `;super_voicewatch`")
            return
        if not config['users']:
            await ctx.send("The voice watchlist is empty")
            return
        for ID in config['users']:
            member = ctx.guild.get_member(ID)
            if member:
                string += f"{member.mention} `({member.name}#{member.discriminator} {member.id})`\n"
            else:
                string += f"{ID}\n"
        try:
            await ctx.send(string)
        except discord.errors.HTTPException:
            await ctx.send(string[0:2000])
            await ctx.send(string[2000:])

    @commands.command(hidden=True)
    async def command_into_voice(self, ctx, member):
        if not ctx.author == self.bot.user:
            return
        await self.into_voice(member)

    async def into_voice(self, member):
        if member.bot:
            return
        guild = str(member.guild.id)
        member_id = str(member.id)
        config = self.bot.db['stats'][guild]['voice']
        config['in_voice'][member_id] = datetime.utcnow().strftime("%Y/%m/%d %H:%M UTC")

    @commands.command(hidden=True)
    async def command_out_of_voice(self, ctx, member, date_str=None):
        if not ctx.author == self.bot.user:
            return
        await self.out_of_voice(member, date_str=None)

    async def out_of_voice(self, member, date_str=None):
        guild = str(member.guild.id)
        member_id = str(member.id)
        config = self.bot.db['stats'][guild]['voice']
        if member_id not in config['in_voice']:
            return

        # calculate how long they've been in voice
        join_time = datetime.strptime(config['in_voice'][str(member.id)], "%Y/%m/%d %H:%M UTC")
        total_length = (datetime.utcnow() - join_time).seconds
        hours = total_length // 3600
        minutes = total_length % 3600 // 60
        del config['in_voice'][member_id]

        # add to their total
        if not date_str:
            date_str = datetime.utcnow().strftime("%Y%m%d")
        if date_str not in config['total_time']:
            config['total_time'][date_str] = {}
        today = config['total_time'][date_str]
        if member_id not in today:
            today[member_id] = [hours, minutes]
        else:
            today[member_id][0] += hours
            today[member_id][1] += minutes

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        async def superwatch_check():
            try:
                config = self.bot.db['super_voicewatch'][str(member.guild.id)]
            except KeyError:
                return
            if member.id in config['users'] and not before.channel and after.channel:
                channel = self.bot.get_channel(config['channel'])
                await channel.send(f"{member.mention} is on the voice superwatch list and has joined a voice channel "
                                   f"({after.channel.name})")
        await superwatch_check()

        """voice stats"""
        # voice
        # 	in_voice:
        # 		user1:
        # 			enter_utc
        # 	total_time:
        # 		user1: hours
        async def voice_update():
            guild = str(member.guild.id)
            if guild not in self.bot.db['stats']:
                return
            if not self.bot.db['stats'][guild]['enable']:
                return

            if not before.channel and after.channel:  # joins voice
                await self.into_voice(member)
            if before.channel and not after.channel:
                await self.out_of_voice(member)
        await voice_update()


    @commands.group(invoke_without_command=True, aliases=['superwatch', 'sw'], hidden=True)
    async def super_watch(self, ctx):
        config = self.bot.db['super_watch'].setdefault(str(ctx.guild.id),
                                                       {"users": [], "channel": ctx.channel.id})
        config['channel'] = ctx.channel.id
        await ctx.send(f"Messages sent from users on the super_watch list will be sent to {ctx.channel.name} "
                       f"({ctx.channel.id}).  \n\n"
                       f"Type `;super_watch add <ID>` to add someone, `;super_watch remove "
                       f"<ID>` to remove them from the list later.  You can change the channel that super_watch "
                       f"sends posts to in the future by typing `;super_watch` again.  \n\n"
                       f"Aliases for this command are: `;superwatch`, `;sw`.")
        await hf.dump_json()

    @super_watch.command(name="add")
    async def superwatch_add(self, ctx, target):
        if str(ctx.guild.id) not in self.bot.db['super_watch']:
            await ctx.invoke(self.super_watch)
        config = self.bot.db['super_watch'][str(ctx.guild.id)]['users']
        target = await hf.member_converter(ctx, target)
        if not target:  # invalid user given
            return
        if target.id not in config:
            config.append(target.id)
            await ctx.send(f"Added {target.name} to super_watch list")
            await hf.dump_json()
        else:
            await ctx.send(f"{target.name} is already on the super_watch list")

    @super_watch.command(name="remove")
    async def superwatch_remove(self, ctx, target):
        config = self.bot.db['super_watch'][str(ctx.guild.id)]['users']
        try:
            target = await commands.MemberConverter().convert(ctx, target)
            target = target.id
        except commands.errors.BadArgument:  # invalid user given
            target = int(target)
        try:
            config.remove(target)
            await ctx.send(f"Removed <@{target}> from super_watch list")
        except ValueError:
            await ctx.send(f"That user wasn't on the super_watch list")
        await hf.dump_json()

    @super_watch.command(name="list")
    async def super_watch_list(self, ctx):
        config = self.bot.db['super_watch'][str(ctx.guild.id)]['users']
        users = [f"<@{ID}>" for ID in config]
        if config:
            await ctx.send(f"Users currently on the super_watch list: {', '.join(users)}")
        else:
            await ctx.send("There's currently no one on the super_watch list")

    @commands.group(invoke_without_command=True, aliases=['setprefix'])
    async def set_prefix(self, ctx, prefix):
        """Sets a custom prefix for the bot"""
        if prefix:
            self.bot.db['prefix'][str(ctx.guild.id)] = prefix
            await ctx.send(f"Set prefix to `{prefix}`.  You can change it again, or type `{prefix}set_prefix reset` "
                           f"to reset it back to the default prefix of `;`")
            await hf.dump_json()
        else:
            prefix = self.bot.db['prefix'].get(str(ctx.guild.id), ';')
            await ctx.send(f"This is the command to set a custom prefix for the bot.  The current prefix is "
                           f"`{prefix}`.  To change this, type `{prefix}set_prefix [prefix]` (for example, "
                           f"`{prefix}set_prefix !`).  Type `{prefix}set_prefix reset` to reset to the default prefix.")

    @set_prefix.command(name='reset')
    async def prefix_reset(self, ctx):
        try:
            prefix = self.bot.db['prefix']
            del prefix[str(ctx.guild.id)]
            await ctx.send("The command prefix for this guild has successfully been reset to `;`")
            await hf.dump_json()
        except KeyError:
            await ctx.send("This guild already uses the default command prefix.")

    def make_options_embed(self, list_in):  # makes the options menu
        emb = discord.Embed(title='Options Menu',
                            description="Reply with any of the option numbers or letters (b/x)\n")
        counter = 1
        options = ''
        for option in list_in:
            options += f"**{counter})** {option}\n"
            counter += 1
        options += "\n**b)** Go back\n"
        options += "**x)** Close the options menu"
        emb.add_field(name="Options", value=options)
        return emb

    async def wait_menu(self, ctx, menu, emb_in, choices_in):  # posts wait menu, gets a response, returns choice
        if menu:
            await menu.delete()
        menu = await ctx.send(embed=emb_in)
        try:
            msg = await self.bot.wait_for('message',
                                          timeout=60.0,
                                          check=lambda x: x.content.casefold() in choices_in and x.author == ctx.author)
        except asyncio.TimeoutError:
            await ctx.send("Menu timed out")
            await menu.delete()
            return 'time_out', menu
        await msg.delete()

        return msg.content, menu

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def options(self, ctx, menu=None):
        """A comprehensive options and configuration menu for the bot"""
        if menu:
            if not isinstance(menu, discord.Message):
                menu = None

        while True:
            options = ["Set/view the mod role (`;set_mod_role <role name>`)",  # 1
                       "Set/view the mod channel (`;set_mod_channel`)",  # 2
                       "Set/view the custom prefix (`;set_prefix <prefix>`)",  # 3
                       "Logging modules",  # 4
                       "Report module (`;report`)",  # 5
                       "Setup a questions channel (`;q`)",  # 6
                       "Automatically readd roles to users who rejoin the server (`;readd_roles`)",  # 7
                       "Reaction-to-enter requirement for the server (`;captcha`)",  # 8
                       "Super voice watch (`;svw`)",  # 9
                       "Super text watch (`;sw`)",  # 10
                       ]
            emb = self.make_options_embed(options)
            emb.description = "(WIP) " + emb.description
            choices = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'x']
            try:
                choice, menu = await self.wait_menu(ctx, menu, emb, choices)
            except discord.Forbidden:
                await ctx.send(f"I lack the ability to manage messages, which I require for the options module")
                return
            if choice == 'time_out':
                return
            elif choice == 'x':
                await menu.delete()
                await ctx.send(f"Closing options menu")
                return


#           main > set mod role
            elif choice == '1':
                while True:
                    options = ['Set the mod role (`;set_mod_role`)', "Unset the mod role",
                               "Set the submod role (currently only for the mute and ;question answer commands) "
                               "(`;set_submod_role`)", "Unset the submod role"]
                    emb = self.make_options_embed(options)
                    emb.title = "Setting mod role"
                    try:
                        config = self.bot.db['mod_role'][str(ctx.guild.id)]
                        role = ctx.guild.get_role(config['id'])
                        emb.description = f"Current role is {role.mention} ({role.id})\n" + emb.description
                    except KeyError:
                        emb.description = f"No role is currently set\n" + emb.description

                    choices = ['1', '2', '3', '4', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await ctx.send(f"Closed options menu")
                        await menu.delete()
                        return
                    elif choice == '1':
                        instr_msg = await ctx.send("Please input the exact name of the role you wish to set as "
                                                   "the mod role")
                        reply_msg = await self.bot.wait_for('message',
                                                            timeout=20.0,
                                                            check=lambda x: x.author == ctx.author)
                        await ctx.invoke(self.set_mod_role, reply_msg.content)
                        await instr_msg.delete()
                        await reply_msg.delete()
                    elif choice == '2':
                        try:
                            del self.bot.db['mod_role'][str(ctx.guild.id)]
                            await ctx.send("Removed the setting for a mod role")
                        except KeyError:
                            await ctx.send("You currently don't have a mod role set")
                    elif choice == '3':
                        instr_msg = await ctx.send("Please input the exact name of the role you wish to set as "
                                                   "the submod role")
                        reply_msg = await self.bot.wait_for('message',
                                                            timeout=20.0,
                                                            check=lambda x: x.author == ctx.author)
                        await ctx.invoke(self.set_submod_role, reply_msg.content)
                        await instr_msg.delete()
                        await reply_msg.delete()
                    elif choice == '4':
                        try:
                            del self.bot.db['submod_role'][str(ctx.guild.id)]
                            await ctx.send("Removed the setting for a submod role")
                        except KeyError:
                            await ctx.send("You currently don't have a submod role set")


#           main > set mod channel
            elif choice == '2':
                while True:
                    options = ['Set the mod channel as this channel (`;set_mod_channel`)', "Unset the mod channel"]
                    emb = self.make_options_embed(options)
                    emb.title = "Setting mod channel"
                    config = self.bot.db['mod_channel']
                    try:
                        channel = ctx.guild.get_channel(config[str(ctx.guild.id)])
                        emb.description = f"Current channel is {channel.mention} ({channel.id})\n" + emb.description
                    except KeyError:
                        emb.description = f"There is no mod channel currently set\n" + emb.description

                    choices = ['1', '2', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await ctx.send(f"Closed options menu")
                        await menu.delete()
                        return
                    elif choice == '1':
                        await ctx.invoke(self.set_mod_channel)
                    elif choice == '2':
                        try:
                            del config[str(ctx.guild.id)]
                            await ctx.send("Unset the mod channel")
                        except KeyError:
                            await ctx.send("There is no mod channel set")


#           # main > set custom prefix
            elif choice == '3':
                while True:
                    options = ['Set the custom prefix (`;set_prefix <prefix>`)',
                               "Reset the server's custom prefix (`<prefix>set_prefix reset`)"]
                    emb = self.make_options_embed(options)
                    emb.title = "Custom Prefix"
                    config = self.bot.db['prefix']
                    current_prefix = config.get(str(ctx.guild.id), 'not set')
                    emb.description = f"The custom prefix is {current_prefix}\n" + emb.description

                    choices = ['1', '2', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await ctx.send(f"Closing options menu")
                        await menu.delete()
                        return
                    elif choice == '1':
                        instr_msg = await ctx.send(f"Please input the custom prefix you wish to use on this server")
                        try:
                            reply_msg = await self.bot.wait_for('message',
                                                                timeout=20.0,
                                                                check=lambda x: x.author == ctx.author)
                            await instr_msg.delete()
                            await reply_msg.delete()
                            await ctx.invoke(self.set_prefix, reply_msg.content)
                        except asyncio.TimeoutError:
                            await ctx.send("Module timed out")
                            await instr_msg.delete()
                            return
                    elif choice == '2':
                        await ctx.invoke(self.prefix_reset)


#           main > logging module
            elif choice == '4':
                while True:
                    options = ['Deleted messages (`;deletes`)',  # 1
                               'Edited messages (`;edits`)',   # 2
                               'Joins and invite link tracking (`;joins`)',  # 3
                               'Leaves (`;leaves`)',  # 4
                               'Kicks (`;kicks`)',  # 5
                               'Bans (`;bans`)',  # 6
                               "Username/nickname changes (`;nicknames`)",  # 7
                               "Removed reactions (`;reactions`)",  # 8
                               ]
                    emb = self.make_options_embed(options)
                    emb.title = "Logging Module"

                    choices = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await ctx.send(f"Closing options menu")
                        await menu.delete()
                        return

                    # main > logging > deletes
                    elif choice == '1':
                        options = ["Enable/disable this module (`;deletes`)",
                                   "Set the channel for logging (`;deletes set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Deletes"
                        config = self.bot.db['deletes'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel(config['channel'])
                                emb.description = f"I am currently set to track deleted messages in " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = f"This module is currently disabled.  It tracks deleted messages " \
                                                  f"by users.\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await ctx.send(f"Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('delete_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('delete_logging deletes_set'))

                    # main > logging > edits
                    elif choice == '2':
                        options = ["Enable/disable this module (`;edits`)",
                                   "Set the channel for logging (`;edits set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Edits"
                        config = self.bot.db['edits'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel(config['channel'])
                                emb.description = f"I am currently set to track edited messages in " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = f"This module is currently disabled.  It tracks edited messages " \
                                                  f"by users.\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await ctx.send(f"Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('edit_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('edit_logging deletes_set'))

                    # main > logging > welcomes/joins
                    elif choice == '3':
                        options = ["Enable/disable this module (`;joins`)",
                                   "Set the channel for logging (`;joins set`)",
                                   "Enable/disable tracking of invite links people used to join (`;joins invites`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Joins/Invite Tracking"
                        config = self.bot.db['welcomes'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel(config['channel'])
                                emb.description = f"I am currently set to log member joins in " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = f"This module is currently disabled.  It tracks joins " \
                                                  f"by users.\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', '3', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await ctx.send(f"Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('welcome_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('welcome_logging welcomes_set'))
                            elif choice == '3':
                                await ctx.invoke(self.bot.get_command('welcome_logging invites_enable'))

                    # main > logging > leaves
                    elif choice == '4':
                        options = ["Enable/disable this module (`;leaves`)",
                                   "Set the channel for logging (`;leaves set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Leaves"
                        config = self.bot.db['leaves'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel(config['channel'])
                                emb.description = f"I am currently set to log when members leave the server in " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = f"This module is currently disabled.  It logs when a member leaves." \
                                                  f"\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await ctx.send(f"Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('leave_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('leave_logging leaves_set'))

                    # main > logging > kicks
                    elif choice == '5':
                        options = ["Enable/disable this module (`;kicks`)",
                                   "Set the channel for logging (`;kicks set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Kicks"
                        config = self.bot.db['kicks'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel(config['channel'])
                                emb.description = f"I am currently set to track kicked members " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = f"This module is currently disabled.  It tracks kicked members " \
                                                  f"\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await ctx.send(f"Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('kick_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('kick_logging kicks_set'))

                    # main > logging > bans
                    elif choice == '6':
                        options = ["Enable/disable this module (`;bans`)",
                                   "Set the channel for logging (`;bans set`)"]
                        emb = self.make_options_embed(options)
                        config = self.bot.db['bans'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel(config['channel'])
                                emb.description = f"I am currently set to track banned members " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = f"This module is currently disabled.  It tracks banned members " \
                                                  f"\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await ctx.send(f"Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('ban_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('ban_logging bans_set'))

                    # main > logging > nicknames
                    elif choice == '7':
                        options = ["Enable/disable this module (`;nicknames`)",
                                   "Set the channel for logging (`;nicknames set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Nicknames"
                        config = self.bot.db['nicknames'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel(config['channel'])
                                emb.description = f"I am currently set to track member nickname changes " \
                                                  f"{channel.mention}\n\nReply with any of the option numbers " \
                                                  f"or letters (b/x)"
                            else:
                                emb.description = f"This module is currently disabled.  It tracks member nickname " \
                                                  f"changes.\n\nReply with any of the option numbers or letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await ctx.send(f"Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('nickname_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('nickname_logging nicknames_set'))

                    # main > logging > reactions
                    elif choice == '8':
                        options = ["Enable/disable this module (`;reactions`)",
                                   "Set the channel for logging (`;reactions set`)"]
                        emb = self.make_options_embed(options)
                        emb.title = "Logging > Reactions"
                        config = self.bot.db['kicks'][str(ctx.guild.id)]

                        while True:
                            if config['enable']:
                                channel = ctx.guild.get_channel(config['channel'])
                                emb.description = f"I am currently set to track when users remove a reaction from a " \
                                                  f"message in {channel.mention}\n\nReply with any of the option " \
                                                  f"numbers or letters (b/x)"
                            else:
                                emb.description = f"This module is currently disabled.  It tracks when users remove " \
                                                  f"a reaction from a\n\nReply with any of the option numbers or " \
                                                  f"letters (b/x)"

                            choices = ['1', '2', 'b', 'x']
                            choice, menu = await self.wait_menu(ctx, menu, emb, choices)

                            if choice == 'time_out':
                                return
                            elif choice == 'b':
                                break
                            elif choice == 'x':
                                await ctx.send(f"Closing options menu")
                                await menu.delete()
                                return
                            elif choice == '1':
                                await ctx.invoke(self.bot.get_command('reaction_logging'))
                            elif choice == '2':
                                await ctx.invoke(self.bot.get_command('reaction_logging reactions_set'))


#           main > report module
            elif choice == '5':
                while True:
                    options = ['Set the mod role (these users can do `;report done`) (`set_mod_role`)',
                               "Set the mod channel (this is where anonymous reports go) (`;set_mod_channel`)",
                               "Set the report room (this is where users get taken for reports) (`;report setup`)",
                               "Check the report room waiting list (`;report check_waiting_list`)",
                               "Clear the report room waiting list (`;report clear_waiting_list`)",
                               "Reset the report room (in case of bugs) (`;report reset`)",
                               "Ping `@here` when someone makes an anonymous report (`;report anonymous_ping`)",
                               "Ping `@here` when someone makes enters the report room (`;report room_ping`)"]
                    emb = self.make_options_embed(options)
                    emb.title = "Setting up the report module"
                    try:
                        config = self.bot.db['report'][str(ctx.guild.id)]
                        channel = ctx.guild.get_channel(config['channel'])
                        emb.description = f"Current report channel is {channel.mention} ({channel.id})\n" \
                                          f"{emb.description}"
                    except KeyError:
                        emb.description = f"The report room is not setup yet.\n{emb.description}"

                    choices = ['1', '2', '3', '4', '5', '6', '7', '8', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await ctx.send(f"Closed options menu")
                        await menu.delete()
                        return

                    # set mod role
                    elif choice == '1':
                        instr_msg = await ctx.send("Please input the exact name of the role you wish to set as "
                                                   "the mod role")
                        reply_msg = await self.bot.wait_for('message',
                                                            timeout=20.0,
                                                            check=lambda x: x.author == ctx.author)
                        await ctx.invoke(self.set_mod_role, reply_msg.content)
                        await instr_msg.delete()
                        await reply_msg.delete()

                    # set mod channel
                    elif choice == '2':
                        print(ctx)
                        await ctx.invoke(self.set_mod_channel)

                    # Set the report room
                    elif choice == '3':
                        print(ctx)
                        await ctx.invoke(self.bot.get_command('report setup'))

                    # Check waiting list
                    elif choice == '4':
                        await ctx.invoke(self.bot.get_command('report check_waiting_list'))

                    # Clear waiting list
                    elif choice == '5':
                        await ctx.invoke(self.bot.get_command('report clear_waiting_list'))

                    # Reset report room
                    elif choice == '6':
                        await ctx.invoke(self.bot.get_command('report reset'))

                    # Ping `@here` for anonymous reports
                    elif choice == '7':
                        await ctx.invoke(self.bot.get_command('report anonymous_ping'))

                    # Ping `@here` for users in the report room
                    elif choice == '8':
                        await ctx.invoke(self.bot.get_command('report room_ping'))

#           main > questions module
            elif choice == '6':
                await ctx.invoke(self.bot.get_command('question setup'))


#           main > readd roles
            elif choice == '7':
                await ctx.invoke(self.bot.get_command('readd_roles'))


#           main > captcha
            elif choice == '8':
                while True:
                    options = ['Enable/disable the module (`;captcha toggle`)',
                               "Set here as the channel the new users will see (`;captcha set_channel`)",
                               "Set the role the new users will receive upon reacting "
                               "(`;captcha set_role <role name>`)",
                               "Post the message to this channel (`;captcha post_message`)"]
                    emb = self.make_options_embed(options)
                    emb.title = "Reaction-to-enter requirement for entering the server"
                    try:
                        config = self.bot.db['captcha'][str(ctx.guild.id)]
                        channel = ctx.guild.get_channel(config['channel'])
                        role = ctx.guild.get_role(config['role'])
                        word_dict = {True: 'enabled', False: 'disabled'}
                        emb.description = f"This module is currently {word_dict[config['enable']]}.\n" \
                                          f"Current entry channel is {channel.mention} ({channel.id})\n" \
                                          f"The role new users receive is {role.mention} ({role.id})\n" \
                                          f"{emb.description}"
                    except KeyError:
                        await ctx.invoke(self.toggle)
                        continue

                    choices = ['1', '2', '3', '4', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await ctx.send(f"Closed options menu")
                        await menu.delete()
                        return

                    # Enable/disable the module
                    elif choice == '1':
                        await ctx.invoke(self.toggle)

                    # Set here as the channel the new users will see
                    elif choice == '2':
                        await ctx.invoke(self.captcha_set_channel)

                    # Set the role the new users will receive upon reacting"
                    elif choice == '3':
                        await ctx.invoke(self.captcha_set_role)

                    # Post the message to this channel
                    elif choice == '4':
                        await ctx.invoke(self.captcha_post_message)


#           main > super voice watch
            elif choice == '9':
                while True:
                    options = ["Set here as the channel logs will be posted (`;svw`)",
                               'View list of people in super voice watch (`;svw list`)']
                    emb = self.make_options_embed(options)
                    emb.title = "Super voice watch"
                    try:
                        config = self.bot.db['super_voicewatch'][str(ctx.guild.id)]
                        channel = ctx.guild.get_channel(config['channel'])
                        emb.description = f"When a user on the super voice list joins a voice channel, this will be " \
                                          f"logged in {channel.mention}\n" \
                                          f"{emb.description}"
                    except KeyError:
                        await ctx.invoke(self.super_voicewatch)
                        continue

                    choices = ['1', '2', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await ctx.send(f"Closed options menu")
                        await menu.delete()
                        return

                    # Set here as the channel the new users will see (`;svw`)
                    elif choice == '1':
                        await ctx.invoke(self.super_voicewatch)

                    # View list of people in super voice watch (`;svw list`)
                    elif choice == '2':
                        await ctx.invoke(self.super_voicewatch_list)


#           main > super text watch
            elif choice == '10':
                while True:
                    options = ["Set here as the channel logs will be sent to (`;sw`)",
                               'View list of people in super voice watch (`;sw list`)']
                    emb = self.make_options_embed(options)
                    emb.title = "Super text watch"
                    try:
                        config = self.bot.db['super_watch'][str(ctx.guild.id)]
                        channel = ctx.guild.get_channel(config['channel'])
                        emb.description = f"When a user on the super text watch list sends any message, this will be " \
                                          f"logged in {channel.mention}.  The purpose for this is if a user joins " \
                                          f"who you suspect to be a troll, and you want to watch them very carefully." \
                                          f"\n{emb.description}"
                    except KeyError:
                        await ctx.invoke(self.super_watch)
                        continue

                    choices = ['1', '2', 'b', 'x']
                    choice, menu = await self.wait_menu(ctx, menu, emb, choices)
                    if choice == 'time_out':
                        return
                    if choice == 'b':
                        break
                    elif choice == 'x':
                        await ctx.send(f"Closed options menu")
                        await menu.delete()
                        return

                    # Set here as the channel the new users will see (`;svw`)
                    elif choice == '1':
                        await ctx.invoke(self.super_watch)

                    # View list of people in super voice watch (`;svw list`)
                    elif choice == '2':
                        await ctx.invoke(self.super_watch_list)

            else:
                await ctx.send("Something went wrong")
                return
            await hf.dump_json()

def setup(bot):
    bot.add_cog(Admin(bot))
