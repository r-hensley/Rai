import discord
from discord.ext import commands
import json
import urllib.request
from .utils import helper_functions as hf
import asyncio

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Admin(commands.Cog):
    """Stuff for admins"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return hf.admin_check(ctx)

    @commands.command()
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
            print([page[:30]])
            if page[0:6] == '!image':
                url = page.split(' ')[1].replace('\r', '').replace('\n', '')
                with open('image', 'wb') as f:
                    urllib.request.urlretrieve(url, "image_file.png")
                msg = await ctx.send(file=discord.File('image_file.png'))
            elif page[:30].replace('\r', '').replace('\n', '').startswith('!lang'):
                print('lang', [page])
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
                print('roles', [page])
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
                # await hf.dump_json()
            else:
                msg = await ctx.send(page)
            if '<@ &' in msg.content:
                await msg.edit(content=msg.content.replace('<@ &', '<@&'))

    @commands.group(invoke_without_command=True)
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

    @captcha.command()
    async def set_channel(self, ctx):
        guild = str(ctx.guild.id)
        if guild not in self.bot.db['captcha']:
            await self.toggle
        guild_config = self.bot.db['captcha'][guild]
        guild_config['channel'] = ctx.channel.id
        await ctx.send(f'Captcha channel set to {ctx.channel.name}')
        await hf.dump_json()

    @captcha.command()
    async def set_role(self, ctx, *, role_input: str = None):
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

    @captcha.command()
    async def post_message(self, ctx):
        guild = str(ctx.guild.id)
        if guild in self.bot.db['captcha']:
            guild_config = self.bot.db['captcha'][guild]
            if guild_config['enable']:
                msg = await ctx.send('Please react with the checkmark to enter the server')
                guild_config['message'] = msg.id
                await hf.dump_json()
                await msg.add_reaction('✅')

    @commands.command(aliases=['purge', 'prune'])
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
        if ctx.channel.permissions_for(ctx.author).manage_messages:
            try:
                await ctx.message.delete()
            except discord.errors.NotFound:
                pass
            if args:
                if args[0] == '0':
                    user = None
                if args[0] != '0':
                    try:
                        user = await commands.MemberConverter().convert(ctx, args[0])
                    except commands.errors.BadArgument:  # invalid user given
                        await ctx.send('User not found')
                        return
                try:
                    msg = await ctx.channel.get_message(args[1])
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
        else:
            await ctx.send(f"You lack permissions to use the `;clear` command.")

    @commands.command()
    async def auto_bans(self, ctx):
        config = hf.database_toggle(ctx, self.bot.db['auto_bans'])
        if config['enable']:
            if not ctx.me.guild_permissions.ban_members:
                await ctx.send("I lack the permission to ban users.  Please fix this before enabling the module")
                hf.database_toggle(ctx, self.bot.db['auto_bans'])
                return
            await ctx.send('Enabled the auto bans module.  I will now automatically ban all users who join with '
                           'a discord invite link username or who join and immediately send an amazingsexdating link')
        else:
            await ctx.send('Disabled the auto bans module.  I will no longer auto ban users who join with a '
                           'discord invite link username or who spam a link to amazingsexdating.')
        await hf.dump_json()

    @commands.command()
    async def set_mod_role(self, ctx, role_name):
        config = hf.database_toggle(ctx, self.bot.db['mod_role'])
        if 'enable' in config:
            del (config['enable'])
        mod_role = discord.utils.find(lambda role: role.name == role_name, ctx.guild.roles)
        config['id'] = mod_role.id
        await ctx.send(f"Set the mod role to {mod_role.name} ({mod_role.id})")
        await hf.dump_json()

    @commands.command(aliases=['setmodchannel'])
    async def set_mod_channel(self, ctx):
        self.bot.db['mod_channel'][str(ctx.guild.id)] = ctx.channel.id
        await ctx.send(f"Set the mod channel for this server as {ctx.channel.name}.")
        await hf.dump_json()

    @commands.command()
    async def readd_roles(self, ctx):
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

    @commands.group(invoke_without_command=True, aliases=['gb', 'gbl', 'blacklist'])
    async def global_blacklist(self, ctx):
        """A global blacklist for banning spammers, requires three votes from mods from three different servers"""
        config = hf.database_toggle(ctx, self.bot.db['global_blacklist']['enable'])
        if config['enable']:
            if not ctx.me.guild_permissions.ban_members:
                await ctx.send('I lack the permission to ban members.  Please fix that before enabling this module')
                hf.database_toggle(ctx, self.bot.db['global_blacklist'])
                return
            await ctx.send("Enabled the global blacklist on this server.  Anyone voted into the blacklist by three "
                           "mods and joining your server will be automatically banned.  "
                           "Type `;global_blacklist residency` to claim your residency on a server.")
        else:
            await ctx.send("Disabled the global blacklist.  Anyone on the blacklist will be able to join  your server.")
        await hf.dump_json()

    @global_blacklist.command()
    async def residency(self, ctx):
        """Claims your residency on a server"""
        config = self.bot.db['global_blacklist']['residency']

        if str(ctx.author.id) in config:
            server = self.bot.get_guild(config[str(ctx.author.id)])
            await ctx.send(f"You've already claimed residency on {server.name}.  You can not change this without "
                           f"talking to Ryan.")
            return

        await ctx.send("For the purpose of maintaining fairness in a ban, you're about to claim your mod residency to "
                       f"`{ctx.guild.name}`.  This can not be changed without talking to Ryan.  "
                       f"Do you wish to continue?\n\nType `yes` or `no` (case insensitive).")
        msg = await self.bot.wait_for('message',
                                      timeout=25.0,
                                      check=lambda m: m.author == ctx.author and m.channel == ctx.channel)

        if msg.content.casefold() == 'yes':  # register
            config[str(ctx.author.id)] = ctx.guild.id
            await ctx.send(f"Registered your residency to `{ctx.guild.name}`.  Type `;global_blacklist add <ID>` to "
                           f"vote on a user for the blacklist")

        elif msg.content.casefold() == 'no':  # cancel
            await ctx.send("Understood.  Exiting module.")

        else:  # invalid response
            await ctx.send("Invalid response")
        await hf.dump_json()

    @global_blacklist.command(aliases=['vote'])
    async def add(self, ctx, user, *, reason: str = None):
        channel = self.bot.get_channel(533863928263082014)
        config = self.bot.db['global_blacklist']
        target_user = self.bot.get_user(int(user))
        print(user)
        print(reason)

        async def post_vote_notification(num_of_votes):
            await ctx.message.add_reaction('✅')
            if target_user:
                message = f"📥 There are now **{num_of_votes}** vote(s) for `{target_user.name} " \
                          f"({user}`). (voted for by {ctx.author.name})"
            else:
                message = f"📥 There are now **{num_of_votes}** vote(s) for `{user}`." \
                          f" (voted for by {ctx.author.name})."
            if reason:
                message += "\nExtra info: {reason}"
            await channel.send(message)

        async def post_ban_notification():
            await ctx.message.add_reaction('✅')
            if target_user:
                message = f"`❌ {target_user.name} ({user}`) has received their final vote from {ctx.author.name}" \
                          f" and been added to the blacklist."
            else:
                message = f"`❌ `{user}` has received their final vote from {ctx.author.name}" \
                          f" and been added to the blacklist."
            await channel.send(message)

        if user in config['votes']:  # already been voted on before
            votes_list = config['votes'][user]  # a list of guild ids that have voted for adding to the blacklist
        else:
            if user not in config['blacklist']:
                votes_list = config['votes'][user] = []  # no votes yet, so an empty list
            else:
                await ctx.send("This user is already on the blacklist")
                return

        try:  # the guild ID that the person trying to add a vote belongs to
            residency = self.bot.db['global_blacklist']['residency'][str(ctx.author.id)]  # a guild id
        except KeyError:
            await ctx.send("Please claim residency on a server first with `;global_blacklist residency`")
            return

        if residency in votes_list:  # ctx.author's server already voted
            await ctx.send(f"Someone from your server `({self.bot.get_guild(residency).name})` has already voted")
        else:  # can take a vote
            votes_list.append(residency)
            num_of_votes = len(config['votes'][user])
            if num_of_votes == 3:
                config['blacklist'].append(int(user))  # adds the user id to the blacklist
                del (config['votes'][user])
                await post_ban_notification()
            else:
                await post_vote_notification(num_of_votes)

        await hf.dump_json()

    @commands.group(invoke_without_command=True, aliases=['svw', 'supervoicewatch'])
    async def super_voicewatch(self, ctx):
        if str(ctx.guild.id) not in self.bot.db['mod_channel']:
            await ctx.send("Before using this, you have to set your mod channel using `;set_mod_channel` in the "
                           "channel you want to designate.")
            return
        await ctx.send("Puts a message in the mod channel every time someone on the super watchlist joins a voice "
                       "channel.  Use `;super_voicewatch add USER` or `'super_voicewatch remove USER` to "
                       "manipulate the list.  Type `;super_voicewatch list` to see a full list.  Alias: `;svw`")

    @super_voicewatch.command()
    async def add(self, ctx, member: discord.Member):
        if str(ctx.guild.id) not in self.bot.db['mod_channel']:
            await ctx.send("Before using this, you have to set your mod channel using `;set_mod_channel` in the "
                           "channel you want to designate.")
            return
        try:
            config = self.bot.db['super_voicewatch'][str(ctx.guild.id)]
        except KeyError:
            config = self.bot.db['super_voicewatch'][str(ctx.guild.id)] = []
        config.append(member.id)
        await ctx.send(f"Added `{member.name} ({member.id})` to the super voice watchlist.")
        await hf.dump_json()

    @super_voicewatch.command()
    async def remove(self, ctx, member: discord.Member):
        try:
            config = self.bot.db['super_voicewatch'][str(ctx.guild.id)]
        except KeyError:
            config = self.bot.db['super_voicewatch'][str(ctx.guild.id)] = []
        try:
            config.remove(member.id)
        except ValueError:
            await ctx.send("That user was not in the watchlist.")
        await ctx.send(f"Removed `{member.name} ({member.id})` from the super voice watchlist.")
        await hf.dump_json()

    @super_voicewatch.command()
    async def list(self, ctx):
        string = ''
        try:
            config = self.bot.db['super_voicewatch'][str(ctx.guild.id)]
        except KeyError:
            await ctx.send("Voice watchlist not set-up yet on this server.  Run `;super_voicewatch`")
            return
        if not config:
            await ctx.send("The voice watchlist is empty")
            return
        for ID in config:
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

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        try:
            config = self.bot.db['super_voicewatch'][str(member.guild.id)]
        except KeyError:
            return
        if member.id in config and not before.channel and after.channel:
            channel = self.bot.get_channel(self.bot.db['mod_channel'][str(member.guild.id)])
            await channel.send(f"{member.mention} is on the voice superwatch list and has joined a voice channel "
                               f"({after.channel.name})")

    @commands.group(invoke_without_command=True, aliases=['superwatch', 'sw'])
    async def super_watch(self, ctx):
        try:
            config = self.bot.db['super_watch'][str(ctx.guild.id)]
            config['channel'] = ctx.channel.id
        except KeyError:
            self.bot.db['super_watch'][str(ctx.guild.id)] = {"users": [], "channel": ctx.channel.id}
        await ctx.send(f"Messages sent from users on the super_watch list will be sent to {ctx.channel.name} "
                       f"({ctx.channel.id}).  \n\n"
                       f"Type `;super_watch add <ID>` to add someone, `;super_watch remove "
                       f"<ID>` to remove them from the list later.  You can change the channel that super_watch "
                       f"sends posts to in the future by typing `;super_watch` again.  \n\n"
                       f"Aliases for this command are: `;superwatch`, `;sw`.")
        await hf.dump_json()

    @super_watch.command()
    async def add(self, ctx, target):
        try:
            config = self.bot.db['super_watch'][str(ctx.guild.id)]['users']
        except KeyError:
            await ctx.send("Super watch is not yet setup for this server.  Run `;super_watch` to set it up.")
        try:
            target = await commands.MemberConverter().convert(ctx, target)
        except commands.errors.BadArgument:  # invalid user given
            await ctx.send("User not found")
            return
        if target.id not in config:
            config.append(target.id)
            await ctx.send(f"Added {target.name} to super_watch list")
            await hf.dump_json()
        else:
            await ctx.send(f"{target.name} is already on the super_watch list")

    @super_watch.command()
    async def remove(self, ctx, target):
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

    @super_watch.command()
    async def list(self, ctx):
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

    @set_prefix.command()
    async def reset(self, ctx):
        try:
            prefix = self.bot.db['prefix']
            del prefix[str(ctx.guild.id)]
            await ctx.send("The command prefix for this guild has successfully been reset to `;`")
            await hf.dump_json()
        except KeyError:
            await ctx.send("This guild already uses the default command prefix.")


def setup(bot):
    bot.add_cog(Admin(bot))
