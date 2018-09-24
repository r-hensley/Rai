import discord
from discord.ext import commands
import asyncio
from imgurpython import ImgurClient
from datetime import datetime
import json
from imgurpython import ImgurClient
from imgurpython.helpers.error import ImgurClientError
import functools
from Levenshtein import distance as LDist

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
            json.dump(self.bot.db, write_file)
            write_file.flush()
            os.fsync(write_file.fileno())
        os.remove(f'{dir_path}/database.json')
        os.rename(f'{dir_path}/database2.json', f'{dir_path}/database.json')

    def module_logging(self, ctx, module):
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
        self.dump_json()
        return result

    def module_set(self, ctx, module):
        guild = str(ctx.guild.id)
        if guild in module:  # server already registered
            guild_config: dict = module[guild]
            guild_config['channel'] = ctx.channel.id
            result = 1
        else:  # new server
            module[guild] = {"enable": True, "channel": ctx.channel.id}
            result = 2
        self.dump_json()
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
            self.dump_json()
            await ctx.send('Before doing this, set a channel for logging with `;edit_logging set`.  '
                           'Then, enable/disable logging by typing `;edit_logging`.')

    @edit_logging.command(aliases=['set'])
    async def edits_set(self, ctx):
        result = self.module_set(ctx, self.bot.db['edits'])
        if result == 1:
            await ctx.send(f'Set the edit logging channel as {ctx.channel.name}')
        elif result == 2:
            self.bot.db['edits'][str(ctx.guild.id)]['distance_limit'] = 3
            self.dump_json()
            await ctx.send(f'Enabled edit logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;edit_logging`.')

    @edit_logging.command(aliases=['set_distance'])
    async def distance_set(self, ctx, distance_limit: int):
        guild = str(ctx.guild.id)
        guild_config: dict = self.bot.db['edits'][guild]
        guild_config['distance_limit'] = distance_limit
        await ctx.send(f'Successfully set Levenshtein Distance limit to {distance_limit}.')
        self.dump_json()
            
    def make_edit_embed(self, before, after):
        author = before.author
        time_dif = round((after.edited_at - before.created_at).total_seconds(), 1)
        emb = discord.Embed(
            description=f'**{author.name}#{author.discriminator}** ({author.id})'
                        f'\n**Message edited after {time_dif} seconds.**',
            colour=0xFF9933,
            timestamp=datetime.utcnow()
        )

        if len(before.content) < 1025:
            emb.add_field(name='**Before:**', value=before.content)
        else:
            print(len(before.content[:1000]), len(before.content[1000:]))
            emb.add_field(name='**Before:** (Part 1):', value=before.content[:1000])
            emb.add_field(name='**Before:** (Part 2):', value=before.content[1000:])

        if len(after.content) < 1025:
            emb.add_field(name='**After:**', value=after.content)
        else:
            print(len(after.content[:1000]), len(after.content[1000:]))
            emb.add_field(name='**After:** (Part 1)', value=after.content[:1000])
            emb.add_field(name='**After:** (Part 2)', value=after.content[1000:])

        emb.set_footer(text=f'<#{before.channel.id}>', icon_url=before.author.avatar_url_as(static_format="png"))

        return emb
    
    async def on_message_edit(self, before, after):
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
                        emb = self.make_edit_embed(before, after)
                        emb.add_field(name='Note:', value=f'Levenshtein Distance: {levenshtein_distance}')
                        await channel.send(embed=emb)
                    else:
                        # channel = self.bot.get_channel(guild_config["channel"])
                        # emb = self.make_edit_embed(before, after)
                        # emb.add_field(name='Note:', value=f'Under Levenshtein Distance limit ({levenshtein_distance})')
                        # await channel.send(embed=emb)
                        pass


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
        result = self.module_set(ctx, self.bot.db['deletes'])
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
            emb.add_field(name='**Message:**', value=f'{message.content}')

        if message.attachments:
            list_of_attachments = []
            for attachment in message.attachments:
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
                    failed = True

            emb.add_field(name='**Attachments:**', value='\n'.join(list_of_attachments))
            if failed:
                emb.add_field(name='**Warning:**', value='Failed to reupload to imgur.  The above link may quickly 404')
            emb.set_thumbnail(url=list_of_attachments[0])

        emb.set_footer(text=f'#{message.channel.name}', icon_url=message.author.avatar_url_as(static_format="png"))

        return emb
    
    async def on_message_delete(self, message):
        guild = str(message.guild.id)
        if not message.author.bot:
            if guild in self.bot.db['deletes']:
                guild_config: dict = self.bot.db['deletes'][guild]
                if guild_config['enable']:
                    channel = self.bot.get_channel(guild_config["channel"])
                    await channel.send(embed=await self.make_delete_embed(message))

    @commands.group(invoke_without_command=True, aliases=['welcome', 'welcomes', 'join', 'joins'])
    async def welcome_logging(self, ctx):
        """Logs server joins + tracks invite links, aliases: 'welcome', 'welcomes', 'join', 'joins'"""
        result = self.module_logging(ctx, self.bot.db['welcomes'])
        server_config = self.bot.db['welcomes'][str(ctx.guild.id)]
        if result == 1:
            await ctx.send('Disabled welcome logging for this server')
        elif result == 2:
            server_config['invites'] = {invite.code: invite.uses for invite in await ctx.guild.invites()}
            self.dump_json()
            await ctx.send('Enabled welcome logging for this server')
        elif result == 3:
            await ctx.send('You have not yet set a channel for welcome logging yet. Run `;welcome_logging set`')
        elif result == 4:
            await ctx.send('Before doing this, set a channel for logging with `;welcome_logging set`.  '
                           'Then, enable/disable logging by typing `;welcome_logging`.')

    @welcome_logging.command(aliases=['set'])
    async def welcomes_set(self, ctx):
        result = self.module_set(ctx, self.bot.db['welcomes'])
        if result == 1:
            await ctx.send(f'Set the welcome logging channel as {ctx.channel.name}')
        elif result == 2:
            server_config['invites'] = {invite.code: invite.uses for invite in await ctx.guild.invites()}
            self.dump_json()
            await ctx.send(f'Enabled welcome logging and set the channel to `{ctx.channel.name}`.  Enable/disable'
                           f'logging by typing `;welcome_logging`.')
            
    def make_welcome_embed(self, member, used_invite):
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

    async def on_member_join(self, member):
        guild = str(member.guild.id)
        if guild in self.bot.db['welcomes']:
            if self.bot.db['welcomes'][guild]['enable']:
                server_config = self.bot.db['welcomes'][guild]
                old_invites = self.bot.db['welcomes'][str(member.guild.id)]['invites']
                invites = await member.guild.invites()
                new_invites = {invite.code: invite.uses for invite in invites}
                used_invite = None
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
                    print('Was unable to find invite')
                self.dump_json()
                channel = self.bot.get_channel(server_config['channel'])
                await channel.send(embed=self.make_welcome_embed(member, used_invite))

        """Japanese Server Welcome"""
        if guild == '189571157446492161':
            # check if they joined from a Japanese site or other
            # the following links are specifically the ones we've used to advertise on japanese sites
            japanese_links = ['6DXjBs5', 'WcBF7XZ', 'jzfhS2', 'w6muGjF', 'TxdPsSm', 'MF9XF89', 'RJrcSb3']
            if str(used_invite.code) in japanese_links:
                await self.bot.jpJHO.send(f'{m.name}さん、サーバーへようこそ！')  # a japanese person possibly
            elif m.id != 414873201349361664:
                await self.bot.jpJHO.send(f'Welcome {m.name}!')  # probably not a japanese person

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
        result = self.module_set(ctx, self.bot.db['leaves'])
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

        if len(member.roles) > 1:  # all users have the @everyone role
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
                await channel.send(embed=self.make_leave_embed(member))

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
        result = self.module_set(ctx, self.bot.db['nicknames'])
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
            if before.nick != after.nick:
                if self.bot.db['nicknames'][guild]['enable']:
                    server_config = self.bot.db['nicknames'][guild]
                    channel = self.bot.get_channel(server_config['channel'])
                    if before.nick and not after.nick:  # nickname removed
                        embed = self.make_nickname_embed(before, after)
                        embed.description = f"**{before.nick}**'s nickname was **removed**"
                    if not before.nick and after.nick:  # nickname added
                        embed = self.make_nickname_embed(before, after)
                        embed.description = \
                            f"**{before.name}#{before.discriminator}**'s nickname was set to **{after.nick}**"
                    if before.name != after.name:
                        embed = self.make_nickname_embed(before, after)
                        embed.description = \
                            f"**{before.name}#{before.discriminator}**'s username was set to " \
                            f"**{after.name}#{after.discriminator}**"
                    if before.nick and after.nick:
                        embed = self.make_nickname_embed(before, after)
                    await channel.send(embed=embed)
                    
                    

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
        result = self.module_set(ctx, self.bot.db['reactions'])
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

        emb.add_field(name='Original message:', value=reaction.message.content)
        if type(reaction.emoji) == discord.Emoji:
            emb.set_thumbnail(url=reaction.emoji.url)
        else:
            emb.add_field(name='Removed reaction', value=f'{reaction.emoji}')

        emb.set_footer(text=f'#{reaction.message.channel.name}',
                       icon_url=member.avatar_url_as(static_format="png"))

        return emb

    async def on_reaction_remove(self, reaction, member):
        guild = str(member.guild.id)
        if not member.bot:
            if guild in self.bot.db['reactions']:
                guild_config: dict = self.bot.db['reactions'][guild]
                if guild_config['enable']:
                    channel = self.bot.get_channel(guild_config["channel"])
                    await channel.send(embed=self.make_reaction_embed(reaction, member))


def setup(bot):
    bot.add_cog(Logger(bot))