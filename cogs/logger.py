import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import json
from imgurpython import ImgurClient
from imgurpython.helpers.error import ImgurClientError, ImgurClientRateLimitError
import functools
from Levenshtein import distance as LDist
import re
from .utils import helper_functions as hf

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SPAN_SERV_ID = 243838819743432704
NADEKO_ID = 116275390695079945
SPAN_WELCOME_CHAN_ID = 243838819743432704
JP_SERV_JHO_ID = 189571157446492161
BANS_CHANNEL_ID = 329576845949534208

with open(f'{dir_path}/gitignore/imgur_token.txt', 'r') as file:
    file.readline()  # comment line in text file
    client_id = file.readline()[:-1]
    client_secret = file.readline()[:-1]
    access_token = file.readline()[:-1]
    refresh_token = file.readline()

imgur_client = ImgurClient(client_id, client_secret, access_token, refresh_token)


class Logger(commands.Cog):
    """Logs stuff"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['mod_channel'] and ctx.command.name != 'set_mod_channel':
            return
        return hf.admin_check(ctx)

    def dump_json(self):
        with open(f'{dir_path}/database2.json', 'w') as write_file:
            json.dump(self.bot.db, write_file, indent=4)
            write_file.flush()
            os.fsync(write_file.fileno())
        os.remove(f'{dir_path}/database.json')
        os.rename(f'{dir_path}/database2.json', f'{dir_path}/database.json')

    @staticmethod
    async def module_logging(ctx, module):
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
        return result

    @staticmethod
    async def module_set(ctx, module):
        guild = str(ctx.guild.id)
        if guild in module:  # server already registered
            guild_config: dict = module[guild]
            guild_config['channel'] = ctx.channel.id
            result = 1
        else:  # new server
            module[guild] = {"enable": True, "channel": ctx.channel.id}
            result = 2
        return result

    async def module_disable_notification(self, guild, guild_config, module_name):
        try:
            channel = self.bot.db['mod_channel'][str(guild.id)]
        except KeyError:
            pass
        else:
            channel = self.bot.get_channel(channel)
            await hf.safe_send(channel, f"Disabled the {module_name} logs due to Rai possibly lacking some permission "
                               f"(possibly `Send Messages`, `Embed Links`, or for bans, `View Audit Log`)")
        finally:
            guild_config['enable'] = False

    @commands.group(invoke_without_command=True, aliases=['edits'])
    async def edit_logging(self, ctx):
        """Logs edited messages, aliases: 'edit', 'edits'"""
        result = await self.module_logging(ctx, self.bot.db['edits'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled edit logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled edit logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for edit logging yet. Run `;edit_logging set`')
        elif result == 4:
            self.bot.db['edits'][str(ctx.guild.id)]['distance_limit'] = 3
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;edit_logging set`.  '
                           'Then, enable/disable logging by typing `;edit_logging`.')

    @edit_logging.command(aliases=['set'])
    async def edits_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['edits'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the edit logging channel as {ctx.channel.name}')
        elif result == 2:
            self.bot.db['edits'][str(ctx.guild.id)]['distance_limit'] = 3
            await hf.safe_send(ctx, f'Enabled edit logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;edit_logging`.')

    @edit_logging.command(aliases=['set_distance'])
    async def distance_set(self, ctx, distance_limit: int):
        guild = str(ctx.guild.id)
        guild_config: dict = self.bot.db['edits'][guild]
        guild_config['distance_limit'] = distance_limit
        await hf.safe_send(ctx, f'Successfully set Levenshtein Distance limit to {distance_limit}.')

    @staticmethod
    def make_edit_embed(before, after, levenshtein_distance):
        author = before.author
        time_dif = round((datetime.utcnow() - before.created_at).total_seconds(), 1)
        emb = discord.Embed(
            description=f'**{author.name}#{author.discriminator}** ({author.id})'
                        f'\n**Message edited after {time_dif} seconds.** [(LD={levenshtein_distance})]'
                        f'(https://en.wikipedia.org/wiki/Levenshtein_distance) - ([Jump URL]({after.jump_url}))',
            colour=0xFF9933,
            timestamp=datetime.utcnow()
        )

        if len(before.content) > 0 and len(after.content) > 0:
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

        emb.set_footer(text=f'#{before.channel.name}', icon_url=before.author.avatar_url_as(static_format="png"))

        return emb

    @commands.Cog.listener()
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
                        if not channel:
                            return
                        await hf.safe_send(channel, 'Please set a Levenshtein Distance with `;edit set_distance 3`')
                        return
                    levenshtein_distance = LDist(before.content, after.content)
                    if levenshtein_distance > distance_limit:
                        channel = self.bot.get_channel(guild_config["channel"])
                        try:
                            await hf.safe_send(channel, embed=self.make_edit_embed(before, after, levenshtein_distance))
                        except discord.errors.Forbidden:
                            await self.module_disable_notification(before.message.guild, guild_config, 'message edits')
        await hf.uhc_check(after)

    @commands.group(invoke_without_command=True, aliases=['deletes'])
    async def delete_logging(self, ctx):
        """Logs deleted messages, aliases: 'delete', 'deletes'"""
        result = await self.module_logging(ctx, self.bot.db['deletes'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled delete logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled delete logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for delete logging yet. Run `;delete_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;delete_logging set`.  '
                           'Then, enable/disable logging by typing `;delete_logging`.')

    @delete_logging.command(aliases=['set'])
    async def deletes_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['deletes'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the delete logging channel as {ctx.channel.name}')
        elif result == 2:
            await hf.safe_send(ctx, f'Enabled delete logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;delete_logging`.')

    async def make_delete_embed(self, message):
        author = message.author
        time_dif = round((datetime.utcnow() - message.created_at).total_seconds(), 1)
        jump_url = ''
        async for msg in message.channel.history(limit=1, before=message):
            jump_url = msg.jump_url
        emb = discord.Embed(
            description=f'**{author.name}#{author.discriminator}** ({author.id})'
                        f'\n**Message deleted after {time_dif} seconds.** ([Jump URL]({jump_url}))',
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
            file_bool = False  # marks if someone uploaded a non-picture file
            for attachment in message.attachments:

                if attachment.filename.split('.')[-1].casefold() not in ['jpg', 'jpeg', 'png', 'gif',
                                                                         'apng', 'tiff', 'mov', 'mp4']:
                    attachment_names.append(attachment.filename)
                    file_bool = True
                    continue
                # asyncio black magic from here:
                # https://github.com/ScreenZoneProjects/ScreenBot-Discord/blob/master/cogs/image.py
                task = functools.partial(imgur_client.upload_from_url, attachment.proxy_url, anon=False)
                task = self.bot.loop.run_in_executor(None, task)
                try:
                    image = await asyncio.wait_for(task, timeout=10)
                    list_of_attachments.append(image['link'])
                    failed = None
                except (asyncio.TimeoutError, ImgurClientError, ImgurClientRateLimitError):
                    list_of_attachments.append(attachment.proxy_url)

            if list_of_attachments:
                emb.add_field(name='**Attachments:**', value='\n'.join(list_of_attachments))
                if failed:
                    emb.add_field(name='**Warning:**',
                                  value='Failed to reupload to imgur.  The above link may quickly 404')
                emb.set_thumbnail(url=list_of_attachments[0])
            if file_bool:
                emb.add_field(name='**File Attachments:**', value='\n'.join(attachment_names))



        emb.set_footer(text=f'#{message.channel.name}', icon_url=message.author.avatar_url_as(static_format="png"))

        return emb

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if ';report' in message.content:
            return  # for keeping anonymous reports anonymous
        if not message.guild:
            return
        guild = str(message.guild.id)
        if not message.author.bot:
            if guild in self.bot.db['deletes']:
                guild_config: dict = self.bot.db['deletes'][guild]
                if guild_config['enable']:
                    try:
                        channel = self.bot.get_channel(guild_config["channel"])
                    except KeyError:
                        guild_config['enable'] = False
                        return
                    if not channel:
                        del (guild_config['channel'])
                        hf.dump_json()
                        return
                    try:
                        await hf.safe_send(channel, embed=await self.make_delete_embed(message))
                    except discord.errors.Forbidden:
                        await self.module_disable_notification(message.guild, guild_config, 'message deletes')

    @commands.group(invoke_without_command=True, aliases=['welcome', 'welcomes', 'join', 'joins'])
    async def welcome_logging(self, ctx):
        """Logs server joins + tracks invite links, aliases: 'welcome', 'welcomes', 'join', 'joins'"""
        result = await self.module_logging(ctx, self.bot.db['welcomes'])
        server_config = self.bot.db['welcomes'][str(ctx.guild.id)]
        if result == 1:
            await hf.safe_send(ctx, 'Disabled welcome logging for this server')
        elif result == 2:
            try:
                server_config['invites'] = {invite.code: invite.uses for invite in await ctx.guild.invites()}
                server_config['invites_enable'] = True
                await hf.safe_send(ctx, 'Enabled welcome logging + invite tracking for this server (type `;invites` to disable'
                               ' invite tracking)')
            except discord.errors.Forbidden:
                await hf.safe_send(ctx, "I've enabled welcome tracking, but I lack permissions to get invite codes.  "
                               "If you want invite tracking too, give me `Manage Server` and then type "
                               f"`{ctx.message.content} invites` to enable invite tracking for future joins.")
                server_config['invites_enable'] = False

        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for welcome logging yet. Run `;welcome_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;welcome_logging set`.  '
                           'Then, enable/disable logging by typing `;welcome_logging`.')

    @welcome_logging.command(aliases=['set'])
    async def welcomes_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['welcomes'])
        server_config = self.bot.db['welcomes'][str(ctx.guild.id)]
        if result == 1:
            await hf.safe_send(ctx, f'Set the welcome logging channel as {ctx.channel.name}')
        elif result == 2:
            try:
                server_config['invites'] = {invite.code: invite.uses for invite in await ctx.guild.invites()}
                server_config['invites_enable'] = True
                await hf.safe_send(ctx, f'Enabled welcome logging + invite tracking and set the channel to `{ctx.channel.name}`.'
                               f'  Enable/disable logging by typing `;welcome_logging`.')
            except discord.errors.Forbidden:
                await hf.safe_send(ctx, "I've enabled welcome message, but I lack permissions to get invite codes.  "
                               "If you want invite tracking too, give me `Manage Server` and then type "
                               "`;invites` to enable invite tracking for future joins.")
                server_config['invites_enable'] = False

    @welcome_logging.command(aliases=['invites', 'invite'])
    async def invites_enable(self, ctx):
        """Enables/disables the identification of used invite links when people join"""
        guild = str(ctx.guild.id)
        if guild in self.bot.db['welcomes']:
            server_config = self.bot.db['welcomes'][guild]
            try:
                server_config['invites_enable'] = not server_config['invites_enable']
                await hf.safe_send(ctx, f"Set invite tracking to `{server_config['invites_enable']}`")
            except KeyError:
                server_config['invites_enable'] = True
                await hf.safe_send(ctx, 'Enabled invites tracking')

    @staticmethod
    async def make_welcome_embed(member, used_invite, channel, list_of_roles=None):
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
        if channel and hasattr(channel.last_message, 'jump_url'):
            emb.description += f"\n([Jump URL]({channel.last_message.jump_url}))"
        if used_invite:
            invite_string = f"Used {used_invite.inviter.name}'s link {used_invite.code}"
            footer_text = f'User Join ({member.guild.member_count}) {invite_string}'
        else:
            footer_text = f'User Join ({member.guild.member_count})'
        if list_of_roles:
            emb.add_field(name='Readded roles:', value=', '.join(reversed([role.name for role in list_of_roles])))

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
                await hf.safe_send(ctx, f'Set welcome message posting to {x}')
            except KeyError:
                config['enable'] = True
                x = config['enable']
                await hf.safe_send(ctx, f'Set welcome message posting to {x}')
        else:
            self.bot.db['welcome_message'][guild] = {}
            config = self.bot.db['welcome_message'][guild]
            config['enable'] = True
            x = config['enable']
            await hf.safe_send(ctx, f'Set welcome message posting to {x}')

    @welcome_message.command()
    async def set_message(self, ctx, *, message: str = None):
        if not message:
            await hf.safe_send(ctx, 'Please put your welcome message after the command invocation.  For example: \n'
                           '```;welcome_message set_message Welcome to the server `$NAME$`! Please read the rules```\n'
                           "Valid flags to use are: \n$NAME$ = The user's name in text\n`$USERMENTION$` = Mentions "
                           "the user\n`$SERVER$` = The name of the server")
        else:
            try:
                config = self.bot.db['welcome_message'][str(ctx.guild.id)]
            except KeyError:
                await hf.safe_send(ctx, f"Run `;welcome_message` first to setup the module")
                return
            config['message'] = message
            await hf.safe_send(ctx, f"Set welcome message to ```{message}```")

    @welcome_message.command()
    async def set_channel(self, ctx):
        try:
            config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        except KeyError:
            await ctx.invoke(self.welcome_message)
            config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        config['channel'] = ctx.channel.id
        await hf.safe_send(ctx, f"Set welcome message channel to {ctx.channel.mention}")

    @welcome_message.command()
    async def show_message(self, ctx):
        config = self.bot.db['welcome_message'][str(ctx.guild.id)]
        await hf.safe_send(ctx, "```" + config['message'] + "```")

    @commands.Cog.listener()
    async def on_member_join(self, member):
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
                await hf.safe_send(channel, message)
        except KeyError:
            pass

        """Join logging"""
        guild = str(member.guild.id)
        used_invite = None
        if guild in self.bot.db['welcomes']:
            if self.bot.db['welcomes'][guild]['enable']:
                server_config = self.bot.db['welcomes'][guild]
                channel = self.bot.get_channel(server_config['channel'])
                try:
                    invites_enable = server_config['invites_enable']
                except KeyError:
                    server_config['invites_enable'] = False
                    invites_enable = server_config['invites_enable']
                    await hf.safe_send(channel, "I've added a toggle for invite tracking since it requires `Manage Server` "
                                       "permission.  If you wish Rai to track used invite links for joins, please type "
                                       "`welcomes invites`.")
                if invites_enable:
                    old_invites = self.bot.db['welcomes'][str(member.guild.id)].setdefault('invites', {})
                    try:
                        invites = await member.guild.invites()
                    except discord.errors.Forbidden:
                        server_config['invites_enable'] = False
                        await hf.safe_send(channel, 
                            "Rai needs the `Manage Server` permission to track invites. For now, I've disabled "
                            "invite link tracking.  If you wish to reenable it, type `;welcomes invites` or use "
                            "the options menu (`;options`)")
                    else:
                        if not self.bot.db['welcomes'][str(member.guild.id)]['invites']:
                            old_invites = {invite.code: invite.uses for invite in invites}
                            self.bot.db['welcomes'][str(member.guild.id)]['invites'] = old_invites
                        else:
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
                                pass

                def get_list_of_roles():
                    list_of_roles = []
                    roles_dict = {role.id: role for role in member.guild.roles}
                    for role_code in config['users'][str(member.id)][1].split(','):
                        try:
                            list_of_roles.append(roles_dict[config['roles'][role_code]])
                        except KeyError:
                            pass
                    return list_of_roles

                """Japanese Server Welcome / readding roles"""
                list_of_roles = []
                if guild == '189571157446492161':
                    jpJHO = self.bot.get_channel(JP_SERV_JHO_ID)
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
                            list_of_roles = get_list_of_roles()
                            new_user_role = member.guild.get_role(249695630606336000)
                            if new_user_role in list_of_roles:
                                list_of_roles.remove(new_user_role)
                            if list_of_roles:
                                try:
                                    await member.add_roles(*list_of_roles)
                                    await member.remove_roles(new_user_role)
                                    await jpJHO.send(
                                        f"Welcome back {member.name}! I've given your previous roles back to you")
                                except discord.Forbidden:
                                    pass
                                del config['users'][str(member.id)]
                    finally:
                        if post_message:
                            if used_invite:
                                if str(used_invite.code) in japanese_links:
                                    await jpJHO.send(
                                        f'{member.name}さん、サーバーへようこそ！')  # a japanese person possibly
                            elif member.id != 414873201349361664:
                                await jpJHO.send(f'Welcome {member.name}!')  # probably not a japanese person
                        if member.id == 414873201349361664:
                            async for message in self.bot.jpJHO.history(limit=10):
                                if message.author.id == 159985870458322944:
                                    await message.delete()
                                    break
                            try:
                                msg = await self.bot.wait_for('message', timeout=10.0,
                                                              check=lambda m: m.author.id == 299335689558949888 and
                                                              m.channel == jpJHO)
                                await msg.delete()
                            except asyncio.TimeoutError:
                                pass

                else:
                    try:
                        config = self.bot.db['readd_roles'][str(member.guild.id)]
                    except KeyError:
                        pass
                    else:
                        if config['enable'] and str(member.id) in config['users']:
                            list_of_roles = get_list_of_roles()
                            await member.add_roles(*list_of_roles)
                            try:
                                await member.send(
                                    f"Welcome back {member.name}! I've given your previous roles back to you")
                            except discord.errors.Forbidden:
                                pass
                            del config['users'][str(member.id)]

                try:
                    if str(member.guild.id) in self.bot.db['welcome_message']:
                        channel_id = self.bot.db['welcome_message'][str(member.guild.id)]['channel']
                        welcome_channel = member.guild.get_channel(channel_id)
                    else:
                        welcome_channel = None
                    x = await self.make_welcome_embed(member, used_invite, welcome_channel, list_of_roles)
                    await hf.safe_send(channel, embed=x)
                except discord.errors.Forbidden:
                    await hf.safe_send(channel, 'Rai needs permission to post embeds to track joins')


        """ban invite link names"""
        try:
            if self.bot.db['auto_bans'][guild]['enable']:
                pat = re.compile(r'.*(discord|discordapp).(gg|com/invite)/[A-Z0-9]{1,7}.*', re.I)
                if re.match(pat, member.name):
                    guild = str(member.guild.id)
                    await member.ban(reason="Name was a discord invite link")
                    message = f"Banned user `{member.name}` from {member.guild.name} for being an invite link name\n" \
                              f"({member.id} {member.mention})"
                    await self.bot.get_channel(BANS_CHANNEL_ID).send(message)
                    self.bot.db['global_blacklist']['blacklist'].append(member.id)
                    channel = self.bot.get_channel(533863928263082014)
                    await hf.safe_send(channel, 
                        f"❌ Automatically added `{member.name} ({member.id}`) to the blacklist for "
                        f"being an invite-link name")
                    return  # stops execution of the rest of the code if was invite link name
        except KeyError:
            pass

        """blacklist bans"""
        config = self.bot.db['global_blacklist']
        if member.id in config['blacklist']:
            try:
                if config[str(member.guild.id)]['enable']:
                    await member.ban(reason="On the global blacklist")
                    bans_channel = self.bot.get_channel(BANS_CHANNEL_ID)
                    await hf.ban_check_servers(self.bot, bans_channel, member)
                    return
            except KeyError:
                pass

        # """Spanish Server welcome"""
        # spanServ = self.bot.get_guild(SPAN_SERV_ID)
        # if member.guild == spanServ:
        #     nadeko_obj = spanServ.get_member(NADEKO_ID)
        #     if str(nadeko_obj.status) == 'offline':
        #         await self.bot.get_channel(SPAN_WELCOME_CHAN_ID).send(
        #             'Welcome to the server.  Nadeko is currently down, '
        #             'so please state your roles and someone in welcoming party will come to'
        #             ' assign your role as soon as possible.  If no one comes, please tag the mods with `@Mods`.  '
        #             'Thanks! '
        #             '(<@&470364944479813635>)'
        #         )

    @commands.group(invoke_without_command=True, aliases=['leave', 'leaves'])
    async def leave_logging(self, ctx):
        """Logs leaves + shows list of roles at time of leave, aliases: 'leave', 'leaves'"""
        result = await self.module_logging(ctx, self.bot.db['leaves'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled leave logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled leave logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for leave logging yet. Run `;leave_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;leave_logging set`.  '
                           'Then, enable/disable logging by typing `;leave_logging`.')

    @leave_logging.command(aliases=['set'])
    async def leaves_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['leaves'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the leave logging channel as `{ctx.channel.name}`')
        elif result == 2:
            await hf.safe_send(ctx, f'Enabled leave logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;leave_logging`.')

    @staticmethod
    def make_leave_embed(member):
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

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = str(member.guild.id)
        if guild in self.bot.db['leaves']:
            if self.bot.db['leaves'][guild]['enable']:
                guild_config = self.bot.db['leaves'][guild]
                channel = self.bot.get_channel(guild_config['channel'])
                if not channel:
                    del self.bot.db['leaves'][guild]
                    return
                try:
                    await hf.safe_send(channel, embed=self.make_leave_embed(member))
                except discord.errors.Forbidden:
                    await self.module_disable_notification(member.guild, guild_config, 'member leave')

        try:
            config = self.bot.db['readd_roles'][str(member.guild.id)]
        except KeyError:
            pass
        else:
            if config['enable']:
                if 'roles' in config:
                    codes = {str(y): x for x, y in config['roles'].items()}  # {str(role_id): index} dictionary
                else:
                    codes = config['roles'] = {}
                found_roles = []
                for role in member.roles:
                    if role.name in ['Nitro Booster', 'New User'] or role.id in [249695630606336000, member.guild.id]:
                        pass
                    else:
                        if str(role.id) in codes:
                            found_roles.append(codes[str(role.id)])
                        else:
                            index = str(len(codes))
                            config['roles'][index] = role.id
                            codes[str(role.id)] = index
                            found_roles.append(codes[str(role.id)])

                if found_roles:  # if the role list isn't empty (i.e., no roles)
                    config['users'][str(member.id)] = [datetime.utcnow().strftime("%Y%m%d"), ','.join(found_roles)]

        if guild in self.bot.db['kicks']:
            guild_config: dict = self.bot.db['kicks'][guild]
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                try:
                    emb = await self.make_kick_embed(member)
                except discord.errors.Forbidden:
                    await self.module_disable_notification(member.guild, guild_config, 'member kick')
                    return
                if emb:
                    await hf.safe_send(channel, embed=emb)

    @commands.group(invoke_without_command=True, aliases=['nickname', 'nicknames'])
    async def nickname_logging(self, ctx):
        """Logs nicknames changes, aliases: 'nickname', 'nicknames'"""
        result = await self.module_logging(ctx, self.bot.db['nicknames'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled nickname logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled nickname logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for nickname logging yet. Run `;nickname_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;nickname_logging set`.  '
                           'Then, enable/disable logging by typing `;nickname_logging`.')

    @nickname_logging.command(aliases=['set'])
    async def nicknames_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['nicknames'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the nickname logging channel as `{ctx.channel.name}`')
        elif result == 2:
            await hf.safe_send(ctx, f'Enabled nickname logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;nickname_logging`.')

    @staticmethod
    def make_nickname_embed(before, after):
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

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        guild = str(before.guild.id)
        if guild in self.bot.db['nicknames']:
            if self.bot.db['nicknames'][guild]['enable']:
                guild_config = self.bot.db['nicknames'][guild]
                channel = self.bot.get_channel(guild_config['channel'])
                if not channel:
                    return
                if before.name == after.name and before.nick == after.nick:
                    return

                try:
                    embed = self.make_nickname_embed(before, after)
                except discord.errors.Forbidden:
                    await self.module_disable_notification(before.guild, guild_config, 'nickname and username changes')
                    return

                if before.name != after.name:  # username change
                    embed.description = f"**{before.name}#{before.discriminator}**'s username was set to " \
                                        f"**{after.name}#{after.discriminator}**"
                    await hf.safe_send(channel, embed=embed)

                if before.nick != after.nick:  # nickname change
                    if before.nick and not after.nick:  # nickname removed
                        embed.description = f"**{before.nick}**'s nickname was **removed**"
                    elif not before.nick and after.nick:  # nickname added
                        embed.description = \
                            f"**{before.name}#{before.discriminator}**'s nickname was set to **{after.nick}**"
                    elif before.nick and after.nick:  # nickname changed
                        pass
                    else:  # no nickname changes
                        return
                    await hf.safe_send(channel, embed=embed)

        """Nadeko updates"""
        if self.bot.user.name == 'Rai':
            spanServ = self.bot.get_guild(SPAN_SERV_ID)
            if before == spanServ.get_member(116275390695079945) and before.guild == spanServ:
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
        result = await self.module_logging(ctx, self.bot.db['reactions'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled reaction logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled reaction logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for reaction logging yet. Run `;reaction_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;reaction_logging set`.  '
                           'Then, enable/disable logging by typing `;reaction_logging`.')

    @reaction_logging.command(aliases=['set'])
    async def reactions_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['reactions'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the reaction logging channel as {ctx.channel.name}')
        elif result == 2:
            await hf.safe_send(ctx, f'Enabled reaction logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;reaction_logging`.')

    @staticmethod
    def make_reaction_embed(reaction, member):
        emb = discord.Embed(
            description=f'**{member.name}#{member.discriminator}** ({member.id}) '
                        f' removed a reaction. ([Jump URL]({reaction.message.jump_url}))',
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

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, member):
        if reaction.message.guild:
            guild = str(member.guild.id)
            if not member.bot:
                if guild in self.bot.db['reactions']:
                    guild_config: dict = self.bot.db['reactions'][guild]
                    if guild_config['enable']:
                        channel = self.bot.get_channel(guild_config["channel"])
                        try:
                            await hf.safe_send(channel, embed=self.make_reaction_embed(reaction, member))
                        except discord.errors.Forbidden:
                            await self.module_disable_notification(
                                reaction.message.guild, guild_config, 'reaction remove')
                            return
                        except AttributeError:
                            del guild_config

    @commands.group(invoke_without_command=True, aliases=['bans'])
    async def ban_logging(self, ctx):
        """Logs deleted bans, aliases: 'bans'"""
        if not ctx.me.guild_permissions.view_audit_log or not ctx.me.guild_permissions.embed_links:
            await hf.safe_send(ctx, "I lack the permission to either view audit logs or embed links.  Please try again.")
            return
        result = await self.module_logging(ctx, self.bot.db['bans'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled ban logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled ban logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for ban logging yet. Run `;ban_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;ban_logging set`.  '
                           'Then, enable/disable logging by typing `;ban_logging`.')

    @ban_logging.command(aliases=['set'])
    async def bans_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['bans'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the ban logging channel as {ctx.channel.name}')
        elif result == 2:
            await hf.safe_send(ctx, f'Enabled ban logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;ban_logging`.')

    async def make_ban_embed(self, guild, member):
        ban_entry = None
        reason = "(could not find audit log entry)"
        by = ""
        await asyncio.sleep(3)
        async for entry in guild.audit_logs(limit=None, oldest_first=False,
                                            action=discord.AuditLogAction.ban,
                                            after=datetime.utcnow() - timedelta(seconds=20)):
            if entry.action == discord.AuditLogAction.ban and entry.target == member:
                ban_entry = entry
                reason = ban_entry.reason
                by = f'*by* {ban_entry.user.name}'
                break
        emb = discord.Embed(
            colour=0x000000,
            timestamp=datetime.utcnow(),
            description=''
        )
        if not reason:
            reason = '(none given)'
        if reason.startswith('⁣') or '-s' in reason:
            reason = reason.replace('⁣', '').replace('-s ', '').replace(' -s', '')
            emb.description = '⁣'
        if reason.startswith('⠀') or '-c' in reason:
            reason = reason.replace('⠀', '').replace('-c', '')
            emb.description = '⠀'
        if reason.startswith('*by* '):
            emb.description += f'❌ **{member.name}#{member.discriminator}** was `banned` ({member.id})\n\n' \
                               f'{reason}'
        else:
            emb.description += f'❌ **{member.name}#{member.discriminator}** was `banned` ({member.id})\n\n' \
                               f'{by}\n**Reason**: {reason}'
        
        emb.set_footer(text=f'User Banned',
                       icon_url=member.avatar_url_as(static_format="png"))
        return emb

    @commands.Cog.listener()
    async def on_member_ban(self, guild, member):
        if member.id == 414873201349361664:
            try:
                await member.unban()
            except discord.errors.NotFound:
                pass
            except discord.errors.Forbidden:
                pass

        guild_id: str = str(guild.id)
        if guild_id in self.bot.db['bans']:
            guild_config: dict = self.bot.db['bans'][guild_id]
            try:
                emb = await self.make_ban_embed(guild, member)
            except discord.errors.Forbidden:
                await self.module_disable_notification(guild, guild_config, 'bans')
                return
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                await hf.safe_send(channel, embed=emb)

            try:
                if (guild_config['crosspost'] and not emb.description.startswith('⁣')) or \
                        (emb.description.startswith('⠀')):
                    old_desc = emb.description.split('\n\n')
                    new_desc = old_desc[0] + f'\n\n*on* {guild.name}\n' + old_desc[1]
                    emb.description = new_desc
                    bans_channel = self.bot.get_channel(BANS_CHANNEL_ID)
                    crosspost_msg = await bans_channel.send(member.mention, embed=emb)

                    if member.id == 270366726737231884:
                        return

                    await hf.ban_check_servers(self.bot, bans_channel, member)

                    await crosspost_msg.add_reaction('⬆')
            except KeyError:
                pass

        if member.id == 414873201349361664:
            try:
                await member.unban()
            except discord.errors.NotFound:
                pass
            try:
                self.bot.db['global_blacklist']['blacklist'].remove(414873201349361664)
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

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        guild_id: str = str(guild.id)
        if guild_id in self.bot.db['bans']:
            guild_config: dict = self.bot.db['bans'][guild_id]
            if guild_config['enable']:
                channel = self.bot.get_channel(guild_config["channel"])
                try:
                    await hf.safe_send(channel, embed=self.make_unban_embed(user))
                except discord.errors.Forbidden:
                    await self.module_disable_notification(guild, guild_config, 'unban')
                    return

    @commands.group(invoke_without_command=True, aliases=['kick', 'kicks'])
    async def kick_logging(self, ctx):
        """Logs deleted kicks, aliases: 'kick', 'kicks'"""
        result = await self.module_logging(ctx, self.bot.db['kicks'])
        if result == 1:
            await hf.safe_send(ctx, 'Disabled kick logging for this server')
        elif result == 2:
            await hf.safe_send(ctx, 'Enabled kick logging for this server')
        elif result == 3:
            await hf.safe_send(ctx, 'You have not yet set a channel for kick logging yet. Run `;kick_logging set`')
        elif result == 4:
            await hf.safe_send(ctx, 'Before doing this, set a channel for logging with `;kick_logging set`.  '
                           'Then, enable/disable logging by typing `;kick_logging`.')

    @kick_logging.command(aliases=['set'])
    async def kicks_set(self, ctx):
        result = await self.module_set(ctx, self.bot.db['kicks'])
        if result == 1:
            await hf.safe_send(ctx, f'Set the kick logging channel as {ctx.channel.name}')
        elif result == 2:
            await hf.safe_send(ctx, f'Enabled kick logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;kick_logging`.')

    async def make_kick_embed(self, member):
        # await asyncio.sleep(1)
        log_channel = self.bot.get_channel(self.bot.db['kicks'][str(member.guild.id)]['channel'])
        try:
            emb = None
            async for entry in member.guild.audit_logs(limit=1, oldest_first=False,
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
