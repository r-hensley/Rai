import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import json
from imgurpython import ImgurClient
import functools
from Levenshtein import distance as LDist
import re
from .utils import helper_functions as hf

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

with open(f'{dir_path}/gitignore/imgur_token.txt', 'r') as file:
    file.readline()  # comment line in text file
    client_id = file.readline()[:-1]
    client_secret = file.readline()[:-1]
    access_token = file.readline()[:-1]
    refresh_token = file.readline()

imgur_client = ImgurClient(client_id, client_secret, access_token, refresh_token)


class Logger:
    """Logs stuff"""

    def __init__(self, bot):
        self.bot = bot

    async def __local_check(self, ctx):
        return ctx.channel.permissions_for(ctx.author).administrator

    def dump_json(self):
        with open(f'{dir_path}/database2.json', 'w') as write_file:
            json.dump(self.bot.db, write_file, indent=4)
            write_file.flush()
            os.fsync(write_file.fileno())
        os.remove(f'{dir_path}/database.json')
        os.rename(f'{dir_path}/database2.json', f'{dir_path}/database.json')

    async def module_logging(self, ctx, module):
        guild = str(ctx.guild.id)
        if guild in module:
            guild_config: dict = module[guild]
            if guild_config['enable']:  # if the guild has enabled logging
                guild_config['enable'] = False
                result = 1
            else:
                if guild_config['channel']:
                    guild_config['enable'] = True
                    result = 2
                else:
                    result = 3
        else:  # first time register for a new guild
            module[guild] = {"enable": False, "channel": ""}
            result = 4
        await hf.dump_json()
        return result

    async def module_set(self, ctx, module):
        guild = str(ctx.guild.id)
        if guild in module:  # server already registered
            guild_config: dict = module[guild]
            guild_config['channel'] = ctx.channel.id
            result = 1
        else:  # new server
            module[guild] = {"enable": True, "channel": ctx.channel.id}
            result = 2
        await hf.dump_json()
        return result

    @commands.group(invoke_without_command=True, aliases=['edit', 'edits'])
    async def edit_logging(self, ctx):
        """Logs edited messages, aliases: 'edit', 'edits'"""
        result = self.module_logging(ctx, self.bot.db['edits'])
        if result == 1:
            await ctx.send('Disabled edit logging for this server')
        elif result == 2:
            await ctx.send('Enabled edit logging for this server')
        elif result == 3:
            await ctx.send('You have not yet set a channel for edit logging yet. Run `;edit_logging set`')
        elif result == 4:
            self.bot.db['edits'][str(ctx.guild.id)]['distance_limit'] = 3
            await hf.dump_json()
            await ctx.send('Before doing this, set a channel for logging with `;edit_logging set`.  '
                           'Then, enable/disable logging by typing `;edit_logging`.')

    @edit_logging.command(aliases=['set'])
    async def edits_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['edits'])
        if result == 1:
            await ctx.send(f'Set the edit logging channel as {ctx.channel.name}')
        elif result == 2:
            self.bot.db['edits'][str(ctx.guild.id)]['distance_limit'] = 3
            await hf.dump_json()
            await ctx.send(f'Enabled edit logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;edit_logging`.')

    @edit_logging.command(aliases=['set_distance'])
    async def distance_set(self, ctx, distance_limit: int):
        guild = str(ctx.guild.id)
        guild_config: dict = self.bot.db['edits'][guild]
        guild_config['distance_limit'] = distance_limit
        await ctx.send(f'Successfully set Levenshtein Distance limit to {distance_limit}.')
        await hf.dump_json()

    def make_edit_embed(self, before, after, levenshtein_distance):
        author = before.author
        time_dif = round((after.edited_at - before.created_at).total_seconds(), 1)
        emb = discord.Embed(
            description=f'**{author.name}#{author.discriminator}** ({author.id})'
                        f'\n**Message edited after {time_dif} seconds.** [(LD={levenshtein_distance})]'
                        f'(https://en.wikipedia.org/wiki/Levenshtein_distance)',
            colour=0xFF9933,
            timestamp=datetime.utcnow()
        )

        if len(before.content) < 1025:
            emb.add_field(name='**Before:**', value=before.content)
        else:
            emb.add_field(name='**Before:** (Part 1):', value=before.content[:1000])
            emb.add_field(name='**Before:** (Part 2):', value=before.content[1000:])

        if len(after.content) < 1025:
            emb.add_field(name='**After:**', value=after.content)
        else:
            emb.add_field(name='**After:** (Part 1)', value=after.content[:1000])
            emb.add_field(name='**After:** (Part 2)', value=after.content[1000:])

        emb.set_footer(text=f'{before.channel.name}', icon_url=before.author.avatar_url_as(static_format="png"))

        return emb

    async def on_message_edit(self, before, after):
        if isinstance(before.channel, discord.DMChannel):
            return
        guild = str(before.guild.id)
        if not before.author.bot:
            if guild in self.bot.db['edits']:
                guild_config: dict = self.bot.db['edits'][guild]
                if guild_config['enable']:
                    try:
                        distance_limit = guild_config["distance_limit"]
                    except KeyError:
                        channel = self.bot.get_channel(guild_config["channel"])
                        await channel.send('Please set a Levenshtein Distance with `;edit set_distance 3`')
                        return
                    levenshtein_distance = LDist(before.content, after.content)
                    if levenshtein_distance > distance_limit:
                        channel = self.bot.get_channel(guild_config["channel"])
                        await channel.send(embed=self.make_edit_embed(before, after, levenshtein_distance))
        await hf.uhc_check(after)

    @commands.group(invoke_without_command=True, aliases=['delete', 'deletes'])
    async def delete_logging(self, ctx):
        """Logs deleted messages, aliases: 'delete', 'deletes'"""
        result = self.module_logging(ctx, self.bot.db['deletes'])
        if result == 1:
            await ctx.send('Disabled delete logging for this server')
        elif result == 2:
            await ctx.send('Enabled delete logging for this server')
        elif result == 3:
            await ctx.send('You have not yet set a channel for delete logging yet. Run `;delete_logging set`')
        elif result == 4:
            await ctx.send('Before doing this, set a channel for logging with `;delete_logging set`.  '
                           'Then, enable/disable logging by typing `;delete_logging`.')

    @delete_logging.command(aliases=['set'])
    async def deletes_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['deletes'])
        if result == 1:
            await ctx.send(f'Set the delete logging channel as {ctx.channel.name}')
        elif result == 2:
            await ctx.send(f'Enabled delete logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;delete_logging`.')

    async def make_delete_embed(self, message):
        author = message.author
        time_dif = round((datetime.utcnow() - message.created_at).total_seconds(), 1)
        emb = discord.Embed(
            description=f'**{author.name}#{author.discriminator}** ({author.id})'
                        f'\n**Message deleted after {time_dif} seconds.**',
            colour=0xDB3C3C,
            timestamp=datetime.utcnow()
        )

        if message.content:
            if len(message.content) < 1025:
                emb.add_field(name='**Message:**', value=message.content)
            else:
                emb.add_field(name='**Message:** (Part 1):', value=message.content[:1000])
                emb.add_field(name='**Message:** (Part 2):', value=message.content[1000:])

        if message.attachments:
            list_of_attachments = []
            attachment_names = []
            failed = True  # will be True unless the code manages to successfully upload an image to imgur
            file = False  # marks if someone uploaded a non-picture file
            for attachment in message.attachments:

                if attachment.filename.split('.')[-1].casefold() not in ['jpg', 'jpeg', 'png', 'gif',
                                                                         'apng', 'tiff', 'mov', 'mp4']:
                    attachment_names.append(attachment.filename)
                    file = True
                    continue
                # asyncio black magic from here:
                # https://github.com/ScreenZoneProjects/ScreenBot-Discord/blob/master/cogs/image.py
                task = functools.partial(imgur_client.upload_from_url, attachment.proxy_url, anon=True)
                task = self.bot.loop.run_in_executor(None, task)
                try:
                    image = await asyncio.wait_for(task, timeout=10)
                    list_of_attachments.append(image['link'])
                    failed = None
                except asyncio.TimeoutError:
                    list_of_attachments.append(attachment.proxy_url)

            if list_of_attachments:
                emb.add_field(name='**Attachments:**', value='\n'.join(list_of_attachments))
                if failed:
                    emb.add_field(name='**Warning:**',
                                  value='Failed to reupload to imgur.  The above link may quickly 404')
                emb.set_thumbnail(url=list_of_attachments[0])
            if file:
                emb.add_field(name='**File Attachments:**', value='\n'.join(attachment_names))

        emb.set_footer(text=f'#{message.channel.name}', icon_url=message.author.avatar_url_as(static_format="png"))

        return emb

    async def on_message_delete(self, message):
        guild = str(message.guild.id)
        if not message.author.bot:
            if guild in self.bot.db['deletes']:
                guild_config: dict = self.bot.db['deletes'][guild]
                if guild_config['enable']:
                    channel = self.bot.get_channel(guild_config["channel"])
                    try:
                        await channel.send(embed=await self.make_delete_embed(message))
                    except discord.errors.HTTPException as e:
                        print('>>Error in on_message_delete, ')
                        print(e)
                        print(message + '<<')

    @commands.group(invoke_without_command=True, aliases=['welcome', 'welcomes', 'join', 'joins'])
    async def welcome_logging(self, ctx):
        """Logs server joins + tracks invite links, aliases: 'welcome', 'welcomes', 'join', 'joins'"""
        result = self.module_logging(ctx, self.bot.db['welcomes'])
        server_config = self.bot.db['welcomes'][str(ctx.guild.id)]
        if result == 1:
            await ctx.send('Disabled welcome logging for this server')
        elif result == 2:
            try:
                server_config['invites'] = {invite.code: invite.uses for invite in await ctx.guild.invites()}
                server_config['invites_enable'] = True
                await hf.dump_json()
                await ctx.send('Enabled welcome logging + invite tracking for this server (type `;invites` to disable'
                               ' invite tracking)')
            except discord.errors.Forbidden:
                await ctx.send("I've enabled welcome message, but I lack permissions to get invite codes.  "
                               "If you want invite tracking too, give me `Manage Server` and then type "
                               "`;invites` to enable invite tracking for future joins.")
                server_config['invites_enable'] = False
                await hf.dump_json()

        elif result == 3:
            await ctx.send('You have not yet set a channel for welcome logging yet. Run `;welcome_logging set`')
        elif result == 4:
            await ctx.send('Before doing this, set a channel for logging with `;welcome_logging set`.  '
                           'Then, enable/disable logging by typing `;welcome_logging`.')

    @welcome_logging.command(aliases=['set'])
    async def welcomes_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['welcomes'])
        if result == 1:
            await ctx.send(f'Set the welcome logging channel as {ctx.channel.name}')
        elif result == 2:
            server_config['invites'] = {invite.code: invite.uses for invite in await ctx.guild.invites()}
            server_config['invites_enable'] = True
            await hf.dump_json()
            await ctx.send(f'Enabled welcome logging + invite tracking and set the channel to `{ctx.channel.name}`.  '
                           f'Enable/disable logging by typing `;welcome_logging`.')

    @welcome_logging.command(aliases=['invites', 'invite'])
    async def invites_enable(self, ctx):
        guild = str(ctx.guild.id)
        if guild in self.bot.db['welcomes']:
            server_config = self.bot.db['welcomes'][guild]
            try:
                server_config['invites_enable'] = not server_config['invites_enable']
                await ctx.send(f"Set invite tracking to `{server_config['invites_enable']}`")
            except KeyError:
                server_config['invites_enable'] = True
                await ctx.send('Enabled invites tracking')
            await hf.dump_json()

    async def make_welcome_embed(self, member, used_invite):
        minutes_ago_created = int(((datetime.utcnow() - member.created_at).total_seconds()) // 60)
        if minutes_ago_created < 60:
            time_str = f'\n\nAccount created **{minutes_ago_created}** minutes ago'
        else:
            time_str = ''

        emb = discord.Embed(
            description=f":inbox_tray: **{member.name}#{member.discriminator}** has `joined`. "
                        f"({member.id}){time_str}",
            colour=0x7BA600,
            timestamp=datetime.utcnow()
        )

        if used_invite:
            invite_string = f"Used {used_invite.inviter.name}'s link {used_invite.code}"
            footer_text = f'User Join ({member.guild.member_count}) {invite_string}'
        else:
            footer_text = f'User Join ({member.guild.member_count})'

        emb.set_footer(text=footer_text, icon_url=member.avatar_url_as(static_format="png"))

        return emb

    @commands.group(invoke_without_command=True)
    async def welcome_message(self, ctx):
        """enable welcome messages"""
        guild = str(ctx.guild.id)
        if guild in self.bot.db['welcome_message']:
            config = self.bot.db['welcome_message'][guild]
            try:
                config['enable'] = not config['enable']
                x = config['enable']
                await ctx.send(f'Set welcome message posting to {x}')
            except KeyError:
                config['enable'] = True
                x = config['enable']
                await ctx.send(f'Set welcome message posting to {x}')
        else:
            self.bot.db['welcome_message'][guild] = {}
            config = self.bot.db['welcome_message'][guild]
            config['enable'] = True
            x = config['enable']
            await ctx.send(f'Set welcome message posting to {x}')
        await hf.dump_json()

    @welcome_message.command()
    async def set_message(self, ctx, *, message: str = None):
        if not message:
            await ctx.send('Please put your welcome message after the command invocation.  For example: \n'
                           '```;welcome_message set_message Welcome to the server `$NAME$`! Please read the rules```\n'
                           "Valid flags to use are: \n$NAME$ = The user's name in text\n`$USERMENTION$` = Mentions "
                           "the user\n`$SERVER$` = The name of the server")
        else:
            config = self.bot.db['welcome_message'][str(ctx.guild.id)]
            config['message'] = message
            await ctx.send(f"Set welcome message to ```{message}```")
            await hf.dump_json()

    @welcome_message.command()
    async def set_channel(self, ctx):
        config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        config['channel'] = ctx.channel.id
        await ctx.send(f"Set welcome message channel to {ctx.channel.mention}")
        await hf.dump_json()

    @welcome_message.command()
    async def show_message(self, ctx):
        config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        await ctx.send("```" + config['message'] + "```")

    async def on_member_join(self, member):
        """Join logging"""
        guild = str(member.guild.id)
        if guild in self.bot.db['welcomes']:
            if self.bot.db['welcomes'][guild]['enable']:
                server_config = self.bot.db['welcomes'][guild]
                channel = self.bot.get_channel(server_config['channel'])
                try:
                    invites_enable = server_config['invites_enable']
                    await hf.dump_json()
                except KeyError:
                    server_config['invites_enable'] = False
                    invites_enable = server_config['invites_enable']
                    await hf.dump_json()
                    await channel.send("I've added a toggle for invite tracking since it requires `Manage Server` "
                                       "permission.  If you wish Rai to track used invite links for joins, please type "
                                       "`welcomes invites`.")
                used_invite = None
                if invites_enable:
                    try:
                        try:
                            old_invites = self.bot.db['welcomes'][str(member.guild.id)]['invites']
                        except KeyError:
                            self.bot.db['welcomes'][str(member.guild.id)]['invites'] = {}
                        if not self.bot.db['welcomes'][str(member.guild.id)]['invites']:
                            invites_list = await member.guild.invites()
                            old_invites = {invite.code: invite.uses for invite in invites_list}
                            self.bot.db['welcomes'][str(member.guild.id)]['invites'] = old_invites
                            await hf.dump_json()
                        invites = await member.guild.invites()
                        new_invites = {invite.code: invite.uses for invite in invites}
                        for invite in new_invites:
                            try:
                                if new_invites[invite] > old_invites[invite]:
                                    used_invite = next(i for i in invites if str(i.code) == invite)
                                    self.bot.db['welcomes'][str(member.guild.id)]['invites'] = new_invites
                                    break
                            except KeyError:  # new invite
                                if new_invites[invite] == 1:
                                    used_invite = next(i for i in invites if str(i.code) == invite)
                                    self.bot.db['welcomes'][str(member.guild.id)]['invites'] = new_invites
                                    break
                        if not used_invite:
                            print('>>Was unable to find invite<<')
                    except discord.errors.Forbidden:
                        server_config['invites_enable'] = False
                        await channel.send(
                            "Rai needs the `Manage Server` permission to track invites. For now, I've disabled "
                            "invite link tracking.  If you wish to reenable it, type `;welcomes invites`")
                    await hf.dump_json()
                try:
                    x = await self.make_welcome_embed(member, used_invite)
                    await channel.send(embed=x)
                except discord.errors.Forbidden:
                    await channel.send('Rai needs permission to post embeds to track joins')

        """ban invite link names"""
        try:
            if self.bot.db['auto_bans'][guild]['enable']:
                pat = re.compile(r'.*(discord|discordapp).(gg|com\/invite)\/[A-Z0-9]{1,7}.*', re.I)
                if re.match(pat, member.name):
                    guild = str(member.guild.id)
                    await member.ban(reason="Name was a discord invite link")
                    message = f"Banned user `{member.name}` from {member.guild.name} for being an invite link name\n" \
                              f"({member.id} {member.mention})"
                    await self.bot.get_channel(329576845949534208).send(message)
                    self.bot.db['global_blacklist']['blacklist'].append(member.id)
                    channel = self.bot.get_channel(533863928263082014)
                    await channel.send(
                        f"❌ Automatically added `{member.name} ({member.id}`) to the blacklist for "
                        f"being an invite-link name")
                    return  # stops execution of the rest of the code if was invite link name
        except KeyError:
            pass
        await hf.dump_json()

        """blacklist bans"""
        config = self.bot.db['global_blacklist']
        if member.id in config['blacklist']:
            try:
                if config['enable'][str(member.guild.id)]['enable']:
                    await member.ban(reason="On the global blacklist")
                    return
            except KeyError:
                pass

        """welcome message"""
        try:
            guild = str(member.guild.id)
            if self.bot.db['welcome_message'][guild]['enable']:
                config = self.bot.db['welcome_message'][guild]
                channel = self.bot.get_channel(config['channel'])
                message = config['message']
                message = message. \
                    replace('$NAME$', member.name). \
                    replace('$USERMENTION$', member.mention). \
                    replace('$SERVER$', member.guild.name)
                welcome_message = await channel.send(message)
        except KeyError:
            pass

        """Japanese Server Welcome"""
        if guild == '189571157446492161':
            # check if they joined from a Japanese site or other
            # the following links are specifically the ones we've used to advertise on japanese sites
            japanese_links = ['6DXjBs5', 'WcBF7XZ', 'jzfhS2', 'w6muGjF', 'TxdPsSm', 'MF9XF89', 'RJrcSb3']
            post_message = True
            try:
                config = self.bot.db['readd_roles'][str(member.guild.id)]
            except KeyError:
                pass
            else:
                if config['enable'] and str(member.id) in config['users']:
                    post_message = False
                    roles_dict = {role.id: role for role in member.guild.roles}
                    list_of_roles = [roles_dict[role] for role in config['users'][str(member.id)][1]]
                    del (list_of_roles[0])
                    new_user_role = member.guild.get_role(249695630606336000)
                    if new_user_role in list_of_roles:
                        list_of_roles.remove(new_user_role)
                    if list_of_roles:
                        await member.add_roles(*list_of_roles)
                        await member.remove_roles(new_user_role)
                        await self.bot.jpJHO.send(
                            f"Welcome back {member.name}! I've given your previous roles back to you")
                        del config['users'][str(member.id)]
                        await hf.dump_json()
            finally:
                if post_message:
                    if str(used_invite.code) in japanese_links:
                        await self.bot.jpJHO.send(f'{member.name}さん、サーバーへようこそ！')  # a japanese person possibly
                    elif member.id != 414873201349361664:
                        await self.bot.jpJHO.send(f'Welcome {member.name}!')  # probably not a japanese person
                if member.id == 414873201349361664:
                    async for message in self.bot.jpJHO.history(limit=10):
                        if message.author.id == 159985870458322944:
                            await message.delete()
                            break
                    m = await self.bot.wait_for('message', timeout=5.0,
                                                check=lambda m: m.author.id == 299335689558949888)
                    await m.delete()
        else:
            try:
                config = self.bot.db['readd_roles'][str(member.guild.id)]
            except KeyError:
                pass
            else:
                if config['enable'] and str(member.id) in config['users']:
                    roles_dict = {role.id: role for role in member.guild.roles}
                    list_of_roles = [roles_dict[role] for role in config['users'][str(member.id)][1]]
                    del (list_of_roles[0])
                    await member.add_roles(*list_of_roles)
                    await member.send(f"Welcome back {member.name}! I've given your previous roles back to you")
                    del config['users'][str(member.id)]
                    await hf.dump_json()

        """Spanish Server welcome"""
        if member.guild == self.bot.spanServ:
            nadeko_obj = self.bot.spanServ.get_member(116275390695079945)
            if str(nadeko_obj.status) == 'offline':
                await self.bot.get_channel(243838819743432704).send(
                    'Welcome to the server.  Nadeko is currently down, '
                    'so please state your roles and someone in welcoming party will come to'
                    ' assign your role as soon as possible.  If no one comes, please tag the mods with `@Mods`.  '
                    'Thanks! '
                    '(<@&470364944479813635>)'
                )

    @commands.group(invoke_without_command=True, aliases=['leave', 'leaves'])
    async def leave_logging(self, ctx):
        """Logs leaves + shows list of roles at time of leave, aliases: 'leave', 'leaves'"""
        result = self.module_logging(ctx, self.bot.db['leaves'])
        if result == 1:
            await ctx.send('Disabled leave logging for this server')
        elif result == 2:
            await ctx.send('Enabled leave logging for this server')
        elif result == 3:
            await ctx.send('You have not yet set a channel for leave logging yet. Run `;leave_logging set`')
        elif result == 4:
            await ctx.send('Before doing this, set a channel for logging with `;leave_logging set`.  '
                           'Then, enable/disable logging by typing `;leave_logging`.')

    @leave_logging.command(aliases=['set'])
    async def leaves_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['leaves'])
        if result == 1:
            await ctx.send(f'Set the leave logging channel as `{ctx.channel.name}`')
        elif result == 2:
            await ctx.send(f'Enabled leave logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;leave_logging`.')

    def make_leave_embed(self, member):
        emb = discord.Embed(
            description=''
                        f":outbox_tray: **{member.name}#{member.discriminator}** has `left` the server. "
                        f"({member.id})",
            colour=0xD12B2B,
            timestamp=datetime.utcnow()
        )

        if len(member.roles) > 1:  # all members have the @everyone role
            emb.add_field(name='Roles:', value=', '.join(reversed([role.name for role in member.roles[1:]])))

        emb.set_footer(
            text=f'User Leave ({member.guild.member_count})',
            icon_url=member.avatar_url_as(static_format="png")
        )
        return emb

    async def on_member_remove(self, member):
        guild = str(member.guild.id)
        if guild in self.bot.db['leaves']:
            if self.bot.db['leaves'][guild]['enable']:
                server_config = self.bot.db['leaves'][guild]
                channel = self.bot.get_channel(server_config['channel'])
                try:
                    await channel.send(embed=self.make_leave_embed(member))
                except AttributeError as e:
                    await self.bot.testChan.send("Error on on_member_remove"
                                                 f"{member.guild}, {e}")

        try:
            config = self.bot.db['readd_roles'][str(member.guild.id)]
        except KeyError:
            pass
        else:
            if config['enable']:
                role_list = [role.id for role in member.roles]
                if 249695630606336000 in role_list:  # new user
                    role_list.remove(249695630606336000)
                if role_list:  # if the role list isn't empty (i.e., no roles)
                    config['users'][str(member.id)] = [datetime.utcnow().strftime("%Y%m%d"), role_list]
                    await hf.dump_json()

        if guild in self.bot.db['kicks']:
            guild_config: dict = self.bot.db['kicks'][guild]
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                emb = await self.make_kick_embed(member)
                if emb:
                    await channel.send(embed=emb)

    @commands.group(invoke_without_command=True, aliases=['nickname', 'nicknames'])
    async def nickname_logging(self, ctx):
        """Logs nicknames changes, aliases: 'nickname', 'nicknames'"""
        result = self.module_logging(ctx, self.bot.db['nicknames'])
        if result == 1:
            await ctx.send('Disabled nickname logging for this server')
        elif result == 2:
            await ctx.send('Enabled nickname logging for this server')
        elif result == 3:
            await ctx.send('You have not yet set a channel for nickname logging yet. Run `;nickname_logging set`')
        elif result == 4:
            await ctx.send('Before doing this, set a channel for logging with `;nickname_logging set`.  '
                           'Then, enable/disable logging by typing `;nickname_logging`.')

    @nickname_logging.command(aliases=['set'])
    async def nicknames_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['nicknames'])
        if result == 1:
            await ctx.send(f'Set the nickname logging channel as `{ctx.channel.name}`')
        elif result == 2:
            await ctx.send(f'Enabled nickname logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;nickname_logging`.')

    def make_nickname_embed(self, before, after):
        emb = discord.Embed(
            description=''
                        f"**{before.nick}**'s nickname was changed to **{after.nick}**",
            colour=0xFF9933,
            timestamp=datetime.utcnow()
        )
        emb.set_footer(
            text=f'{before.name}#{before.discriminator} ({before.id})',
            icon_url=before.avatar_url_as(static_format="png")
        )
        return emb

    async def on_member_update(self, before, after):
        guild = str(before.guild.id)
        if guild in self.bot.db['nicknames']:
            if self.bot.db['nicknames'][guild]['enable']:
                server_config = self.bot.db['nicknames'][guild]
                channel = self.bot.get_channel(server_config['channel'])
                if not channel:
                    return
                if before.name != after.name:  # username change
                    embed = self.make_nickname_embed(before, after)
                    embed.description = f"**{before.name}#{before.discriminator}**'s username was set to **{after.name}#{after.discriminator}**"
                    await channel.send(embed=embed)
                if before.nick != after.nick:  # nickname change
                    if before.nick and not after.nick:  # nickname removed
                        embed = self.make_nickname_embed(before, after)
                        embed.description = f"**{before.nick}**'s nickname was **removed**"
                    elif not before.nick and after.nick:  # nickname added
                        embed = self.make_nickname_embed(before, after)
                        embed.description = \
                            f"**{before.name}#{before.discriminator}**'s nickname was set to **{after.nick}**"
                    elif before.nick and after.nick:
                        embed = self.make_nickname_embed(before, after)
                    else:
                        return
                    await channel.send(embed=embed)

        """Nadeko updates"""
        if before == self.bot.spanServ.get_member(116275390695079945) and before.guild == self.bot.spanServ:
            if str(before.status) == 'online' and str(after.status) == 'offline':
                def check(beforecheck, aftercheck):
                    return after.id == beforecheck.id and \
                           str(beforecheck.status) == 'offline' and \
                           str(aftercheck.status) == 'online'

                try:
                    await self.bot.wait_for('member_update', check=check, timeout=1200)
                    self.bot.waited = False
                except asyncio.TimeoutError:
                    self.bot.waited = True

                if self.bot.waited:
                    await self.bot.spanSP.send(  # nadeko was offline for 20 mins
                        "Nadeko has gone offline.  New users won't be able to tag themselves, "
                        "and therefore will not be able to join the server.  Please be careful of this."
                    )

            if str(before.status) == 'offline' and str(after.status) == 'online':
                if self.bot.waited:
                    self.bot.waited = False  # waited is True if Nadeko has been offline for more than 20 minutes
                    await self.bot.spanSP.send('Nadeko is back online now.')

    @commands.group(invoke_without_command=True, aliases=['reaction', 'reactions'])
    async def reaction_logging(self, ctx):
        """Logs deleted reactions, aliases: 'reaction', 'reactions'"""
        result = self.module_logging(ctx, self.bot.db['reactions'])
        if result == 1:
            await ctx.send('Disabled reaction logging for this server')
        elif result == 2:
            await ctx.send('Enabled reaction logging for this server')
        elif result == 3:
            await ctx.send('You have not yet set a channel for reaction logging yet. Run `;reaction_logging set`')
        elif result == 4:
            await ctx.send('Before doing this, set a channel for logging with `;reaction_logging set`.  '
                           'Then, enable/disable logging by typing `;reaction_logging`.')

    @reaction_logging.command(aliases=['set'])
    async def reactions_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['reactions'])
        if result == 1:
            await ctx.send(f'Set the reaction logging channel as {ctx.channel.name}')
        elif result == 2:
            await ctx.send(f'Enabled reaction logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;reaction_logging`.')

    def make_reaction_embed(self, reaction, member):
        emb = discord.Embed(
            description=f'**{member.name}#{member.discriminator}** ({member.id})'
                        f' removed a reaction.',
            colour=0xD12B2B,
            timestamp=datetime.utcnow()
        )

        if reaction.message.content:
            emb.add_field(name='Original message:', value=reaction.message.content)
        if type(reaction.emoji) == discord.Emoji:
            emb.set_thumbnail(url=reaction.emoji.url)
        else:
            emb.add_field(name='Removed reaction', value=f'{reaction.emoji}')

        emb.set_footer(text=f'#{reaction.message.channel.name}',
                       icon_url=member.avatar_url_as(static_format="png"))

        return emb

    async def on_reaction_remove(self, reaction, member):
        if reaction.message.guild:
            guild = str(member.guild.id)
            if not member.bot:
                if guild in self.bot.db['reactions']:
                    guild_config: dict = self.bot.db['reactions'][guild]
                    if guild_config['enable']:
                        channel = self.bot.get_channel(guild_config["channel"])
                        await channel.send(embed=self.make_reaction_embed(reaction, member))

    @commands.group(invoke_without_command=True, aliases=['ban', 'bans'])
    async def ban_logging(self, ctx):
        """Logs deleted bans, aliases: 'ban', 'bans'"""
        if not ctx.me.guild_permissions.view_audit_log or not ctx.me.guild_permissions.embed_links:
            await ctx.send("I lack the permission to either view audit logs or embed links.  Please try again.")
            return
        result = self.module_logging(ctx, self.bot.db['bans'])
        if result == 1:
            await ctx.send('Disabled ban logging for this server')
        elif result == 2:
            await ctx.send('Enabled ban logging for this server')
        elif result == 3:
            await ctx.send('You have not yet set a channel for ban logging yet. Run `;ban_logging set`')
        elif result == 4:
            await ctx.send('Before doing this, set a channel for logging with `;ban_logging set`.  '
                           'Then, enable/disable logging by typing `;ban_logging`.')

    @ban_logging.command(aliases=['set'])
    async def bans_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['bans'])
        if result == 1:
            await ctx.send(f'Set the ban logging channel as {ctx.channel.name}')
        elif result == 2:
            await ctx.send(f'Enabled ban logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;ban_logging`.')

    @staticmethod
    async def make_ban_embed(guild, member):
        emb = None
        try:
            await asyncio.sleep(1)
            ban_entry = None
            async for entry in guild.audit_logs(limit=None, reverse=False,
                                                action=discord.AuditLogAction.ban,
                                                after=datetime.utcnow() - timedelta(seconds=10)):
                if entry.action == discord.AuditLogAction.ban:
                    ban_entry = entry
                    break
        except discord.errors.Forbidden as e:
            print('>>on_member_ban ' + e + '<<')
            return
        if ban_entry.created_at > datetime.utcnow() - timedelta(seconds=10) and ban_entry.target == member:
            reason = ban_entry.reason
            emb = True
        if emb:
            emb = discord.Embed(
                description=f'❌ **{member.name}#{member.discriminator}** was `banned` ({member.id})\n\n'
                            f'*by* {ban_entry.user.mention}\n**Reason**: {reason}',
                colour=0x000000,
                timestamp=datetime.utcnow()
            )
            emb.set_footer(text=f'User Banned',
                           icon_url=member.avatar_url_as(static_format="png"))
            return emb
        else:
            emb = discord.Embed(
                description=f'❌ **{member.name}#{member.discriminator}** was `banned` ({member.id})\n\n'
                            f'(Note, there was a bug in the code, could not get audit log data)',
                colour=0x000000,
                timestamp=datetime.utcnow()
            )
            emb.set_footer(text=f'User Banned',
                           icon_url=member.avatar_url_as(static_format="png"))

    async def on_member_ban(self, guild, member):
        guild_id: str = str(guild.id)
        if guild_id in self.bot.db['bans']:
            guild_config: dict = self.bot.db['bans'][guild_id]
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                await channel.send(embed=await self.make_ban_embed(guild, member))

        if member.id == 414873201349361664:
            await member.unban()
            try:
                self.bot.db['global_blacklist']['blacklist'].remove(414873201349361664)
                await hf.dump_json()
            except ValueError:
                pass

    @staticmethod
    def make_unban_embed(user):
        emb = discord.Embed(
            description=f'❕ **{user.name}#{user.discriminator}** was `unbanned` ({user.id})',
            colour=0x7F8C8D,
            timestamp=datetime.utcnow()
        )
        emb.set_footer(text=f'User unbanned',
                       icon_url=user.avatar_url_as(static_format="png"))
        return emb

    async def on_member_unban(self, guild, user):
        guild_id: str = str(guild.id)
        if guild_id in self.bot.db['bans']:
            guild_config: dict = self.bot.db['bans'][guild_id]
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                await channel.send(embed=self.make_unban_embed(user))

    @commands.group(invoke_without_command=True, aliases=['kick', 'kicks'])
    async def kick_logging(self, ctx):
        """Logs deleted kicks, aliases: 'kick', 'kicks'"""
        result = self.module_logging(ctx, self.bot.db['kicks'])
        if result == 1:
            await ctx.send('Disabled kick logging for this server')
        elif result == 2:
            await ctx.send('Enabled kick logging for this server')
        elif result == 3:
            await ctx.send('You have not yet set a channel for kick logging yet. Run `;kick_logging set`')
        elif result == 4:
            await ctx.send('Before doing this, set a channel for logging with `;kick_logging set`.  '
                           'Then, enable/disable logging by typing `;kick_logging`.')

    @kick_logging.command(aliases=['set'])
    async def kicks_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['kicks'])
        if result == 1:
            await ctx.send(f'Set the kick logging channel as {ctx.channel.name}')
        elif result == 2:
            await ctx.send(f'Enabled kick logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;kick_logging`.')

    async def make_kick_embed(self, member):
        # await asyncio.sleep(1)
        log_channel = self.bot.get_channel(self.bot.db['kicks'][str(member.guild.id)]['channel'])
        try:
            emb = None
            async for entry in member.guild.audit_logs(limit=1, reverse=False,
                                                       action=discord.AuditLogAction.kick,
                                                       after=datetime.utcnow() - timedelta(seconds=10)):
                if entry.created_at > datetime.utcnow() - timedelta(seconds=10) and entry.target == member:
                    kick_entry = entry
                    reason = kick_entry.reason
                    emb = True
        except discord.errors.Forbidden:
            await log_channel.send('Failed to post kick log due to lacking audit logs or embed permissions')
            return
        if emb:
            emb = discord.Embed(
                description=f'❌ **{member.name}#{member.discriminator}** was `kicked` ({member.id})\n\n'
                            f'*by* {kick_entry.user.mention}\n**Reason**: {reason}',
                colour=0x4C4C4C,
                timestamp=datetime.utcnow()
            )
            emb.set_footer(text=f'User Kicked',
                           icon_url=member.avatar_url_as(static_format="png"))
            return emb


def setup(bot):
    bot.add_cog(Logger(bot))
