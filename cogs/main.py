import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta, date
from .utils import helper_functions as hf
import re
from textblob import TextBlob as tb
import textblob
import requests
import json

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
COLOR_CHANNEL_ID = 577382927596257280
BLACKLIST_CHANNEL_ID = 533863928263082014
BANS_CHANNEL_ID = 329576845949534208
MODERATING_CHANNEL_ID = 257990571103223809
MODCHAT_SERVER_ID = 257984339025985546
RYRY_SPAM_CHAN = 275879535977955330
JP_SERVER_ID = 189571157446492161


def blacklist_check():
    async def pred(ctx):
        if not ctx.guild:
            return
        if ctx.author in ctx.bot.get_guild(MODCHAT_SERVER_ID).members:
            if ctx.guild.id == MODCHAT_SERVER_ID or hf.admin_check(ctx):
                return True

    return commands.check(pred)


class Main(commands.Cog):
    """My custom cog that does stuff!"""

    def __init__(self, bot):
        self.bot = bot
        self.ignored_characters = []
        hf.setup(bot)

    @commands.command()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def new_help(self, ctx):
        x = self.bot.commands
        msg_dict = {}
        emb = discord.Embed(title='Help', description="Type `;help <command>` for more info on any command or category")
        for command in x:
            if await command.can_run(ctx) and not command.hidden:
                if command.cog_name in msg_dict:
                    msg_dict[command.cog_name].append(command)
                else:
                    msg_dict[command.cog_name] = [command]
        for cog in msg_dict:
            str = ''
            for command in msg_dict[cog]:
                if command.short_doc:
                    str += f"⠀⠀**{command.name}**\n{command.short_doc}\n"
                else:
                    str += f"⠀⠀**{command.name}**\n"
            emb.add_field(name=f"⁣\n__{command.cog_name}__",
                          value=str, inline=False)
        await hf.safe_send(ctx, embed=emb)

    @commands.command(hidden=True)
    async def _check_desync_voice(self, ctx):
        config = self.bot.stats
        for guild_id in config:
            if guild_id not in config:
                continue
            if not config[guild_id]['enable']:
                continue
            guild_config = config[guild_id]
            guild = self.bot.get_guild(int(guild_id))
            try:
                voice_channels = guild.voice_channels
            except AttributeError:
                continue
            users_in_voice = []
            for channel in voice_channels:
                users_in_voice += [str(member.id) for member in channel.members]
            for user_id in guild_config['voice']['in_voice'].copy():  # all users in the database
                if user_id not in users_in_voice:  # if not in voice, remove from database
                    member = guild.get_member(int(user_id))
                    if not member:
                        del guild_config['voice']['in_voice'][user_id]
                        return
                    await ctx.invoke(self.bot.get_command("command_out_of_voice"), member)

            for user_id in users_in_voice.copy():  # all users in voice
                member = guild.get_member(int(user_id))
                vs = member.voice
                if vs:
                    if vs.deaf or vs.self_deaf or vs.afk:  # deafened or afk but in database, remove
                        await ctx.invoke(self.bot.get_command("command_out_of_voice"), member)
                    if user_id not in guild_config['voice']['in_voice']:  # in voice, not in database, add
                        if vs.channel:
                            await ctx.invoke(self.bot.get_command("command_into_voice"), member, vs)
                else:
                    await ctx.invoke(self.bot.get_command("command_out_of_voice"), member)  # in voice but no vs? remove

    @commands.command(hidden=True)
    async def _unban_users(self, ctx):
        config = self.bot.db['bans']
        for guild_id in config:
            unbanned_users = []
            guild_config = config[guild_id]
            try:
                mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][guild_id])
            except KeyError:
                mod_channel = None
            if 'timed_bans' in guild_config:
                for member_id in guild_config['timed_bans'].copy():
                    unban_time = datetime.strptime(guild_config['timed_bans'][member_id], "%Y/%m/%d %H:%M UTC")
                    if unban_time < datetime.utcnow():
                        guild = self.bot.get_guild(int(guild_id))
                        member = discord.Object(id=member_id)
                        try:
                            await guild.unban(member, reason="End of timed ban")
                            del config[guild_id]['timed_bans'][member_id]
                            unbanned_users.append(member_id)
                        except discord.NotFound:
                            pass
            if mod_channel and unbanned_users:
                text_list = []
                for i in unbanned_users:
                    user = self.bot.get_user(int(i))
                    text_list.append(f"{user.mention} ({user.name})")
                await hf.safe_send(mod_channel,
                                   embed=discord.Embed(description=f"I've unbanned {', '.join(text_list)}, as"
                                                                   f"the time for their temporary ban has expired",
                                                       color=discord.Color(int('00ffaa', 16))))

    @commands.command(hidden=True)
    async def _unmute_users(self, ctx):
        config = self.bot.db['mutes']
        for guild_id in config:
            unmuted_users = []
            guild_config = config[guild_id]
            try:
                mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][guild_id])
            except KeyError:
                mod_channel = None
            if 'timed_mutes' in guild_config:
                for member_id in guild_config['timed_mutes'].copy():
                    unmute_time = datetime.strptime(guild_config['timed_mutes'][member_id], "%Y/%m/%d %H:%M UTC")
                    if unmute_time < datetime.utcnow():
                        result = await ctx.invoke(self.bot.get_command('unmute'), member_id, int(guild_id))
                        if result:
                            unmuted_users.append(member_id)
            if unmuted_users and mod_channel:
                text_list = []
                for i in unmuted_users:
                    user = self.bot.get_user(int(i))
                    if user:
                        text_list.append(f"{user.mention} ({user.name})")
                    if not user:
                        text_list.append(f"{i}")
                await hf.safe_send(mod_channel,
                                   embed=discord.Embed(description=f"I've unmuted {', '.join(text_list)}, as "
                                                                   f"the time for their temporary mute has expired",
                                                       color=discord.Color(int('00ffaa', 16))))

    @commands.command(hidden=True)
    async def _delete_old_stats_days(self, ctx):
        for server_id in self.bot.stats:
            config = self.bot.stats[server_id]
            for day in config['messages'].copy():
                days_ago = (datetime.utcnow() - datetime.strptime(day, "%Y%m%d")).days
                if days_ago > 30:
                    for user_id in config['messages'][day]:
                        for channel_id in config['messages'][day][user_id]:
                            try:
                                int(channel_id)  # skip 'emoji' and 'lang' entries
                            except ValueError:
                                continue
                            if 'member_totals' not in config:
                                config['member_totals'] = {}
                            if user_id in config['member_totals']:
                                config['member_totals'][user_id] += config['messages'][day][user_id][channel_id]
                            else:
                                config['member_totals'][user_id] = config['messages'][day][user_id][channel_id]
                    del config['messages'][day]
            for day in config['voice']['total_time'].copy():
                days_ago = (datetime.utcnow() - datetime.strptime(day, "%Y%m%d")).days
                if days_ago > 30:
                    del config['voice']['total_time'][day]

    # @commands.command(aliases=['r'])
    # async def iam(self, ctx, role):
    #     shortened_names = {'0': 'test0', '1': 'test1', '2': 'test2', '3': 'test3', '4': 'test4', '5': 'test5'}
    #     if role in shortened_names:
    #         desired_role = shortened_names[role]
    #     else:
    #         desired_role = role
    #     role_dict = {}
    #     if desired_role not in ['test0', 'test1', 'test2', 'test3', 'test4', 'test5']:
    #         return
    #     for role_name in ['test0', 'test1', 'test2', 'test3', 'test4', 'test5']:
    #         role_dict[role_name] = discord.utils.get(ctx.guild.roles, name=role_name)
    #     old_role = None
    #     for role_name in role_dict:
    #         if role_dict[role_name] in ctx.author.roles:
    #             await ctx.author.remove_roles(role_dict[role_name])
    #             old_role = role_name
    #     if not old_role:
    #         await hf.safe_send(ctx, "You must have one of the test roles first before using this.")
    #         return
    #     await ctx.author.add_roles(role_dict[desired_role])
    #     old = role_dict[old_role]
    #     new = role_dict[desired_role]
    #     await hf.safe_send(ctx, embed=discord.Embed(description=f"Changed {ctx.author.display_name} "
    #                                                    f"from {old.mention} to {new.mention}.",
    #                                        color=role_dict[desired_role].color))
    #
    # @commands.group(aliases=['c', 'color'], invoke_without_command=True)
    # async def color_change(self, ctx, role_name_in=None, color_in=None):
    #     colors_channel = self.bot.get_channel(COLOR_CHANNEL_ID)
    #     shortened_names = {'0': 'test0', '1': 'test1', '2': 'test2', '3': 'test3', '4': 'test4', '5': 'test5',
    #                        '6': 'test6', '7': 'test7'}
    #     role_names = {'test0': 'NE', 'test1': 'FE', 'test2': 'OL', 'test3': 'NS', 'test4': 'FS', 'test5': 'Mods'}
    #     if role_name_in in shortened_names:
    #         role_name_in = shortened_names[role_name_in]
    #     if ctx.guild.id == 243838819743432704:
    #         if not color_in:
    #             color_str = "The current colors are: \n"
    #             for role_name in ['test0', 'test1', 'test2', 'test3', 'test4', 'test5', 'test6', 'test7']:
    #                 role = discord.utils.get(ctx.guild.roles, name=role_name)
    #                 if not role:
    #                     continue
    #                 color_str += f"{role.mention}: #{role.color.r:02X},{role.color.g:02X},{role.color.b:02X}"
    #                 if role_name in role_names:
    #                     color_str += f" ({role_names[role_name]})\n"
    #                 else:
    #                     color_str += '\n'
    #             await hf.safe_send(ctx, color_str)
    #             return
    #         if role_name_in in ['test0', 'test1', 'test2', 'test3', 'test4', 'test5', 'test6', 'test7']:
    #             if not ctx.channel == colors_channel:
    #                 return
    #             role = discord.utils.get(ctx.guild.roles, name=role_name_in)
    #             if not role:
    #                 await hf.safe_send(ctx, f"{role_name_in} not found.")
    #                 return
    #             try:
    #                 color = discord.Color(int(color_in, 16))
    #             except ValueError:
    #                 await hf.safe_send(ctx, f"Invalid color code used.  You may only use numbers 0-9 and letters a-f.")
    #                 return
    #             await hf.safe_send(ctx, embed=discord.Embed(description=f"Changed the color of {role.mention} to {color_in}.",
    #                                                color=color))
    #             await role.edit(color=color)
    #
    # @color_change.command(name="save")
    # @hf.is_submod()
    # async def color_save(self, ctx):
    #     """Save the current color set"""
    #     config = self.bot.db['colors']
    #     color_str = ""
    #     colors_channel = self.bot.get_channel(COLOR_CHANNEL_ID)
    #     for role_name in ['test0', 'test1', 'test2', 'test3', 'test4', 'test5']:
    #         if not ctx.channel == colors_channel:
    #             return
    #         role = discord.utils.get(ctx.guild.roles, name=role_name)
    #         if not role:
    #             await hf.safe_send(ctx, f"{role_name} not found.")
    #             return
    #         color_str += f"{role.name}: #{role.color.r:02X},{role.color.g:02X},{role.color.b:02X}\n"
    #     config[str(len(config)+1)] = color_str
    #    #
    # @color_change.command(name="load")
    # @hf.is_submod()
    # async def color_load(self, ctx, index=None):
    #     try:
    #         config = self.bot.db['colors'][str(index)]
    #         new_colors = []
    #         for color_str in config.split('\n')[:-1]:
    #             new_colors.append(color_str.split('#')[1].replace(',', ''))
    #     except ValueError:
    #         await hf.safe_send(ctx, "Input a single number that you get from `;c list`.")
    #         return
    #     colors_channel = self.bot.get_channel(COLOR_CHANNEL_ID)
    #     role_names = ['test0', 'test1', 'test2', 'test3', 'test4', 'test5']
    #     for index in range(6):
    #         if not ctx.channel == colors_channel:
    #             return
    #         role = discord.utils.get(ctx.guild.roles, name=role_names[index])
    #         if not role:
    #             await hf.safe_send(ctx, f"{role_name} not found.")
    #             return
    #         color = discord.Color(int(new_colors[index], 16))
    #         await role.edit(color=color)
    #     await ctx.invoke(self.color_change)
    #
    # @color_change.command(name='list')
    # async def color_list(self, ctx):
    #     config = self.bot.db['colors']
    #     to_send = 'Saved configs:\n\n'
    #     for index in range(len(config)):
    #         to_send += f"〰〰({index+1})〰〰\n{config[str(index+1)]}\n"
    #     await hf.safe_send(ctx, to_send)

    @commands.Cog.listener()
    async def on_message(self, msg):
        if msg.author.bot:
            return

        # "Experimental global watch list"
        # if msg.author.id == 202979770235879427:
        #     channel = self.bot.get_channel(374489744974807040)
        #     await hf.safe_send(channel, f"Message by {msg.author.name} in {msg.channel.mention}:\n\n```{msg.content}```")

        """Messages/pings to Rai"""

        async def message_to_bot():
            if (msg.channel == msg.author.dm_channel and msg.author.id not in [202995638860906496, 414873201349361664]) \
                    or '270366726737231884' in msg.content:
                if isinstance(msg.channel, discord.DMChannel):
                    embed = hf.green_embed(f"DM from {msg.author.mention} "
                                           f"({msg.author.name}#{msg.author.discriminator}) - "
                                           f"[Jump URL]({msg.jump_url})")
                    async for message in msg.channel.history(limit=2):
                        if 'report' in message.content.casefold() and message.author == self.bot.user:
                            return
                else:
                    embed = hf.green_embed(f"Ping from {msg.author.mention} "
                                           f"({msg.author.name}#{msg.author.discriminator}) in {msg.channel.mention} "
                                           f"({msg.guild.name}) - [Jump URL]({msg.jump_url})")
                if msg.content:
                    embed.add_field(name="Text", value=msg.content[:1024])
                if msg.content[1024:]:
                    embed.add_field(name="Text pt. 2", value=msg.content[1024:])
                if msg.attachments:
                    for attachment in msg.attachments:
                        embed.add_field(name="Attachment", value=attachment.url)

                channel_id = str(msg.channel.id)
                length = len(channel_id)
                i = [channel_id[round(0 * length / 3): round(1 * length / 3)],
                     channel_id[round(1 * length / 3): round(2 * length / 3)],
                     channel_id[round(2 * length / 3): round(3 * length / 3)]]
                color = {'r': int(i[0]) % 255, 'g': int(i[1]) % 255, 'b': int(i[2]) % 255}
                embed.color = discord.Color.from_rgb(color['r'], color['g'], color['b'])

                spam_chan = self.bot.get_channel(RYRY_SPAM_CHAN)
                await spam_chan.send(f"{msg.channel.id} <@202995638860906496>", embed=embed)

        await message_to_bot()

        """Message as the bot"""

        async def message_as_bot():
            if isinstance(msg.channel, discord.DMChannel) \
                    and msg.author.id == self.bot.owner_id and msg.content[0:3] == 'msg':
                await self.bot.get_channel(int(msg.content[4:22])).send(str(msg.content[22:]))

        await message_as_bot()

        """Replace tatsumaki/nadeko serverinfo posts"""

        async def replace_tatsumaki_posts():
            if msg.content in ['t!serverinfo', 't!server', 't!sinfo', '.serverinfo', '.sinfo']:
                if msg.guild.id in [189571157446492161, 243838819743432704, 275146036178059265]:
                    new_ctx = await self.bot.get_context(msg)
                    await new_ctx.invoke(self.serverinfo)

        await replace_tatsumaki_posts()

        """Ping me if someone says my name"""

        async def mention_ping():
            cont = str(msg.content)
            if (
                    (
                            'ryry' in cont.casefold()
                            or ('ryan' in cont.casefold() and msg.guild != self.bot.spanServ)
                            or 'らいらい' in cont.casefold()
                            or 'ライライ' in cont.casefold()
                            or '来来' in cont.casefold()
                            or '雷来' in cont.casefold()
                    ) and
                    (not msg.author.bot or msg.author.id == 202995638860906496)
                    # checks to see if account is a bot account
            ):  # random sad face
                if 'aryan' in cont.casefold():  # why do people say this so often...
                    return
                else:
                    await self.bot.spamChan.send(
                        f'**By {msg.author.name} in {msg.channel.mention}** ({msg.channel.name}): '
                        f'\n{msg.content}'
                        f'\n{msg.jump_url} <@202995638860906496>'[:2000])

        await mention_ping()

        """Self mute"""
        if msg.author.id == self.bot.owner_id and self.bot.selfMute:
            try:
                await msg.delete()
            except discord.errors.NotFound:
                pass

        ##########################################

        if not msg.guild:  # all code after this has msg.guild requirement
            return

        ##########################################

        """check for servers of banned IDs"""
        async def check_guilds():
            if msg.guild.id == 257984339025985546:
                async def check_user(content):
                    bans_channel = msg.channel
                    re_result = re.findall('(?:^| |\n)(\d{17,22})', content)
                    users = []
                    if re_result:
                        for user_id in [int(user_id) for user_id in re_result]:
                            if user_id == 270366726737231884:
                                continue
                            user = self.bot.get_user(user_id)
                            if user:
                                users.append(user)
                    for user in users:
                        await hf.ban_check_servers(self.bot, bans_channel, user)

                await check_user(msg.content)
                for embed in msg.embeds:
                    if embed.description:
                        await check_user(embed.description)

        await check_guilds()

        """chinese server banned words"""
        words = ['动态网自由门', '天安門', '天安门', '法輪功', '李洪志', 'Free Tibet', 'Tiananmen Square',
                 '反右派鬥爭', 'The Anti-Rightist Struggle', '大躍進政策', 'The Great Leap Forward', '文化大革命',
                 '人權', 'Human Rights', '民運', 'Democratization', '自由', 'Freedom', '獨立', 'Independence']
        if msg.guild.id in [266695661670367232, 494502230385491978, 320439136236601344, 275146036178059265]:
            word_count = 0
            for word in words:
                if word in msg.content:
                    word_count += 1
                if word_count == 5:
                    mod_channel = self.bot.get_channel(self.bot.db['mod_channel'][str(msg.guild.id)])
                    log_channel = self.bot.get_channel(self.bot.db['bans'][str(msg.guild.id)]['channel'])
                    if datetime.utcnow() - msg.author.joined_at < timedelta(minutes=60):
                        try:
                            await msg.delete()
                        except discord.Forbidden:
                            await hf.safe_send(mod_channel,
                                               f"Rai is lacking the permission to delete messages for the Chinese "
                                               f"spam message.")
                        except discord.NotFound:
                            pass

                        # await msg.author.send("That message doesn't do anything to Chinese computers.  It doesn't "
                        #                       "get their internet shut down or get them arrested or anything.  "
                        #                       "It's just annoying, so please stop trying it.")
                        try:
                            await msg.author.ban(reason=f"*by* Rai\n"
                                                        f"**Reason: **Automatic ban: Chinese banned words spam\n"
                                                        f"{msg.content[:100]}")
                        except discord.Forbidden:
                            await hf.safe_send(mod_channel,
                                               f"I tried to ban someone for the Chinese spam message, but I lack "
                                               f"the permission to ban users.")

                        await hf.safe_send(log_channel, f"Banned {msg.author.name} for the banned words spam message."
                                                        f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                                        f"\n```{msg.content}"[:1850] + '```')

                        break
                    else:

                        await hf.safe_send(mod_channel,
                                           f"Warning: {msg.author.name} may have said the banned words spam message"
                                           f"\nMessage was posted in {msg.channel.mention}.  Message:"
                                           f"\n```{msg.content}"[:1995] + '```')
                        break

        """best sex dating"""

        async def spam_account_bans():
            words = ['amazingsexdating', 'bestdatingforall', 'nakedphotos.club', 'privatepage.vip', 'viewc.site']
            try:
                for word in words:
                    if word in msg.content:
                        time_ago = datetime.utcnow() - msg.author.joined_at
                        msg_text = f"Bot spam message in [{msg.guild.name}] - [{msg.channel.name}] by {msg.author.name}" \
                                   f" (joined {time_ago.seconds//3600}h {time_ago.seconds%3600//60}m ago [{time_ago}])" \
                                   f"```{msg.content}```"
                        await self.bot.get_user(self.bot.owner_id).send(msg_text)
                        if str(msg.author.guild.id) not in self.bot.db['auto_bans']:
                            return
                        if self.bot.db['auto_bans'][str(msg.author.guild.id)]['enable']:
                            if time_ago < timedelta(minutes=10) or \
                                    (msg.channel.id == 559291089018814464 and time_ago < timedelta(hours=5)):
                                if msg.author.id in [202995638860906496, 414873201349361664]:
                                    return
                                await msg.author.ban(reason=f'For posting spam link: {msg.content}',
                                                     delete_message_days=1)
                                self.bot.db['global_blacklist']['blacklist'].append(msg.author.id)
                                channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
                                emb = hf.red_embed(f"{msg.author.id} (automatic addition)")
                                emb.add_field(name="Reason", value=msg.content)
                                await hf.safe_send(channel, embed=emb)
                                created_ago = datetime.utcnow() - msg.author.created_at
                                joined_ago = datetime.utcnow() - msg.author.joined_at
                                message = f"**Banned a user for posting a {word} link.**" \
                                          f"\n**ID:** {msg.author.id}" \
                                          f"\n**Server:** {msg.author.guild.name}" \
                                          f"\n**Name:** {msg.author.name} {msg.author.mention}" \
                                          f"\n**Account creation:** {msg.author.created_at} " \
                                          f"({created_ago.days}d {created_ago.seconds//3600}h ago)" \
                                          f"\n**Server join:** {msg.author.joined_at} " \
                                          f"({joined_ago.days}d {joined_ago.seconds//3600}h ago)" \
                                          f"\n**Message:** {msg.content}"
                                emb2 = hf.red_embed(message)
                                emb2.color = discord.Color(int('000000', 16))
                                await self.bot.get_channel(329576845949534208).send(embed=emb2)
                                if str(msg.guild.id) in self.bot.db['bans']:
                                    if self.bot.db['bans'][str(msg.guild.id)]['channel']:
                                        channel_id = self.bot.db['bans'][str(msg.guild.id)]['channel']
                                        await self.bot.get_channel(channel_id).send(embed=emb2)

            except KeyError as e:
                print(f'>>passed for key error on amazingsexdating: {e}<<')
                pass
            except AttributeError as e:
                print(f'>>passed for attributeerror in amazingsexdating: {e}<<')
                pass

        await spam_account_bans()

        """mods ping on spanish server"""
        if msg.guild.id == 243838819743432704:
            if '<@&258806166770024449>' in msg.content:
                ch = self.bot.get_channel(563448201139716136)
                me = self.bot.get_user(202995638860906496)
                fourteen = self.bot.get_user(136444391777763328)
                em = discord.Embed(title=f"Mods Ping",
                                   description=f"From {msg.author.mention} ({msg.author.name}) "
                                               f"in {msg.channel.mention}\n{msg.jump_url}",
                                   color=discord.Color(int('FFAA00', 16)),
                                   timestamp=datetime.utcnow())
                em.add_field(name="Content", value=f"{msg.content}\n⁣".replace('<@&258806166770024449>', ''))
                await ch.send(embed=em)
                await me.send(embed=em)
                await fourteen.send(embed=em)

        """Replace .mute on spanish server"""
        if msg.guild.id == 243838819743432704:
            if msg.content.startswith('.mute'):
                ctx = await self.bot.get_context(msg)
                if not hf.submod_check(ctx):
                    return
                args = msg.content.split()[1:]
                if len(args) == 1:
                    await ctx.invoke(self.bot.get_command('mute'), args[0])
                elif len(args) > 1:
                    await ctx.invoke(self.bot.get_command('mute'), args[0], member=' '.join(args[1:]))
                else:
                    await hf.safe_send(ctx, "Use `;mute` instead")

        """super_watch"""
        try:
            if msg.author.id in self.bot.db['super_watch'][str(msg.guild.id)]['users']:
                channel = self.bot.get_channel(self.bot.db['super_watch'][str(msg.guild.id)]['channel'])
                await hf.safe_send(channel,
                                   f"<#{msg.channel.id}> Message from super_watch user {msg.author.name}: "
                                   f"\n{msg.content}")
        except KeyError:
            pass

        """Message counting"""

        # stats:
        # 	guild1:
        # 		enable = True/False
        # 		messages (for ,u):
        # 			{5/6/2019:
        # 				{user_id1:
        #                   emoji: {emoji1: 1, emoji2: 3}
        #                   lang: {'eng': 25, 'sp': 30}
        # 					channel1: 30,
        # 					channel2: 20
        # 				user_id2:
        #                   emoji: {emoji1: 1, emoji2: 3}
        #                   lang: {'eng': 25, 'sp': 30}
        # 					channel1: 40,
        # 					channel2: 10
        # 				...}
        # 			5/5/2019:
        # 				{user_id1:
        #                   emoji: {emoji1: 1, emoji2: 3}
        #                   lang: {'eng': 25, 'sp': 30}
        # 					channel1: 30,
        # 					channel2: 20
        # 				user_id2:
        #                   emoji: {emoji1: 1, emoji2: 3}
        #                   lang: {'eng': 25, 'sp': 30}
        # 					channel1: 40,
        # 					channel2: 10
        # 				...}
        # 			...
        def msg_count():
            if msg.author.bot:
                return
            if str(msg.guild.id) not in self.bot.stats:
                return
            if not self.bot.stats[str(msg.guild.id)]['enable']:
                return

            config = self.bot.stats[str(msg.guild.id)]
            date_str = datetime.utcnow().strftime("%Y%m%d")
            if date_str not in config['messages']:
                config['messages'][date_str] = {}
            today = config['messages'][date_str]
            author = str(msg.author.id)
            channel = str(msg.channel.id)

            # emojis
            emojis = re.findall(':([A-Za-z0-9\_]+):', msg.content)
            for character in msg.content:
                if hf.is_emoji(character):
                    emojis.append(character)
                if hf.is_ignored_emoji(character) and character not in self.ignored_characters:
                    self.ignored_characters.append(character)

            # languages
            lang_used = None
            try:
                lang_used = tb(hf.rem_emoji_url(msg)).detect_language()
            except textblob.exceptions.TranslatorError:
                pass

            today.setdefault(author, {})
            today[author][channel] = today[author].get(channel, 0) + 1
            today[author].setdefault('emoji', {})
            for emoji in emojis:
                if emoji in ['、']:
                    continue
                today[author]['emoji'][emoji] = today[author]['emoji'].get(emoji, 0) + 1
            if lang_used:
                today[author].setdefault('lang', {})
                today[author]['lang'][lang_used] = today[author]['lang'].get(lang_used, 0) + 1

        msg_count()

        """Ultra Hardcore"""
        await hf.uhc_check(msg)

        """Chinese server hardcore mode"""
        if msg.guild.id == 266695661670367232:
            if '*' not in msg.content and msg.channel.id not in self.bot.db['hardcore']["266695661670367232"][
                'ignore']:
                if len(msg.content) > 3:
                    try:
                        ROLE_ID = self.bot.db['hardcore'][str(msg.guild.id)]['role']
                        role = msg.guild.get_role(ROLE_ID)
                    except KeyError:
                        return
                    except AttributeError:
                        return
                    if not hasattr(msg.author, 'roles'):
                        return
                    if role in msg.author.roles:
                        learning_eng = msg.guild.get_role(266778623631949826)
                        ratio = hf.jpenratio(msg)
                        if ratio is not None:
                            if learning_eng in msg.author.roles:
                                if ratio < .55:
                                    try:
                                        await msg.delete()
                                    except discord.errors.NotFound:
                                        pass
                                    if len(msg.content) > 30:
                                        await hf.long_deleted_msg_notification(msg)
                            else:
                                if ratio > .45:
                                    try:
                                        await msg.delete()
                                    except discord.errors.NotFound:
                                        pass
                                    if len(msg.content) > 60:
                                        await hf.long_deleted_msg_notification(msg)

        """Spanish server hardcore"""

        async def spanish_server_hardcore():
            if msg.guild.id == 243838819743432704 and '*' not in msg.content and len(msg.content):
                if msg.content[0] != '=' and len(msg.content) > 3:
                    if msg.channel.id not in self.bot.db['hardcore']['243838819743432704']['ignore']:
                        role = msg.guild.get_role(526089127611990046)
                        if role in msg.author.roles:
                            learning_eng = msg.guild.get_role(247021017740869632)
                            learning_sp = msg.guild.get_role(297415063302832128)
                            try:
                                i_see = hf.rem_emoji_url(msg)
                                lang_used = tb(i_see).detect_language()
                            except textblob.exceptions.TranslatorError:
                                return
                            if learning_eng in msg.author.roles:  # learning English, delete all Spanish
                                if lang_used == 'es':
                                    try:
                                        await msg.delete()
                                    except discord.errors.NotFound:
                                        return
                                    if len(msg.content) > 30:
                                        await hf.long_deleted_msg_notification(msg)
                            elif learning_sp in msg.author.roles:  # learning Spanish, delete all English
                                if lang_used == 'en':
                                    try:
                                        await msg.delete()
                                    except discord.errors.NotFound:
                                        return
                                    if len(msg.content) > 30:
                                        await hf.long_deleted_msg_notification(msg)
                            else:
                                try:
                                    await msg.author.send("You have hardcore enabled but you don't have the proper "
                                                          "learning role.  Please attach either 'Learning Spanish' or "
                                                          "'Learning English' to properly use hardcore mode, or take "
                                                          "off hardcore mode using the reactions in the server rules "
                                                          "page")
                                except discord.errors.Forbidden:
                                    pass

        await spanish_server_hardcore()

    @commands.command(aliases=['emojis', 'emoji'])
    @commands.bot_has_permissions(embed_links=True)
    async def emotes(self, ctx, args=None):
        """Shows top emojis usage of the server.  Type `;emojis` to display top 25, and type `;emojis -a` to show all
        emojis. Type `;emojis -l` to show least used emojis."""
        if str(ctx.guild.id) not in self.bot.stats:
            return
        config = self.bot.stats[str(ctx.guild.id)]['messages']
        emojis = {}
        for date in config:
            for user_id in config[date]:
                for emoji in config[date][user_id]['emoji']:
                    if emoji in emojis:
                        emojis[emoji] += config[date][user_id]['emoji'][emoji]
                    else:
                        emojis[emoji] = config[date][user_id]['emoji'][emoji]

        emoji_dict = {emoji.name: emoji for emoji in ctx.guild.emojis}
        msg = 'Top Emojis:\n'
        if args == '-s':
            for emoji in emojis:
                print(emoji)
                if emoji not in emoji_dict:
                    continue
                emoji_obj = emoji_dict[emoji]
                x = datetime.utcnow() - emoji_obj.created_at
                if x < timedelta(days=30):
                    emojis[emoji] = int(emojis[emoji] * 30 / (x.days + 1))
            args = '-a'
            msg = 'Scaled Emoji Counts (last 30 days, emojis created in the last 30 days have ' \
                  'numbers scaled to 30 days):\n'
        top_emojis = sorted(list(emojis.items()), key=lambda x: x[1], reverse=True)

        saved_msgs = []
        fields_count = 0

        if args == '-a':
            for emoji in top_emojis:
                if emoji[0] in emoji_dict:
                    emoji_obj = emoji_dict[emoji[0]]
                    addition = f"{str(emoji_obj)}: {emoji[1]}\n"
                    if len(msg + addition) < 2000:
                        msg += addition
                    else:
                        saved_msgs.append(msg)
                        msg = addition
            if saved_msgs:
                if saved_msgs[-1] != msg:
                    saved_msgs.append(msg)
                for msg in saved_msgs:
                    await hf.safe_send(ctx, msg)
            else:
                await hf.safe_send(ctx, msg)

        elif args == '-l':
            emb = hf.red_embed("Least Used Emojis (last 30 days)")
            for emoji in top_emojis[::-1]:
                if fields_count < 25:
                    if emoji[0] in emoji_dict:
                        emoji_obj = emoji_dict[emoji[0]]
                        fields_count += 1
                        emb.add_field(name=f"{fields_count}) {str(emoji_obj)}", value=emoji[1])
                else:
                    break
            await hf.safe_send(ctx, embed=emb)

        else:
            emb = hf.green_embed("Most Used Emojis (last 30 days)")
            for emoji in top_emojis:
                if fields_count < 25:
                    if emoji[0] in emoji_dict:
                        emoji_obj = emoji_dict[emoji[0]]
                        emb.add_field(name=f"{fields_count + 1}) {str(emoji_obj)}", value=emoji[1])
                        fields_count += 1
                else:
                    break
            await hf.safe_send(ctx, embed=emb)

    @commands.command(aliases=['git'])
    @commands.bot_has_permissions(send_messages=True)
    async def github(self, ctx):
        """Gives my github page"""
        await hf.safe_send(ctx, 'https://github.com/ryry013/Rai')

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def punch(self, ctx, user: discord.Member = None):
        """A punch command I made as a test"""
        if not user:
            user = ctx.author
        await hf.safe_send(ctx, "ONE PUNCH! And " + user.mention + " is out! ლ(ಠ益ಠლ)")

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def ping(self, ctx, x=4):
        """sends back 'hello'"""
        await hf.safe_send(ctx, str(round(self.bot.latency, x)) + 's')

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def invite(self, ctx):
        """Gives an invite to bring this bot to your server"""
        await hf.safe_send(ctx,
                           discord.utils.oauth_url(self.bot.user.id,
                                                   permissions=discord.Permissions(permissions=27776)))

    @commands.group(invoke_without_command=True)
    @commands.bot_has_permissions(send_messages=True)
    async def report(self, ctx, *, user=None):
        """Make a report to the mods"""
        if isinstance(ctx.channel, discord.DMChannel):
            return
        guild_id = str(ctx.guild.id)
        if guild_id not in self.bot.db['report']:
            await hf.safe_send(ctx, f"This server has not run the setup for the report function yet.  Please type "
                                    f"`;report setup`.")
            return
        config = self.bot.db['report'][guild_id]
        report_room = self.bot.get_channel(config['channel'])

        if user:
            user = await hf.member_converter(ctx, user)
            if not user:
                if not hf.admin_check(ctx):
                    await hf.safe_send(ctx,
                                       "You shouldn't type the report into the channel.  Just type `;report` and a menu "
                                       "will help you.")
                else:
                    await hf.safe_send(ctx,
                                       "I couldn't find that user.  Please try again, or type just `;report` if you want to"
                                       " make your own report")
                return
        else:
            user = ctx.author

        report_text = [
            # [0]: when the user first enters the module
            f"Welcome to the reporting module.  You're about to make a report to the mods of the "
            f"{ctx.guild.name} server.  Please select one of the following options for your report.\n\n"
            f"1) Send a report to the mods.\n"
            f"2) Send an anonymous report to the mods.\n"
            f"3) Talk with the mods.\n"
            f"4) Cancel",

            # [1]: user chooses option 1: anonymous report
            "Please type your report in one message below.  Make sure to include any relevant information, such as "
            "who the report is about, which channel they did whatever you're reporting about was in, and any "
            "other users involved.",

            # [2]: finishes anonymous report
            "Thank you for your report.  The mods have been notified, and your name is anonymous.",

            # [3]: user chooses option 2: report room
            f".\n\n\n\n\n__Please go here__: {report_room.mention}\n"
            f"In ten seconds, I'll send a welcome message there.",

            # [4]: initial ping to mods in report room
            f"{user.name} - This user has entered the report room.  If they don't "
            f"come to this channel in the next ten seconds, they will not be able to "
            f"see the following message and might be confused as to what's happening. @here",

            # [5]: entry message in report room
            f"Welcome to the report room {user.mention}.  Only the mods can read your messages here, so you"
            f" can now make your report.  When you are finished, type `;report done` and a log of this conversation "
            f"will be sent to you.  Please ping one of the mods you see online or if no one responds to you.",

            # [6]: a mod requesting a user in the report room
            f"Your presence has been requested in {report_room.mention}.  There should be a "
            f"welcome message there explaining what is happening, but you might not see it so "
            f"it might be a blank channel.  "
            f"\n\n\n  Please go here within 10 seconds of this message: {report_room.mention}.  "
            f"\n\n\n  If you missed the 10 second window, that's ok.  The channel will be blank, but it's about "
            f"this: in this channel, only the mods can see your messages, and no other users will "
            f"ever be able to see what you have typed in the past if they too join the "
            f"channel.  At the end, a log of the chat will be sent to you.",

            # [7]: message to the mods that someone is on the waitlist
            f'The user {user.mention} has tried to access the report room, but was put on '
            f'the wait list because someone else is currently using it.',

            # [8]: initial ping to user
            f'Please come to this channel {user.mention}'
        ]

        if user != ctx.author and hf.admin_check(ctx):  # if the mods called in a user
            await self.report_room(ctx, config, user, report_text, True)
            return

        try:
            await ctx.message.delete()
        except discord.errors.Forbidden:
            await report_room.send(f"I tried to delete the invocation for a ;report in {ctx.channel.mention} but I "
                                   f"lacked the `Manage Messages` permission so I could not.  Please delete"
                                   f"the `;report` message that the user sent to maintain their privacy.")

        reaction = await self.report_options(ctx, report_text)  # presents users with options for what they want to do
        if not reaction:
            return

        if str(reaction.emoji) == "1⃣":  # Send a report
            await self.report_room(ctx, config, ctx.author, report_text)

        if str(reaction.emoji) == '2⃣':  # Send an anonymous report
            await self.anonymous_report(ctx, report_text)

        if str(reaction.emoji) == "3⃣":  # Talk to the mods
            await self.report_room(ctx, config, ctx.author, report_text)

        if str(reaction.emoji) == '4⃣':  # Cancel
            await hf.safe_send(ctx.author, 'Understood.  Have a nice day!')
            return

    @report.command(name='setup')
    @hf.is_admin()
    @commands.bot_has_permissions(send_messages=True)
    async def report_setup(self, ctx):
        """Sets the channel"""
        perms = ctx.channel.permissions_for(ctx.me)
        if not perms.read_messages or not perms.read_message_history or not perms.manage_roles:
            await ctx.message.add_reaction('\N{CROSS MARK}')
            try:
                await hf.safe_send(ctx, "I need permissions for reading messages, reading message history, and "
                                        "managing either channel permissions or server roles.  Please check these")
            except discord.errors.Forbidden:
                await hf.safe_send(ctx.author, f"Rai lacks the permission to send messages in {ctx.channel.mention}.")
            return

        guild_id = str(ctx.guild.id)
        if guild_id in self.bot.db['report']:
            self.bot.db['report'][guild_id]['channel'] = ctx.channel.id
            await hf.safe_send(ctx, f"Successfully set the report room channel to {ctx.channel.mention}.")
        else:
            self.bot.db['report'][guild_id] = {'channel': ctx.channel.id,
                                               'current_user': None,
                                               'waiting_list': [],
                                               'entry_message': None}
            await hf.safe_send(ctx, f"Initial setup for report room complete.  The report room channel has been set to "
                                    f"{ctx.channel.mention}.")

    @report.command()
    async def done(self, ctx):
        """Use this when a report is finished in the report room"""
        try:
            config = self.bot.db['report'][str(ctx.guild.id)]
            report_room = ctx.bot.get_channel(config['channel'])
        except KeyError:
            return
        if not config['current_user']:
            return
        if ctx.channel != report_room:
            return

        user = ctx.guild.get_member(config['current_user'])
        start_message = await ctx.channel.fetch_message(config['entry_message'])
        config['current_user'] = None
        config['entry_message'] = None
        await report_room.set_permissions(user, overwrite=None)

        message_log = 'Start of log:\n'
        async for message in ctx.channel.history(limit=None, after=start_message):
            next_line = f'**__{message.author}:__** {message.content} \n'
            if len(message_log + next_line) > 2000:
                await user.send(message_log)
                message_log = next_line
            else:
                message_log += next_line
        await user.send(message_log)

        await report_room.send('Session closed, and a log has been sent to the user')

        if config['waiting_list']:
            waiting_list = config['waiting_list']
            for member_id in waiting_list:
                if config['current_user']:
                    break
                member = ctx.guild.get_member(member_id)
                msg = 'The report room is now open.  Try sending `;report` to me again. If you ' \
                      'wish to be removed from the waiting list, please react with the below emoji.'
                waiting_msg = await member.send(msg)
                await waiting_msg.add_reaction('🚫')
                asyncio.sleep(10)

    @report.command()
    @hf.is_admin()
    async def check_waiting_list(self, ctx):
        """Checks who is on the waiting list for the report room"""
        guild_id = str(ctx.guild.id)
        if guild_id not in self.bot.db['report']:
            return
        config = self.bot.db['report'][guild_id]

        message = 'List of users on the waiting list: '
        if config['waiting_list']:
            members = [ctx.guild.get_member(user).mention for user in config['waiting_list']]
            message = message + ', '.join(members)
        else:
            message = 'There are no users on the waiting list'
        await hf.safe_send(ctx, message)

    @report.command()
    @hf.is_admin()
    async def clear_waiting_list(self, ctx):
        """Clears the waiting list for the report room"""
        guild_id = str(ctx.guild.id)
        if guild_id not in self.bot.db['report']:
            return
        config = self.bot.db['report'][guild_id]

        if config['waiting_list']:
            config['waiting_list'] = []
            hf.dump_json()
            await hf.safe_send(ctx, 'Waiting list cleared')
        else:
            await hf.safe_send(ctx, 'There was no one on the waiting list.')

    @report.command(name="reset")
    @hf.is_admin()
    async def report_reset(self, ctx):
        """Manually reset the report module in case of some bug"""
        try:
            config = self.bot.db['report'][str(ctx.guild.id)]
        except KeyError:
            return
        config['current_user'] = config['entry_message'] = None
        config['waiting_list'] = []
        hf.dump_json()
        await hf.safe_send(ctx,
                           f"The report module has been reset on this server.  Check the permission overrides on the "
                           f"report channel to make sure there are no users left there.")

    @report.command(name="anonymous_ping")
    @hf.is_admin()
    async def report_anonymous_ping(self, ctx):
        """Enable/disable a `@here` ping for if someone makes an anonymous report"""
        try:
            config = self.bot.db['report'][str(ctx.guild.id)]
        except KeyError:
            return
        config['anonymous_ping'] = not config['anonymous_ping']
        if config['anonymous_ping']:
            await hf.safe_send(ctx, "Enabled pinging for anonymous reports.  I'll add a `@here` ping to the next one.")
        else:
            await hf.safe_send(ctx, "Disabled pinging for anonymous reports.")

    @report.command(name="room_ping")
    @hf.is_admin()
    async def report_room_ping(self, ctx):
        """Enable/disable a `@here` ping for if someone enters the report room"""
        try:
            config = self.bot.db['report'][str(ctx.guild.id)]
        except KeyError:
            return
        config['room_ping'] = not config['room_ping']
        if config['room_ping']:
            await hf.safe_send(ctx, "Enabled pinging for when someone enters the report room.  "
                                    "I'll add a `@here` ping to the next one.")
        else:
            await hf.safe_send(ctx, "Disabled pinging for the report room.")

    @staticmethod
    async def report_options(ctx, report_text):
        """;report: Presents a user with the options of making an anonymous report or entering the report room"""

        def check(reaction, user):
            return user == ctx.author and (str(reaction.emoji) in "1⃣2⃣3⃣4⃣")  # 4⃣

        try:
            msg = await hf.safe_send(ctx.author, report_text[0])  # when the user first enters the module
        except discord.errors.Forbidden:
            await hf.safe_send(ctx, f"I'm unable to complete your request, as the user does not have PMs "
                                    f"from server members enabled.")
            ctx.bot.db['report'][str(ctx.guild.id)]['current_user'] = None
            hf.dump_json()
            return

        await msg.add_reaction("1⃣")  # Send a report (report room)
        await msg.add_reaction('2⃣')  # Send an anonymous report
        await msg.add_reaction('3⃣')  # Talk to the mods (report room)
        await msg.add_reaction('4⃣')  # cancel

        try:
            reaction, user = await ctx.bot.wait_for('reaction_add', timeout=300.0, check=check)
            return reaction
        except asyncio.TimeoutError:
            await hf.safe_send(ctx.author, "Module timed out.")
            return

    @staticmethod
    async def anonymous_report(ctx, report_text):
        """;report: The code for an anonymous report submission"""
        await hf.safe_send(ctx.author, report_text[1])  # Instructions for the anonymous report

        def check(m):
            return m.author == ctx.author and isinstance(m.channel, discord.channel.DMChannel)

        try:
            msg = await ctx.bot.wait_for('message', timeout=300.0, check=check)
            await hf.safe_send(ctx.author, report_text[2])  # "thank you for the report"
            mod_channel = ctx.bot.get_channel(ctx.bot.db['mod_channel'][str(ctx.guild.id)])
            initial_msg = 'Received report from a user: \n\n'
            if ctx.bot.db['report'][str(ctx.guild.id)].setdefault('anonymous_ping', False):
                initial_msg = '@here ' + initial_msg
            await hf.safe_send(mod_channel, initial_msg)
            await hf.safe_send(mod_channel, msg.content)
            return
        except asyncio.TimeoutError:
            await hf.safe_send(ctx.author, f"Module timed out.")
            return

    @staticmethod
    async def report_room(ctx, config, user, report_text, from_mod=False):
        report_room = ctx.bot.get_channel(config['channel'])
        if config['current_user']:  # if someone is in the room already
            config['waiting_list'].append(user.id)
            msg = f"Sorry but someone else is using the room right now.  I'll message you when it's ope" \
                  f"n in the order that I received requests.  You are position " \
                  f"{config['waiting_list'].index(user.id)+1} on the list"
            await user.send(msg)  # someone is in the room, you've been added to waiting list
            try:
                mod_channel = ctx.guild.get_channel(ctx.cog.bot.db['mod_channel'][str(ctx.guild.id)])
                await hf.safe_send(mod_channel,
                                   f"{user.mention} ({user.name}) tried to enter the report room, but someone "
                                   f"else is already in it.  Try typing `;report done` in the report room, "
                                   f"and type `;report check_waiting_list` to see who is waiting.")
            except KeyError:
                await report_room.send(f"Note to the mods: I tried to send you a notification about the report room, "
                                       f"but you haven't set a mod channel yet.  Please type `;set_mod_channel` in "
                                       f"your mod channel.")
            return
        if user.id in config['waiting_list']:
            config['waiting_list'].remove(user.id)
        config['current_user'] = user.id
        if report_room.permissions_for(user).read_messages or not config.setdefault('room_ping', False):
            initial_msg = report_text[4][:-5]
        else:
            initial_msg = report_text[4]
        await report_room.set_permissions(user, read_messages=True)

        if from_mod:
            try:
                await user.send(report_text[6])
            except discord.errors.Forbidden:
                await hf.safe_send(ctx, f"I'm unable to complete your request, as the user does not have PMs "
                                        f"from server members enabled.")
                ctx.bot.db['report'][str(ctx.guild.id)]['current_user'] = None
                hf.dump_json()
                return
        else:
            await user.send(report_text[3])  # please go to the report room

        msg = await report_room.send(initial_msg)  # initial msg to mods
        await report_room.send(report_text[8])
        config['entry_message'] = msg.id
        await asyncio.sleep(10)
        await report_room.send(report_text[5])  # full instructions text in report room

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user: discord.Member):
        """removes people from the waiting list for ;report if they react with '🚫' to a certain message"""
        if reaction.emoji == '🚫':
            if user == self.bot.user:
                return
            if reaction.message.channel == user.dm_channel:
                config = self.bot.db['report']
                for guild_id in config:
                    if user.id in config[guild_id]['waiting_list']:
                        config[guild_id]['waiting_list'].remove(user.id)
                        await user.send("Understood.  You've been removed from the waiting list.  Have a nice day.")

                        mod_channel = self.bot.get_channel(self.bot.db["mod_channel"][guild_id])
                        msg_to_mod_channel = f"The user {user.name} was previously on the wait list for the " \
                                             f"report room but just removed themselves."
                        await hf.safe_send(mod_channel, msg_to_mod_channel)
                        return
                await user.send("You aren't on the waiting list.")

        if str(reaction.emoji) in '🗑❌':
            if reaction.message.author == self.bot.user:
                await reaction.message.delete()

        if user.bot:
            return
        if str(user.guild.id) not in self.bot.stats:
            return
        if not self.bot.stats[str(user.guild.id)]['enable']:
            return

        try:
            emoji = reaction.emoji.name
        except AttributeError:
            emoji = reaction.emoji
        config = self.bot.stats[str(user.guild.id)]
        date_str = datetime.utcnow().strftime("%Y%m%d")
        if date_str not in config['messages']:
            config['messages'][date_str] = {}
        today = config['messages'][date_str]
        today[str(user.id)].setdefault('emoji', {})
        today[str(user.id)]['emoji'][emoji] = today[str(user.id)]['emoji'].get(emoji, 0) + 1

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        if payload.emoji.name == '⬆':
            if payload.channel_id == BLACKLIST_CHANNEL_ID:  # votes on blacklist
                channel = self.bot.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
                ctx = await self.bot.get_context(message)
                ctx.author = self.bot.get_user(payload.user_id)
                ctx.reacted_user_id = payload.user_id
                user_id = message.embeds[0].title.split(' ')[0]
                config = self.bot.db['global_blacklist']
                if user_id not in config['votes2']:
                    return
                if str(payload.user_id) in config['residency']:
                    voting_guild_id = config['residency'][str(payload.user_id)]
                    if voting_guild_id not in config['votes2'][user_id]['votes']:
                        if message.embeds[0].color != discord.Color(int('ff0000', 16)):
                            await ctx.invoke(self.blacklist_add, args=user_id)
                else:
                    await hf.safe_send(ctx.author,
                                       "Please claim residency on a server first with `;global_blacklist residency`")
                    return

            elif payload.channel_id == BANS_CHANNEL_ID:
                channel = self.bot.get_channel(BANS_CHANNEL_ID)
                message = await channel.fetch_message(payload.message_id)
                ctx = await self.bot.get_context(message)
                ctx.author = self.bot.get_user(payload.user_id)
                ctx.reacted_user_id = payload.user_id
                user_id = re.search('\((\d{17,22})\)', message.embeds[0].description).group(1)
                try:
                    reason = re.search('\*\*Reason\*\*: (.*)$', message.embeds[0].description, flags=re.S).group(1)
                except AttributeError:
                    return
                config = self.bot.db['global_blacklist']
                if str(payload.user_id) in config['residency']:
                    if user_id not in config['blacklist'] and str(user_id) not in config['votes2']:
                        await ctx.invoke(self.blacklist_add, args=f"{user_id} {reason}")
                else:
                    await hf.safe_send(ctx.author, "Please claim residency on a server first with `;gbl residency`")
                    return

        if payload.emoji.name == '✅':  # captcha
            if str(payload.guild_id) in self.bot.db['captcha']:
                config = self.bot.db['captcha'][str(payload.guild_id)]
                if config['enable']:
                    guild = self.bot.get_guild(payload.guild_id)
                    role = guild.get_role(config['role'])
                    if payload.message_id == config['message']:
                        try:
                            await guild.get_member(payload.user_id).add_roles(role)
                            return
                        except discord.errors.Forbidden:
                            await self.bot.get_user(202995638860906496).send(
                                'on_raw_reaction_add: Lacking `Manage Roles` permission'
                                f' <#{payload.guild_id}>')

        if payload.guild_id == 266695661670367232:  # chinese
            if payload.emoji.name in '🔥📝🖋🗣🎙':
                roles = {'🔥': 496659040177487872,
                         '📝': 509446402016018454,
                         '🗣': 266713757030285313,
                         '🖋': 344126772138475540,
                         '🎙': 454893059080060930}
                server = 0
            else:
                return
        elif payload.guild_id == 243838819743432704:  # spanish/english
            if payload.emoji.name in '🎨🐱🐶🎮table👪🎥❗👚💻📔✏🔥📆':
                roles = {'🎨': 401930364316024852,
                         '🐱': 254791516659122176,
                         '🐶': 349800774886359040,
                         '🎮': 343617472743604235,
                         '👪': 402148856629821460,
                         '🎥': 354480160986103808,
                         '👚': 376200559063072769,
                         '💻': 401930404908630038,
                         '❗': 243859335892041728,
                         '📔': 286000427512758272,
                         '✏': 382752872095285248,
                         '🔥': 526089127611990046,
                         'table': 396080550802096128,
                         '📆': 555478189363822600}
                server = 1
            else:
                return
        else:
            return

        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)
        if not user.bot:
            try:
                config = self.bot.db['roles'][str(payload.guild_id)]
            except KeyError:
                return
            if server == 0:
                if payload.message_id != config['message']:
                    return
            elif server == 1:
                if payload.message_id != config['message1'] and payload.message_id != config['message2']:
                    return
            role = guild.get_role(roles[payload.emoji.name])
            try:
                await user.add_roles(role)
            except discord.errors.Forbidden:
                self.bot.get_user(202995638860906496).send(
                    'on_raw_reaction_add: Lacking `Manage Roles` permission'
                    f'<#{payload.guild_id}>')

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if not payload.guild_id:
            return
        if not payload.emoji.name:
            print(payload)
            print(payload.channel_id)
            print(payload.emoji)
        if payload.guild_id == 266695661670367232:  # chinese
            if payload.emoji.name in '🔥📝🖋🗣🎙':
                roles = {'🔥': 496659040177487872,
                         '📝': 509446402016018454,
                         '🗣': 266713757030285313,
                         '🖋': 344126772138475540,
                         '🎙': 454893059080060930}
                server = 0
            else:
                return
        elif payload.guild_id == 243838819743432704:  # spanish/english
            if payload.emoji.name in '🎨🐱🐶🎮table👪🎥❗👚💻📔✏🔥📆':
                roles = {'🎨': 401930364316024852,
                         '🐱': 254791516659122176,
                         '🐶': 349800774886359040,
                         '🎮': 343617472743604235,
                         '👪': 402148856629821460,
                         '🎥': 354480160986103808,
                         '👚': 376200559063072769,
                         '💻': 401930404908630038,
                         '❗': 243859335892041728,
                         '📔': 286000427512758272,
                         '✏': 382752872095285248,
                         '🔥': 526089127611990046,
                         'table': 396080550802096128,
                         '📆': 555478189363822600}
                server = 1
            else:
                return
        else:
            return
        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)
        if not user.bot:
            try:
                config = self.bot.db['roles'][str(payload.guild_id)]
            except KeyError:
                return
            if server == 0:
                if payload.message_id != config['message']:
                    return
            elif server == 1:
                if payload.message_id != config['message1'] and payload.message_id != config['message2']:
                    return
            role = guild.get_role(roles[payload.emoji.name])
            try:
                await user.remove_roles(role)
            except discord.errors.Forbidden:
                self.bot.get_user(202995638860906496).send(
                    'on_raw_reaction_remove: Lacking `Manage Roles` permission'
                    f'<#{payload.guild_id}>')

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def pencil(self, ctx):
        try:
            await ctx.author.edit(nick=ctx.author.display_name + '📝')
            await hf.safe_send(ctx,
                               "I've added 📝 to your name.  This means you wish to be corrected in your sentences")
        except discord.errors.Forbidden:
            await hf.safe_send(ctx, "I lack the permissions to change your nickname")
        except discord.errors.HTTPException:
            await ctx.message.add_reaction('💢')

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def eraser(self, ctx):
        try:
            await ctx.author.edit(nick=ctx.author.display_name[:-1])
            await ctx.message.add_reaction('◀')
        except discord.errors.Forbidden:
            await hf.safe_send(ctx, "I lack the permissions to change your nickname")

    @commands.command(aliases=['ryry'])
    @commands.bot_has_permissions(send_messages=True)
    async def ryan(self, ctx):
        """Posts a link to the help docs server for my bot"""
        await hf.safe_send(ctx, "You can find some shitty docs for how to use my bot here: "
                                "https://github.com/ryry013/Rai/blob/master/README.md \n"
                                "You can ask questions and find some further details here: https://discord.gg/7k5MMpr")

    @commands.command(aliases=[';p', ';s', ';play', ';skip', '_;', '-;', ')', '__;', '___;', ';leave', ';join',
                               ';l', ';q', ';queue', ';pause', ';volume', ';1', ';vol', ';np', ';list'], hidden=True)
    async def ignore_commands_list(self, ctx):
        pass

    @commands.command(aliases=['cl', 'checklanguage'])
    @commands.bot_has_permissions(send_messages=True)
    async def check_language(self, ctx, *, msg: str):
        """Shows what's happening behind the scenes for hardcore mode.  Will try to detect the language that your
        message was typed in, and display the results.  Note that this is non-deterministic code, which means
        repeated results of the same exact message might give different results every time."""
        stripped_msg = hf.rem_emoji_url(msg)
        if not stripped_msg:
            stripped_msg = ' '
        try:
            lang_result = tb(stripped_msg).detect_language()
        except textblob.exceptions.TranslatorError:
            lang_result = "There was an error detecting the languages"
        str = f"Your message:```{msg}```" \
              f"The message I see (no emojis or urls): ```{stripped_msg}```" \
              f"The language I detect: ```{lang_result}```" \
              f"If the first language is your native language, your message would be deleted"

        await hf.safe_send(ctx, str)

    def get_color_from_name(self, ctx):
        config = self.bot.db['questions'][str(ctx.channel.guild.id)]
        channel_list = sorted([int(channel) for channel in config])
        index = channel_list.index(ctx.channel.id) % 6
        # colors = ['00ff00', 'ff9900', '4db8ff', 'ff0000', 'ff00ff', 'ffff00'] below line is in hex
        colors = [65280, 16750848, 5093631, 16711680, 16711935, 16776960]
        return colors[index]

    async def add_question(self, ctx, target_message, title=None):
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        except KeyError:
            try:
                await hf.safe_send(ctx,
                                   f"This channel is not setup as a questions channel.  Run `;question setup` in the "
                                   f"questions channel to start setup.")
            except discord.Forbidden:
                await hf.safe_send(ctx.author, "Rai lacks permissions to send messages in that channel")
                return
            return
        if not title:
            title = target_message.content
        # for channel in self.bot.db['questions'][str(ctx.guild.id)]:
        # for question in self.bot.db['questions'][str(ctx.guild.id)][channel]:
        # question = self.bot.db['questions'][str(ctx.guild.id)][channel][question]
        # if (datetime.today() - datetime.strptime(question['date'], "%Y/%m/%d")).days >= 3:
        # log_channel = self.bot.get_channel(self.bot.db['questions']['channel']['log_channel'])
        # await hf.safe_send(log_channel, f"Closed question for being older than three days and unanswered")

        question_number = 1
        while str(question_number) in config['questions']:
            question_number += 1
        if question_number > 9:
            await hf.safe_send(ctx, f"Note, I've reached the maximum amount of open questions for reactions.  Try "
                                    f"running `;q list` and clearing out some old questions.")
        config['questions'][str(question_number)] = {}
        config['questions'][str(question_number)]['title'] = title
        config['questions'][str(question_number)]['question_message'] = target_message.id
        config['questions'][str(question_number)]['author'] = target_message.author.id
        config['questions'][str(question_number)]['command_caller'] = ctx.author.id
        config['questions'][str(question_number)]['date'] = date.today().strftime("%Y/%m/%d")

        log_channel = self.bot.get_channel(config['log_channel'])
        color = self.get_color_from_name(ctx)  # returns a RGB tuple unique to every username
        emb = discord.Embed(title=f"Question number: `{question_number}`",
                            description=f"Asked by {target_message.author.mention} ({target_message.author.name}) "
                                        f"in {target_message.channel.mention}",
                            color=discord.Color(color),
                            timestamp=datetime.utcnow())
        if len(f"{title}\n") > (1024 - len(target_message.jump_url)):
            emb.add_field(name=f"Question:", value=f"{title}"[:1024])
            if title[1024:]:
                emb.add_field(name=f"Question (cont.):", value=f"{title[1024:]}\n")
            emb.add_field(name=f"Jump Link to Question:", value=target_message.jump_url)
        else:
            emb.add_field(name=f"Question:", value=f"{title}\n{target_message.jump_url}")
        if ctx.author != target_message.author:
            emb.set_footer(text=f"Question added by {ctx.author.name}")
        try:
            log_message = await hf.safe_send(log_channel, embed=emb)
        except discord.errors.HTTPException as err:
            if err.status == 400:
                await hf.safe_send(ctx, "The question was too long")
            elif err.status == 403:
                await hf.safe_send(ctx, "I didn't have permissions to post in that channel")
            del (config['questions'][str(question_number)])
            return
        config['questions'][str(question_number)]['log_message'] = log_message.id
        number_map = {'1': '1\u20e3', '2': '2\u20e3', '3': '3\u20e3', '4': '4\u20e3', '5': '5\u20e3',
                      '6': '6\u20e3', '7': '7\u20e3', '8': '8\u20e3', '9': '9\u20e3'}
        if question_number < 10:
            try:
                await target_message.add_reaction(number_map[str(question_number)])
            except discord.errors.Forbidden:
                await hf.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")

        if target_message.author != ctx.author:
            msg_text = f"Hello, someone has marked one of your questions using my questions log feature.  It is now " \
                       f"logged in <#{config['log_channel']}>.  This will" \
                       f" help make sure you receive an answer.  When someone answers your question, please type " \
                       f"`;q a` to mark the question as answered.  Thanks!"
            await hf.safe_send(target_message.author, msg_text)

    @commands.group(invoke_without_command=True, aliases=['q'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def question(self, ctx, *, args):
        """A module for asking questions, put the title of your quesiton like `;question <title>`"""
        args = args.split(' ')
        if not args:
            msg = f"This is a module to help you ask your questions.  To ask a question, decide a title for your " \
                  f"question and type `;question <title>`.  For example, if your question is about the meaning " \
                  f"of a word in a sentence, you could format the command like `;question Meaning of <word> " \
                  f"in <sentence>`. Put that command in the questions channel and you're good to go!  " \
                  f"(Alias: `;q <title>`)"
            await hf.safe_send(ctx, msg)
            return

        try:  # there is definitely some text in the arguments
            target_message = await ctx.channel.fetch_message(int(args[0]))  # this will work if the first arg is an ID
            if len(args) == 1:
                title = target_message.content  # if there was no text after the ID
            else:
                title = ' '.join(args[1:])  # if there was some text after the ID
        except (discord.errors.NotFound, ValueError):  # no ID cited in the args
            target_message = ctx.message  # use the current message as the question link
            title = ' '.join(args)  # turn all of args into the title

        await self.add_question(ctx, target_message, title)

    @question.command(name='setup')
    @hf.is_admin()
    async def question_setup(self, ctx):
        """Use this command in your questions channel"""
        config = self.bot.db['questions'].setdefault(str(ctx.guild.id), {})
        if str(ctx.channel.id) in config:
            msg = await hf.safe_send(ctx, "This will reset the questions database for this channel.  "
                                          "Do you wish to continue?  Type `y` to continue.")
            try:
                await self.bot.wait_for('message', timeout=15.0, check=lambda m: m.content == 'y' and
                                                                                 m.author == ctx.author)
            except asyncio.TimeoutError:
                await msg.edit(content="Canceled...", delete_after=10.0)
                return
        msg_1 = await hf.safe_send(ctx,
                                   f"Questions channel set as {ctx.channel.mention}.  In the way I just linked this "
                                   f"channel, please give me a link to the log channel you wish to use for this channel.")
        try:
            msg_2 = await self.bot.wait_for('message', timeout=20.0, check=lambda m: m.author == ctx.author)
        except asyncio.TimeoutError:
            await msg_1.edit(content="Canceled...", delete_after=10.0)
            return

        try:
            log_channel_id = int(msg_2.content.split('<#')[1][:-1])
            log_channel = self.bot.get_channel(log_channel_id)
            if not log_channel:
                raise NameError
        except (IndexError, NameError):
            await hf.safe_send(ctx, f"Invalid channel specified.  Please start over and specify a link to a channel "
                                    f"(should highlight blue)")
            return
        config[str(ctx.channel.id)] = {'questions': {},
                                       'log_channel': log_channel_id}
        await hf.safe_send(ctx,
                           f"Set the log channel as {log_channel.mention}.  Setup complete.  Try starting your first "
                           f"question with `;question <title>` in this channel.")

    @question.command(aliases=['a'])
    async def answer(self, ctx, *, args=''):
        """Marks a question as answered, format: `;q a <question_id 0-9> [answer_id]`
        and has an optional answer_id field for if you wish to specify an answer message"""
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        except KeyError:
            await hf.safe_send(ctx,
                               f"This channel is not setup as a questions channel.  Please make sure you mark your "
                               f"question as 'answered' in the channel you asked it in.")
            return
        questions = config['questions']
        args = args.split(' ')

        async def self_answer_shortcut():
            for question_number in questions:
                if ctx.author.id == questions[question_number]['author']:
                    return int(question_number)
            await hf.safe_send(ctx, f"Only the asker of the question can omit stating the question ID.  You "
                                    f"must specify which question  you're trying to answer: `;q a <question id>`.  "
                                    f"For example, `;q a 3`.")
            return

        answer_message = answer_text = answer_id = None
        if args == ['']:  # if a user just inputs ;q a
            number = await self_answer_shortcut()
            answer_message = ctx.message
            answer_text = ''
            if not number:
                await hf.safe_send(ctx, f"Please enter the number of the question you wish to answer, like `;q a 3`.")
                return

        elif len(args) == 1:  # 1) ;q a <question ID>     2) ;q a <word>      3) ;q a <message ID>
            try:  # arg is a number
                single_arg = int(args[0])
            except ValueError:  # arg is a single text word
                number = await self_answer_shortcut()
                answer_message = ctx.message
                answer_text = args[0]
            else:
                if len(str(single_arg)) <= 2:  # ;q a <question ID>
                    number = args[0]
                    answer_message = ctx.message
                    answer_text = ctx.message.content
                elif 17 <= len(str(single_arg)) <= 21:  # ;q a <message ID>
                    try:
                        answer_message = await ctx.channel.fetch_message(single_arg)
                    except discord.errors.NotFound:
                        await hf.safe_send(ctx, f"I thought `{single_arg}` was a message ID but I couldn't find that "
                                                f"message in this channel.")
                        return
                    answer_text = answer_message.content[:900]
                    number = await self_answer_shortcut()
                else:  # ;q a <single word>
                    number = await self_answer_shortcut()
                    answer_message = ctx.message
                    answer_text = str(single_arg)

        else:  # args is more than one word
            number = args[0]
            try:  # example: ;q a 1 554490627279159341
                if 17 < len(args[1]) < 21:
                    answer_message = await ctx.channel.fetch_message(int(args[1]))
                    answer_text = answer_message.content[:900]
                else:
                    raise TypeError
            except (ValueError, TypeError):  # Supplies text answer:   ;q a 1 blah blah answer goes here
                answer_message = ctx.message
                answer_text = ' '.join(args[1:])
            except discord.errors.NotFound:
                await hf.safe_send(ctx,
                                   f"A corresponding message to the specified ID was not found.  `;q a <question_id> "
                                   f"<message id>`")
                return

        try:
            number = str(number)
            question = questions[number]
        except KeyError:
            await hf.safe_send(ctx,
                               f"Invalid question number.  Check the log channel again and input a single number like "
                               f"`;question answer 3`.  Also, make sure you're answering in the right channel.")
            return
        except Exception:
            await hf.safe_send(ctx, f"You've done *something* wrong... (´・ω・`)")
            raise

        try:
            log_channel = self.bot.get_channel(config['log_channel'])
            log_message = await log_channel.fetch_message(question['log_message'])
        except discord.errors.NotFound:
            log_message = None
            await hf.safe_send(ctx, f"Message in log channel not found.  Continuing code.")

        try:
            question_message = await ctx.channel.fetch_message(question['question_message'])
            if ctx.author.id not in [question_message.author.id, question['command_caller']] \
                    and not hf.submod_check(ctx):
                await hf.safe_send(ctx, f"Only mods or the person who asked/started the question "
                                        f"originally can mark it as answered.")
                return
        except discord.errors.NotFound:
            if log_message:
                await log_message.delete()
            del questions[number]
            msg = await hf.safe_send(ctx, f"Original question message not found.  Closing question")
            await asyncio.sleep(5)
            await msg.delete()
            try:
                await ctx.message.delete()
            except discord.NotFound:
                pass
            return

        if log_message:
            emb = log_message.embeds[0]
            if answer_message.author != question_message.author:
                emb.description += f"\nAnswered by {answer_message.author.mention} ({answer_message.author.name})"
            emb.title = "ANSWERED"
            emb.color = discord.Color.default()
            if not answer_text:
                answer_text = ''
            emb.add_field(name=f"Answer: ",
                          value=answer_text + '\n' + answer_message.jump_url)
            await log_message.edit(embed=emb)

        try:
            question_message = await ctx.channel.fetch_message(question['question_message'])
            for reaction in question_message.reactions:
                if reaction.me:
                    try:
                        await question_message.remove_reaction(reaction.emoji, self.bot.user)
                    except discord.errors.Forbidden:
                        await hf.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")
        except discord.errors.NotFound:
            msg = await hf.safe_send(ctx, "That question was deleted")
            await log_message.delete()
            await asyncio.sleep(5)
            await msg.delete()
            await ctx.message.delete()

        try:
            del (config['questions'][number])
        except KeyError:
            pass
        if ctx.message:
            try:
                await ctx.message.add_reaction('\u2705')
            except discord.errors.Forbidden:
                await hf.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")
            except discord.NotFound:
                pass

    @question.command(aliases=['reopen', 'bump'])
    @hf.is_admin()
    async def open(self, ctx, message_id):
        """Reopens a closed question, point message_id to the log message in the log channel"""
        config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        for question in config['questions']:
            if int(message_id) == config['questions'][question]['log_message']:
                question = config['questions'][question]
                break
        log_channel = self.bot.get_channel(config['log_channel'])
        try:
            log_message = await log_channel.fetch_message(int(message_id))
        except discord.errors.NotFound:
            await hf.safe_send(ctx, f"Specified log message not found")
            return
        emb = log_message.embeds[0]
        if emb.title == 'ANSWERED':
            emb.description = emb.description.split('\n')[0]
            try:
                question_message = await ctx.channel.fetch_message(int(emb.fields[0].value.split('/')[-1]))
            except discord.errors.NotFound:
                await hf.safe_send(ctx, f"The message for the original question was not found")
                return
            await self.add_question(ctx, question_message, question_message.content)
        else:
            new_log_message = await hf.safe_send(log_channel, embed=emb)
            question['log_message'] = new_log_message.id
        await log_message.delete()

    @question.command(name='list')
    async def question_list(self, ctx):
        """Shows a list of currently open questions"""
        try:
            config = self.bot.db['questions'][str(ctx.guild.id)]
        except KeyError:
            await hf.safe_send(ctx, f"There are no questions channels on this server.  Run `;question setup` in the "
                                    f"questions channel to start setup.")
            return
        emb = discord.Embed(title=f"List of open questions:")
        if str(ctx.channel.id) in config:
            log_channel_id = config[str(ctx.channel.id)]['log_channel']
        elif str(ctx.guild.id) in config:
            log_channel_id = config[str(ctx.guild.id)]['log_channel']
        else:
            log_channel_id = '0'  # use all channels
        for channel in config:
            if config[channel]['log_channel'] != log_channel_id and log_channel_id != 0:
                continue
            channel_config = config[str(channel)]['questions']
            for question in channel_config.copy():
                try:
                    question_channel = self.bot.get_channel(int(channel))
                    question_message = await question_channel.fetch_message(
                        channel_config[question]['question_message'])
                    question_text = ' '.join(question_message.content.split(' '))
                    text_splice = 1020 - len(question_message.jump_url) - \
                                  len(f"By {question_message.author.mention} in {question_message.channel.mention}\n\n")
                    value_text = f"By {question_message.author.mention} in {question_message.channel.mention}\n" \
                                 f"{question_text[:text_splice]}\n" \
                                 f"{question_message.jump_url}"
                    emb.add_field(name=f"Question `{question}`",
                                  value=value_text)
                except discord.errors.NotFound:
                    emb.add_field(name=f"Question `{question}`",
                                  value="original message not found")
        await hf.safe_send(ctx, embed=emb)

    @question.command(aliases=['edit'])
    @hf.is_admin()
    async def change(self, ctx, log_id, target, *text):
        """Edit either the asker, answerer, question, title, or answer of a question log in the log channel"""
        config = self.bot.db['questions'][str(ctx.guild.id)][str(ctx.channel.id)]
        log_channel = self.bot.get_channel(config['log_channel'])
        target_message = await log_channel.fetch_message(int(log_id))
        if target not in ['asker', 'answerer', 'question', 'title', 'answer']:
            await hf.safe_send(ctx,
                               f"Invalid field specified in the log message.  Please choose a target to edit out of "
                               f"`asker`, `answerer`, `question`, `title`, `answer`")
            return
        emb = target_message.embeds[0]

        if target == 'question':
            try:
                question_id = int(text[0])  # ;q edit 555932038612385798 question 555943517994614784
                question_message = await ctx.channel.fetch_message(question_id)
                emb.set_field_at(0, name=emb.fields[0].name, value=f"{question_message.content[:900]}\n"
                                                                   f"{question_message.jump_url})")
            except ValueError:
                question_message = ctx.message  # ;q edit 555932038612385798 question <New question text>
                question_text = ' '.join(question_message.content.split(' ')[3:])
                emb.set_field_at(0, name=emb.fields[0].name, value=f"{question_text}\n{question_message.jump_url}")
        if target == 'title':
            title = ' '.join(text)
            jump_url = emb.fields[0].split('\n')[-1]
            emb.set_field_at(0, name=emb.fields[0].name, value=f"{title}\n{jump_url}")
        if target == 'asker':
            try:
                asker = ctx.guild.get_member(int(text[0]))
            except ValueError:
                await hf.safe_send(ctx, f"To edit the asker, give the user ID of the user.  For example: "
                                        f"`;q edit <log_message_id> asker <user_id>`")
                return
            new_description = emb.description.split(' ')
            new_description[2] = f"{asker.mention} ({asker.name})"
            del new_description[3]
            emb.description = ' '.join(new_description)

        if emb.title == 'ANSWERED':
            if target == 'answerer':
                answerer = ctx.guild.get_member(int(text[0]))
                new_description = emb.description.split('Answered by ')[1] = answerer.mention
                emb.description = 'Answered by '.join(new_description)
            elif target == 'answer':
                try:  # ;q edit <log_message_id> answer <answer_id>
                    answer_message = await ctx.channel.fetch_message(int(text[0]))
                    emb.set_field_at(1, name=emb.fields[1].name, value=answer_message.jump_url)
                except ValueError:
                    answer_message = ctx.message  # ;q edit <log_message_id> answer <new text>
                    answer_text = 'answer '.join(ctx.message.split('answer ')[1:])
                    emb.set_field_at(1, name=emb.fields[1].name, value=f"{answer_text[:900]}\n"
                                                                       f"{answer_message.jump_url}")

        if emb.footer.text:
            emb.set_footer(text=emb.footer.text + f", Edited by {ctx.author.name}")
        else:
            emb.set_footer(text=f"Edited by {ctx.author.name}")
        await target_message.edit(embed=emb)
        try:
            await ctx.message.add_reaction('\u2705')
        except discord.errors.Forbidden:
            await hf.safe_send(ctx, f"I lack the ability to add reactions, please give me this permission")

    @commands.command()
    @commands.bot_has_permissions(send_messages=True)
    async def jisho(self, ctx, *, text):
        """Provides a link to a Jisho search"""
        await ctx.message.delete()
        await hf.safe_send(ctx,
                           f"Try finding the meaning to the word you're looking for here: https://jisho.org/search/{text}")

    @commands.command(aliases=['server', 'info', 'sinfo'])
    @commands.cooldown(1, 30, type=commands.BucketType.channel)
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def serverinfo(self, ctx):
        """Shows info about this server"""
        guild = ctx.guild
        if not guild:
            await hf.safe_send(ctx,
                               f"{ctx.channel}.  Is that what you were looking for?  (Why are you trying to call info "
                               f"on 'this server' in a DM?)")
            return
        em = discord.Embed(title=f"**{guild.name}**",
                           description=f"**ID:** {guild.id}",
                           timestamp=guild.created_at,
                           colour=discord.Colour(0x877AD6))
        em.set_thumbnail(url=guild.icon_url)
        em.add_field(name="Region", value=guild.region)
        em.add_field(name="Channels", value=f"{len(guild.text_channels)} text / {len(guild.voice_channels)} voice")
        em.add_field(name="Verification Level", value=guild.verification_level)
        em.add_field(name="Guild created on (UTC)", value=guild.created_at.strftime("%Y/%m/%d %H:%M:%S"))
        em.add_field(name="Number of members", value=ctx.guild.member_count)

        if guild.afk_channel:
            em.add_field(name="Voice AFK Timeout",
                         value=f"{guild.afk_timeout//60} mins → {guild.afk_channel.mention}")

        if guild.explicit_content_filter != "disabled":
            em.add_field(name="Explicit Content Filter", value=guild.explicit_content_filter)

        if guild.id not in [189571157446492161, 243838819743432704]:
            em.add_field(name="Server owner", value=f"{guild.owner.name}#{guild.owner.discriminator}")

        list_of_members = guild.members
        if len(list_of_members) < 20000:
            role_count = {}
            for member in list_of_members:
                for role in member.roles:
                    if role.name in role_count:
                        role_count[role.name] += 1
                    else:
                        role_count[role.name] = 1
            sorted_list = sorted(list(role_count.items()), key=lambda x: x[1], reverse=True)
            top_five_roles = ''
            counter = 0
            for role in sorted_list[1:7]:
                counter += 1
                top_five_roles += f"{role[0]}: {role[1]}\n"
                # if counter == 3:
                #    top_five_roles += '\n'
            top_five_roles = top_five_roles[:-1]
            em.add_field(name=f"Top 6 roles (out of {len(guild.roles)})", value=top_five_roles)
        else:
            em.add_field(name="Roles", value=str(len(guild.roles)))

        how_long_ago = datetime.utcnow() - guild.created_at
        days = how_long_ago.days
        years = days // 365
        bef_str = ''
        if years:
            bef_str = f"{years} years, "
        months = (days - 365 * years) // 30.416666666666668
        if months:
            bef_str += f"{int(months)} months, "
        days = days - 365 * years - round(30.416666666666668 * months)
        bef_str += f"{days} days"
        em.set_footer(text=f"Guild created {bef_str} ago on:")
        if len(em.fields) % 2 == 0:
            two = em.fields[-2]
            em.add_field(name=two.name, value=two.value)
            em.remove_field(-3)
        try:
            await hf.safe_send(ctx, embed=em)
        except discord.Forbidden:
            pass

    @commands.group(invoke_without_command=True, aliases=['gb', 'gbl', 'blacklist'], hidden=True)
    @blacklist_check()
    async def global_blacklist(self, ctx):
        """A global blacklist for banning spammers, requires three votes from mods from three different servers"""
        config = hf.database_toggle(ctx, self.bot.db['global_blacklist'])
        if config['enable']:
            if not ctx.me.guild_permissions.ban_members:
                await hf.safe_send(ctx,
                                   'I lack the permission to ban members.  Please fix that before enabling this module')
                hf.database_toggle(ctx, self.bot.db['global_blacklist'])
                return
            await hf.safe_send(ctx,
                               "Enabled the global blacklist on this server.  Anyone voted into the blacklist by three "
                               "mods and joining your server will be automatically banned.  "
                               "Type `;global_blacklist residency` to claim your residency on a server.")
        else:
            await hf.safe_send(ctx,
                               "Disabled the global blacklist.  Anyone on the blacklist will be able to join  your server.")

    @global_blacklist.command(name='reason', aliases=['edit'])
    @blacklist_check()
    async def blacklist_reason(self, ctx, entry_message_id, *, reason):
        """Add a reason to a blacklist entry: `;gbl reason <message_id> <reason>`"""
        blacklist_channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
        entry_message = await blacklist_channel.fetch_message(int(entry_message_id))
        emb = entry_message.embeds[0]
        old_reason = emb.fields[1].value
        emb.set_field_at(1, name=emb.fields[1].name, value=reason)
        await entry_message.edit(embed=emb)
        await hf.safe_send(ctx, f"Changed reason of {entry_message.jump_url}\nOld reason: ```{old_reason}```")

    @global_blacklist.command(name='remove', alias=['delete'])
    @blacklist_check()
    async def blacklist_remove(self, ctx, entry_message_id):
        """Removes an entry from the blacklist channel"""
        blacklist_channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
        try:
            entry_message = await blacklist_channel.fetch_message(int(entry_message_id))
        except discord.NotFound:
            await hf.safe_send(ctx,
                               f"Message not found.  If you inputted the ID of a user, please input the message ID of "
                               f"the entry in the blacklist instead.")
            return
        emb = entry_message.embeds[0]
        target_id = emb.title.split(' ')[0]
        await entry_message.delete()

        try:
            self.bot.db['global_blacklist']['blacklist'].remove(str(target_id))
        except ValueError:
            pass

        try:
            del self.bot.db['global_blacklist']['votes2'][str(target_id)]
        except ValueError:
            pass

        emb.color = discord.Color(int('ff00', 16))
        emb.set_field_at(0, name="Entry removed by", value=f"{ctx.author.name}#{ctx.author.discriminator}")
        await blacklist_channel.send(embed=emb)

        await ctx.message.add_reaction('✅')

    @global_blacklist.command()
    @blacklist_check()
    async def residency(self, ctx):
        """Claims your residency on a server"""
        config = self.bot.db['global_blacklist']['residency']

        if str(ctx.author.id) in config:
            server = self.bot.get_guild(config[str(ctx.author.id)])
            await hf.safe_send(ctx,
                               f"You've already claimed residency on {server.name}.  You can not change this without "
                               f"talking to Ryan.")
            return

        await hf.safe_send(ctx,
                           "For the purpose of maintaining fairness in a ban, you're about to claim your mod residency to "
                           f"`{ctx.guild.name}`.  This can not be changed without talking to Ryan.  "
                           f"Do you wish to continue?\n\nType `yes` or `no` (case insensitive).")
        msg = await self.bot.wait_for('message',
                                      timeout=25.0,
                                      check=lambda m: m.author == ctx.author and m.channel == ctx.channel)

        if msg.content.casefold() == 'yes':  # register
            config[str(ctx.author.id)] = ctx.guild.id
            await hf.safe_send(ctx,
                               f"Registered your residency to `{ctx.guild.name}`.  Type `;global_blacklist add <ID>` to "
                               f"vote on a user for the blacklist")

        elif msg.content.casefold() == 'no':  # cancel
            await hf.safe_send(ctx, "Understood.  Exiting module.")

        else:  # invalid response
            await hf.safe_send(ctx, "Invalid response")

    @blacklist_check()
    @global_blacklist.command(aliases=['vote'], name="add")
    async def blacklist_add(self, ctx, *, args):
        """Add people to the blacklist"""
        args = args.replace('\n', ' ').split()
        list_of_ids = []
        reason = "None"
        for arg_index in range(len(args)):
            if re.search('\d{17,22}', args[arg_index]):
                list_of_ids.append(str(args[arg_index]))
            else:
                reason = ' '.join(args[arg_index:])
                break
        channel = self.bot.get_channel(BLACKLIST_CHANNEL_ID)
        config = self.bot.db['global_blacklist']
        if not list_of_ids:
            await hf.safe_send(ctx.author, f"No valid ID found in command")
            return
        for user in list_of_ids:
            user_obj = self.bot.get_user(user)
            if not user_obj:
                try:
                    user_obj = await self.bot.fetch_user(user)
                except discord.NotFound:
                    user_obj = None

            async def post_vote_notification(target_user, reason):
                await ctx.message.add_reaction('✅')
                if not target_user:
                    target_user = ''
                emb = discord.Embed(title=f"{user} {target_user} (1 vote)", color=discord.Color(int('ffff00', 16)))
                emb.add_field(name='Voters', value=ctx.author.name)
                emb.add_field(name='Reason', value=reason)
                msg = await hf.safe_send(channel, embed=emb)
                await msg.add_reaction('⬆')
                return msg

            try:  # the guild ID that the person trying to add a vote belongs to
                user_residency = config['residency'][str(ctx.author.id)]  # a guild id
            except KeyError:
                await hf.safe_send(ctx.author,
                                   "Please claim residency on a server first with `;global_blacklist residency`")
                return

            if user in config['blacklist']:  # already blacklisted
                await hf.safe_send(ctx, f"{user} is already on the blacklist")
                continue

            if user not in config['votes2']:  # 0 votes
                config['votes2'][user] = {'votes': [user_residency], 'message': 0}
                msg = await post_vote_notification(user_obj, reason)
                config['votes2'][user]['message'] = msg.id
                continue

            if user in config['votes2']:  # 1 or 2 votes
                list_of_votes = config['votes2'][user]['votes']
                if user_residency in list_of_votes:
                    await hf.safe_send(ctx.author, f"{user} - Someone from your server already voted")
                    continue

                message = await channel.fetch_message(config['votes2'][user]['message'])
                emb = message.embeds[0]
                title_str = emb.title
                result = re.search('(\((.*)\))? \((.) votes?\)', title_str)
                # target_username = result.group(2)
                num_of_votes = result.group(3)
                emb.title = re.sub('(.) vote', f'{int(num_of_votes)+1} vote', emb.title)
                if num_of_votes == '1':  # 1-->2
                    emb.title = emb.title.replace('vote', 'votes')
                    config['votes2'][user]['votes'].append(user_residency)
                if num_of_votes == '2':  # 2-->3
                    emb.color = discord.Color(int('ff0000', 16))
                    del config['votes2'][user]
                    config['blacklist'].append(int(user))
                emb.set_field_at(0, name=emb.fields[0].name, value=emb.fields[0].value + f', {ctx.author.name}')
                await message.edit(embed=emb)

    @global_blacklist.command(name='list')
    @blacklist_check()
    async def blacklist_list(self, ctx):
        """Lists the users with residencies on each server"""
        users_str = ''
        users_dict = {}
        config = self.bot.db['global_blacklist']['residency']
        for user_id in config:
            user = self.bot.get_user(int(user_id))
            guild = self.bot.get_guild(config[user_id])
            if guild in users_dict:
                users_dict[guild].append(user)
            else:
                users_dict[guild] = [user]
        for guild in users_dict:
            try:
                users_str += f"**{guild.name}:** {', '.join([user.name for user in users_dict[guild]])}\n"
            except AttributeError:
                pass
        emb = discord.Embed(title="Global blacklist residencies", description="Listed below is a breakdown of who "
                                                                              "holds residencies in which servers.\n\n")
        emb.description += users_str
        await hf.safe_send(ctx, embed=emb)

    @commands.command()
    @hf.is_submod()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    async def mute(self, ctx, time, member=None, *, reason=None):
        """Mutes a user.  Syntax: `;mute <time> <member>`.  Example: `;mute 1d2h Abelian`  Mute for "0" for an
        indefinite mute."""

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

        time_string, length = hf.parse_time(str(time))
        if not time_string:  # indefinite mute
            if not reason:
                reason = ''
            if member:
                reason = f"{member} {reason}"
            member = time
            time = None

        silent = False
        if reason:
            if '-s' in reason or '-n' in reason:
                if ctx.guild.id == JP_SERVER_ID:
                    await hf.safe_send(ctx, "Maybe you meant to use Ciri?")
                reason = reason.replace(' -s', '').replace('-s ', '').replace('-s', '')
                silent = True

        target = await hf.member_converter(ctx, member)
        if not target:
            return
        if role in target.roles:
            await hf.safe_send(ctx, "This user is already muted (already has the mute role)")
            return
        await target.add_roles(role, reason=f"Muted by {ctx.author.name} in {ctx.channel.name}")

        if target.voice:  # if they're in a channel, move them out then in to trigger the mute
            voice_state = target.voice
            try:
                if ctx.guild.afk_channel:
                    await target.move_to(ctx.guild.afk_channel)
                    await target.move_to(voice_state.channel)
                else:
                    for channel in ctx.guild.voice_channels:
                        if not channel.members:
                            await target.move_to(channel)
                            await target.move_to(voice_state.channel)
                            break
            except discord.Forbidden:
                pass

        if time_string:
            config['timed_mutes'][str(target.id)] = time_string

        notif_text = f"**{target.name}#{target.discriminator}** has been **muted** from text and voice chat."
        if time_string:
            notif_text = notif_text[:-1] + f" for {time}."
        if reason:
            notif_text += f"\nReason: {reason}"
        emb = hf.red_embed(notif_text)
        if time_string:
            emb.description = emb.description[:-1] + f" for {length[0]}d{length[1]}h."
        if silent:
            emb.description += " (The user was not notified of this)"
        await hf.safe_send(ctx, embed=emb)

        modlog_config = hf.add_to_modlog(ctx, target, 'Mute', reason, silent, time)
        modlog_channel = self.bot.get_channel(modlog_config['channel'])

        emb = hf.red_embed(f"You have been muted on {ctx.guild.name} server")
        emb.color = discord.Color(int('ffff00', 16))  # embed
        if time_string:
            emb.add_field(name="Length", value=f"{time} (will be unmuted on {time_string})", inline=False)
        else:
            emb.add_field(name="Length", value="Indefinite", inline=False)
        if reason:
            emb.add_field(name="Reason", value=reason)
        if not silent:
            await target.send(embed=emb)

        emb.insert_field_at(0, name="User", value=f"{target.name} ({target.id})", inline=False)
        emb.description = "Mute"
        emb.add_field(name="Jump URL", value=ctx.message.jump_url, inline=False)
        emb.set_footer(text=f"Muted by {ctx.author.name} ({ctx.author.id})")
        try:
            await hf.safe_send(modlog_channel, embed=emb)
        except AttributeError:
            await hf.safe_send(ctx, embed=emb)

    @commands.command()
    @hf.is_submod()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    async def unmute(self, ctx, target_in, guild=None):
        """Unmutes a user"""
        if not guild:
            guild = ctx.guild
            target: discord.Member = await hf.member_converter(ctx, target_in)
        else:
            guild = self.bot.get_guild(int(guild))
            target: discord.Member = guild.get_member(int(target_in))
        config = self.bot.db['mutes'][str(guild.id)]
        role = guild.get_role(config['role'])

        failed = False
        if target:
            target_id = target.id
            try:
                await target.remove_roles(role)
                failed = False
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

    lang_codes_dict = {'af': 'Afrikaans', 'ga': 'Irish', 'sq': 'Albanian', 'it': 'Italian', 'ar': 'Arabic',
                       'ja': 'Japanese', 'az': 'Azerbaijani', 'kn': 'Kannada', 'eu': 'Basque', 'ko': 'Korean',
                       'bn': 'Bengali', 'la': 'Latin', 'be': 'Belarusian', 'lv': 'Latvian', 'bg': 'Bulgarian',
                       'lt': 'Lithuanian', 'ca': 'Catalan', 'mk': 'Macedonian', 'zh-CN': 'Chinese Simplified',
                       'ms': 'Malay', 'zh-TW': 'Chinese Traditional', 'mt': 'Maltese', 'hr': 'Croatian',
                       'no': 'Norwegian', 'cs': 'Czech', 'fa': 'Persian', 'da': 'Danish', 'pl': 'Polish',
                       'nl': 'Dutch', 'pt': 'Portuguese', 'en': 'English', 'ro': 'Romanian', 'eo': 'Esperanto',
                       'ru': 'Russian', 'et': 'Estonian', 'sr': 'Serbian', 'tl': 'Filipino', 'sk': 'Slovak',
                       'fi': 'Finnish', 'sl': 'Slovenian', 'fr': 'French', 'es': 'Spanish', 'gl': 'Galician',
                       'sw': 'Swahili', 'ka': 'Georgian', 'sv': 'Swedish', 'de': 'German', 'ta': 'Tamil',
                       'el': 'Greek', 'te': 'Telugu', 'gu': 'Gujarati', 'th': 'Thai', 'ht': 'Haitian Creole',
                       'tr': 'Turkish', 'iw': 'Hebrew', 'uk': 'Ukrainian', 'hi': 'Hindi', 'ur': 'Urdu',
                       'hu': 'Hungarian', 'vi': 'Vietnamese', 'is': 'Icelandic', 'cy': 'Welsh', 'id': 'Indonesian',
                       'yi': 'Yiddish'}

    @commands.command(aliases=['uc'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def uchannels(self, ctx, *, member: str = None):
        if not member:
            member = ctx.author
        else:
            member = await hf.member_converter(ctx, member)
            if not member:
                return
        try:
            config = self.bot.stats[str(ctx.guild.id)]['messages']
        except KeyError:
            return

        message_count = {}
        for day in config:
            if str(member.id) in config[day]:
                user = config[day][str(member.id)]
                for channel in user:
                    if channel in ['emoji', 'lang']:
                        continue
                    message_count[channel] = message_count.get(channel, 0) + user[channel]
        sorted_msgs = sorted(message_count.items(), key=lambda x: x[1], reverse=True)
        emb = discord.Embed(title=f'Usage stats for {member.name} ({member.nick})',
                            description="Last 30 days",
                            color=discord.Color(int('00ccFF', 16)),
                            timestamp=member.joined_at)
        lb = ''
        index = 1
        total = 0
        for channel_tuple in sorted_msgs:
            total += channel_tuple[1]
        for channel_tuple in sorted_msgs:
            if str(ctx.channel.id) not in self.bot.stats[str(ctx.guild.id)]['hidden']:
                if channel_tuple[0] in self.bot.stats[str(ctx.guild.id)]['hidden']:
                    continue
            try:
                channel = ctx.guild.get_channel(int(channel_tuple[0]))
                if not channel:
                    continue
                lb += f"**{index}) {channel.name}**: {round((channel_tuple[1]/total)*100, 2)}% ({channel_tuple[1]})\n"
                index += 1
            except discord.NotFound:
                pass
            if index == 26:
                break
        emb.add_field(name="Top channels", value=lb[:1024])
        await hf.safe_send(ctx, embed=emb)

    @commands.command(aliases=['u'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def user(self, ctx, *, member: str = None):
        """Gives info about a user.  Leave the member field blank to get info about yourself."""
        if not member:
            member = ctx.author
        else:
            member = await hf.member_converter(ctx, member)
            if not member:
                return
        try:
            config = self.bot.stats[str(ctx.guild.id)]['messages']
        except KeyError:
            return

        # ### Collect all the data from the database ###
        emoji_dict = {emoji.name: emoji for emoji in ctx.guild.emojis}
        message_count = {}
        emoji_count = {}
        lang_count = {}
        total_msgs_month = 0
        total_msgs_week = 0
        for day in config:
            if str(member.id) in config[day]:
                user = config[day][str(member.id)]
                for channel in user:
                    if channel in ['emoji', 'lang']:
                        continue
                    message_count[channel] = message_count.get(channel, 0) + user[channel]
                    days_ago = (datetime.utcnow() - datetime.strptime(day, "%Y%m%d")).days
                    if days_ago <= 7:
                        total_msgs_week += user[channel]
                    total_msgs_month += user[channel]
                if 'emoji' in user:
                    for emoji in user['emoji']:
                        if emoji in emoji_dict:
                            name = emoji_dict[emoji]
                        else:
                            name = emoji
                        emoji_count[name] = emoji_count.get(name, 0) + user['emoji'][emoji]
                if 'lang' in user:
                    for lang in user['lang']:
                        lang_count[lang] = lang_count.get(lang, 0) + user['lang'][lang]

        # ### Sort the data ###
        sorted_msgs = sorted(message_count.items(), key=lambda x: x[1], reverse=True)
        # looks like [('284045742652260352', 15), ('296491080881537024', 3), ('296013414755598346', 1)]
        sorted_emojis = sorted(emoji_count.items(), key=lambda x: x[1], reverse=True)
        sorted_langs = sorted(lang_count.items(), key=lambda x: x[1], reverse=True)

        # ### Make embed ###
        emb = discord.Embed(title=f'Usage stats for {member.name} ({member.nick})',
                            description="Last 30 days",
                            color=discord.Color(int('00ccFF', 16)),
                            timestamp=member.joined_at)
        emb.add_field(name="Messages sent M | W",
                      value=f"{total_msgs_month} | {total_msgs_week}")

        # ### Find top 3 most active channels ###
        good_channels = 0
        hidden = self.bot.stats[str(ctx.guild.id)]['hidden']
        for channel in sorted_msgs.copy():
            if str(ctx.channel.id) in hidden:  # you're in a hidden channel, keep all
                break
            if channel[0] in hidden:  # one of the top channels is a hidden channel, remove
                sorted_msgs.remove(channel)
            else:  # it's not a hidden channel, keep
                good_channels += 1
            if good_channels == 3:  # you have three kept channels
                break

        # ### Format top 3 channels text field / Add field to embed ###
        channeltext = ''
        try:
            channel1 = (self.bot.get_channel(int(sorted_msgs[0][0])),
                        round(100 * sorted_msgs[0][1] / total_msgs_month, 2))
            channeltext += f"**#{channel1[0]}**: {channel1[1]}%⠀\n"
            channel2 = (self.bot.get_channel(int(sorted_msgs[1][0])),
                        round(100 * sorted_msgs[1][1] / total_msgs_month, 2))
            channeltext += f"**#{channel2[0]}**: {channel2[1]}%⠀\n"
            channel3 = (self.bot.get_channel(int(sorted_msgs[2][0])),
                        round(100 * sorted_msgs[2][1] / total_msgs_month, 2))
            channeltext += f"**#{channel3[0]}**: {channel3[1]}%⠀\n"
        except IndexError:  # will stop automatically if there's not three channels in the list
            pass
        if channeltext:
            emb.add_field(name="Top Channels:",
                          value=f"{channeltext}")

        # ### Calculate voice time / Add field to embed ###
        voice_config = self.bot.stats[str(ctx.guild.id)]['voice']['total_time']
        voice_time = 0
        for day in voice_config:
            if str(member.id) in voice_config[day]:
                time = voice_config[day][str(member.id)]
                voice_time += time
        hours = voice_time // 60
        minutes = voice_time % 60
        if voice_time:
            emb.add_field(name="Time in voice chats",
                          value=f"{hours}h {minutes}m")

        # ### If no messages or voice in last 30 days ###
        if (not total_msgs_month or not sorted_msgs) and not voice_time:
            emb = discord.Embed(title=f'Usage stats for {member.name} ({member.nick})',
                                description="This user hasn't said anything in the past 30 days",
                                color=discord.Color(int('00ccFF', 16)),
                                timestamp=member.joined_at)

        # ### Add emojis field ###
        if sorted_emojis:
            value = ''
            counter = 0
            for emoji_tuple in sorted_emojis:
                value += f"{str(emoji_tuple[0])} {str(emoji_tuple[1])} times\n"
                counter += 1
                if counter == 3:
                    break
            emb.add_field(name='Most used emojis', value=value)

        # ### Add top langauges field ###
        if sorted_langs:
            value = ''
            counter = 0
            total = 0
            for lang_tuple in sorted_langs:
                total += lang_tuple[1]
            for lang_tuple in sorted_langs:
                if lang_tuple[0] not in self.lang_codes_dict:
                    continue
                percentage = round((lang_tuple[1] / total) * 100, 1)
                if counter in [0, 1]:
                    value += f"**{self.lang_codes_dict[lang_tuple[0]]}**: {percentage}%\n"
                if counter > 1 and percentage > 5:
                    value += f"**{self.lang_codes_dict[lang_tuple[0]]}**: {percentage}%\n"
                counter += 1
                if counter == 5:
                    break
            emb.add_field(name='Most used languages', value=value)

        # ### Calculate join position ###
        sorted_members_by_join = sorted([(member, member.joined_at) for member in ctx.guild.members],
                                        key=lambda x: x[1],
                                        reverse=False)
        join_order = 0
        for i in sorted_members_by_join:
            if i[0].id == member.id:
                join_order = sorted_members_by_join.index(i)
                break
        if join_order + 1:
            emb.set_footer(text=f"(#{join_order+1} to join this server) Joined on:")

        # ### Send ###
        try:
            await hf.safe_send(ctx, embed=emb)
        except discord.Forbidden:
            try:
                await hf.safe_send(ctx, "I lack the permissions to send embeds in this channel")
                await hf.safe_send(ctx.author, embed=emb)
            except discord.Forbidden:
                await hf.safe_send(ctx.author, "I lack the permission to send messages in that channel")

    @staticmethod
    def make_leaderboard_embed(ctx, channel_in, dict_in, title):
        sorted_dict = sorted(dict_in.items(), reverse=True, key=lambda x: x[1])
        emb = discord.Embed(title=title,
                            description="Last 30 days",
                            color=discord.Color(int('00ccFF', 16)),
                            timestamp=datetime.utcnow())
        if channel_in:
            emb.title = f"Leaderboard for #{channel_in.name}"
        number_of_users_found = 0
        found_yourself = False
        for i in range(len(sorted_dict)):
            member = ctx.guild.get_member(int(sorted_dict[i][0]))
            if member:
                if number_of_users_found < 24 or \
                        (number_of_users_found == 24 and (found_yourself or member == ctx.author)) or \
                        number_of_users_found > 24 and member == ctx.author:
                    if title.startswith("Messages"):
                        value = sorted_dict[i][1]
                        emb.add_field(name=f"{number_of_users_found+1}) {member.name}",
                                      value=sorted_dict[i][1])
                    elif title.startswith("Voice"):
                        hours = sorted_dict[i][1] // 60
                        minutes = sorted_dict[i][1] % 60
                        emb.add_field(name=f"{number_of_users_found+1}) {member.name}",
                                      value=f"{hours}h {minutes}m")
                number_of_users_found += 1
                if member == ctx.author:
                    found_yourself = True
            if number_of_users_found >= 25 and found_yourself:
                break
        return emb

    async def make_lb(self, ctx, channel_in):
        try:
            config = self.bot.stats[str(ctx.guild.id)]['messages']
        except KeyError:
            return
        msg_count = {}
        for day in config:
            for user in config[day]:
                for channel in config[day][user]:
                    if channel in ['emoji', 'lang']:
                        continue
                    if channel_in:
                        if str(channel_in.id) != channel:
                            continue
                    try:
                        msg_count[user] += config[day][user][channel]
                    except KeyError:
                        msg_count[user] = config[day][user][channel]
        try:
            await hf.safe_send(ctx,
                               embed=self.make_leaderboard_embed(ctx, channel_in, msg_count, "Messages Leaderboard"))
        except discord.Forbidden:
            try:
                await hf.safe_send(ctx, "I lack the permissions to send embeds in this channel")
                await hf.safe_send(ctx.author, embed=emb)
            except discord.Forbidden:
                await hf.safe_send(ctx.author, "I lack the permission to send messages in that channel")

    @commands.command()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def lb(self, ctx):
        """Shows a leaderboard of the top 25 most active users this month"""
        await self.make_lb(ctx, False)

    @commands.command()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def chlb(self, ctx, channel=None):
        if not channel:
            channel = ctx.channel
        else:
            channel_id = channel[2:-1]
            try:
                channel = ctx.guild.get_channel(int(channel_id))
            except ValueError:
                await hf.safe_send(ctx,
                                   f"Please provide a link to a channel, not just the channel name (e.g. `;chlb #general`),"
                                   f"or if you just type `;chlb` it will show the leaderboard for the current channel.")
                return
        await self.make_lb(ctx, channel)

    @commands.command(aliases=['v', 'vclb', 'vlb', 'voicechat'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def vc(self, ctx):
        """Prints a leaderboard of who has the most time in voice"""
        try:
            config = self.bot.stats[str(ctx.guild.id)]['voice']['total_time']
        except KeyError:
            return
        lb_dict = {}
        for day in config:
            for user in config[day]:
                if user in lb_dict:
                    lb_dict[user] += config[day][user]
                else:
                    lb_dict[user] = config[day][user]
        await hf.safe_send(ctx, embed=self.make_leaderboard_embed(ctx, None, lb_dict, "Voice Leaderboard"))

    @commands.command(name="delete", aliases=['del'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def msg_delete(self, ctx, *ids):
        """A command to delete messages for mods (nod admins, submods).  Usage: `;del <list of IDs>`\n\n
        Example: `;del 589654995956269086 589654963337166886 589654194189893642`"""
        await ctx.message.delete()
        if not hf.submod_check(ctx):
            try:
                if ctx.author.id not in self.bot.db['channel_mods'][str(ctx.guild.id)][str(ctx.channel.id)]:
                    return
            except KeyError:
                return
        msgs = []
        failed_ids = []
        invalid_ids = []

        # search ctx.channel for the ids
        for msg_id in ids:
            try:
                msg = await ctx.channel.fetch_message(msg_id)
                msgs.append(msg)
            except discord.NotFound:
                failed_ids.append(msg_id)
            except discord.HTTPException:
                invalid_ids.append(msg_id)

        if invalid_ids:
            await hf.safe_send(ctx, f"The following IDs were not properly formatted: `{'`, `'.join(invalid_ids)}`")

        # search every channel, not just ctx.channel for the missing IDs
        if failed_ids:
            for channel in ctx.guild.text_channels:
                for msg_id in failed_ids.copy():
                    try:
                        msg = await channel.fetch_message(msg_id)
                        msgs.append(msg)
                        failed_ids.remove(msg_id)
                    except discord.NotFound:
                        break
                    except discord.Forbidden:
                        break
                if not failed_ids:
                    break
        if failed_ids:
            await hf.safe_send(ctx, f"Unable to find ID(s) `{'`, `'.join(failed_ids)}`.")

        if not msgs:
            return  # no messages found

        emb = discord.Embed(title=f"Deleted messages", color=discord.Color(int('ff0000', 16)),
                            description=f"by {ctx.author.mention} ({ctx.author.name}#{ctx.author.discriminator})")
        embeds = []
        for msg_index in range(len(msgs)):
            msg = msgs[msg_index]
            jump_url = ''
            async for msg_history in msg.channel.history(limit=1, before=msg):
                jump_url = msg_history.jump_url
            try:
                await msg.delete()
            except discord.NotFound:
                continue
            except discord.Forbidden:
                await ctx.send(f"I lack the permission to delete messages in {msg.channel.mention}.")
                return
            if msg.embeds:
                for embed in msg.embeds:
                    embeds.append(embed)
                    emb.add_field(name=f"Embed deleted [Jump URL]({jump_url})", value="Content shown below")
            if msg.content:
                emb.add_field(name=f"Message {msg_index} by "
                                   f"{msg.author.name}#{msg.author.discriminator} ({msg.author.id})",
                              value=f"([Jump URL]({jump_url})) {msg.content}"[:1024 - len(jump_url)])
            if msg.content[1024:]:
                emb.add_field(name=f"continued", value=f"...{msg.content[1024-len(jump_url):len(jump_url)+1024]}")
            if msg.attachments:
                x = [f"{att.filename}: {att.proxy_url}" for att in msg.attachments]
                emb.add_field(name="Attachments (might expire soon):", value='\n'.join(x))
            emb.timestamp = msg.created_at
        emb.set_footer(text=f"In #{msgs[0].channel.name} - Message sent at:")
        if str(ctx.guild.id) in self.bot.db['submod_channel']:
            channel = self.bot.get_channel(self.bot.db['submod_channel'][str(ctx.guild.id)])
        elif str(ctx.guild.id) in self.bot.db['mod_channel']:
            channel = self.bot.get_channel(self.bot.db['mod_channel'][str(ctx.guild.id)])
        else:
            await hf.safe_send(ctx, "Please set either a mod channel or a submod channel with "
                                    "`;set_mod_channel` or `;set_submod_channel`")
            return
        await hf.safe_send(channel, embed=emb)
        if embeds:
            for embed in embeds:
                await hf.safe_send(channel, embed=embed)

    @commands.command()
    async def lsar(self, ctx, page_num=1):
        """Lists self-assignable roles"""
        if not ctx.guild:
            return
        roles_list = []
        config = self.bot.db['SAR'].setdefault(str(ctx.guild.id), {'0': []})
        for group in config.copy():
            if len(config[group]) == 0:
                del config[group]
        groups = sorted([int(key) for key in config])
        groups = [str(i) for i in groups]
        for group in groups:
            for role in config[group]:
                roles_list.append((group, role))
        role_list_str = f"**There are {len(roles_list)} self-assignable roles**\n"
        if len(roles_list) == 1:
            role_list_str = role_list_str.replace('roles', 'role').replace('are', 'is')
        current_group = ''
        try:
            current_group = roles_list[20 * (page_num - 1)][0]
            role_list_str += f"⟪Group {current_group}⟫\n"
        except IndexError:
            pass

        for role_tuple in roles_list[20 * (page_num - 1):20 * page_num]:
            if current_group != role_tuple[0]:
                current_group = groups[groups.index(current_group) + 1]
                role_list_str += f"\n⟪Group {current_group}⟫\n"

            role = ctx.guild.get_role(role_tuple[1])
            if not role:
                await ctx.send(f"{role_tuple}, {config[current_group]}, {current_group}")
                config[current_group].remove(role_tuple[1])
                continue
            role_list_str += f"⠀{role.name}\n"

        emb = discord.Embed(description=role_list_str, color=discord.Color(int('00ff00', 16)))
        emb.set_footer(text=f"{page_num} / {(len(roles_list)//20)+1}")
        await hf.safe_send(ctx, embed=emb)

    @commands.command()
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    async def iam(self, ctx, *, role_name):
        """Command used to self-assign a role"""
        if not ctx.guild:
            return
        if str(ctx.guild.id) not in self.bot.db['SAR']:
            return
        config = self.bot.db['SAR'][str(ctx.guild.id)]
        desired_role = discord.utils.find(lambda role: role.name.casefold() == role_name.casefold(), ctx.guild.roles)
        if not desired_role:
            await hf.safe_send(ctx,
                               embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** No role found"))
            return

        if desired_role in ctx.author.roles:
            await hf.safe_send(ctx, embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** "
                                                       f"You already have that role"))
            return

        for group in config:
            for role_id in config[group]:
                if desired_role.id == role_id:
                    await ctx.author.add_roles(desired_role)
                    await hf.safe_send(ctx, embed=hf.green_embed(
                        f"**{ctx.author.name}#{ctx.author.discriminator}** You now have"
                        f" the **{desired_role.name}** role."))
                    return

    @commands.command(aliases=['iamn'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True, manage_roles=True)
    async def iamnot(self, ctx, *, role_name):
        """Command used to remove a self-assigned role"""
        if str(ctx.guild.id) not in self.bot.db['SAR']:
            return
        config = self.bot.db['SAR'][str(ctx.guild.id)]

        desired_role = discord.utils.find(lambda role: role.name.casefold() == role_name.casefold(), ctx.guild.roles)
        if not desired_role:
            await hf.safe_send(ctx,
                               embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** No role found"))
            return

        if desired_role not in ctx.author.roles:
            await hf.safe_send(ctx, embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** "
                                                       f"You don't have that role"))
            return

        for group in config:
            for role_id in config[group]:
                if desired_role.id == role_id:
                    await ctx.author.remove_roles(desired_role)
                    await hf.safe_send(ctx,
                                       embed=hf.green_embed(
                                           f"**{ctx.author.name}#{ctx.author.discriminator}** You no longer have "
                                           f"the **{desired_role.name}** role."))
                    return

        await hf.safe_send(ctx, embed=hf.red_embed(f"**{ctx.author.name}#{ctx.author.discriminator}** That role is not "
                                                   f"self-assignable."))

    @commands.command()
    @commands.bot_has_permissions(send_messages=True, manage_messages=True)
    async def pin(self, ctx, message_id=None):
        """Pin a message"""
        if not hf.submod_check(ctx):
            try:
                if ctx.author.id not in self.bot.db['channel_mods'][str(ctx.guild.id)][str(ctx.channel.id)]:
                    return
            except KeyError:
                return

        to_be_pinned_msg = None
        if not message_id:
            async for message in ctx.channel.history(limit=2):
                if message.content == ';pin':
                    continue
                to_be_pinned_msg = message
        else:
            if not re.search('\d{17,22}', message_id):
                await hf.safe_send(ctx, "Please input a valid ID")
                return
            to_be_pinned_msg = await ctx.channel.fetch_message(message_id)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        try:
            await to_be_pinned_msg.pin()
        except discord.Forbidden:
            await hf.safe_send(ctx, "I lack permission to pin messages in this channel")

    @commands.command()
    @commands.bot_has_permissions(embed_links=True, ban_members=True)
    async def ban(self, ctx, *args):
        """Bans a user.  Usage: `;ban [time #d#h] <user> [reason]`  Example: `;ban @Ryry013 being mean` or
        `;ban 2d3h @Abelian posting invite links`.  If crossposting is enabled, you can add `-s` into the reason to
        make this ban not crosspost"""
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

        if ctx.guild.id == 243838819743432704:
            for _ in ['_']:
                if ctx.guild.get_role(258819531193974784) in ctx.author.roles:
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
                await hf.safe_send(ctx, "The target user has PMs disabled.")
        try:
            await target.ban(reason=text)
        except discord.Forbidden:
            await hf.safe_send(ctx, f"I couldn't ban that user.  They're probably above me in the role list.")
            return
        if length:
            config = self.bot.db['bans'].setdefault(str(ctx.guild.id),
                                                    {'enable': False, 'channel': None, 'timed_bans': {}})
            timed_bans = config.setdefault('timed_bans', {})
            timed_bans[str(target.id)] = time_string
        await hf.safe_send(ctx, f"Successfully banned")

    @commands.command(aliases=['tk', 't', 'taekim', 'gram', 'g'])
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def grammar(self, ctx, *, search_term=None):
        """Searches for grammar articles.  Use: `;grammar <search term>`.  To specify a certain website, put
        it in the beginning of your search term from one of the following options:
        `[taekim-complete, taekim-grammar, taekim, maggie, japanesetest4you, imabi, jlptsensei, ejlx]`. \n
        Aliases = `[tk, t, taekim, gram, g, imabi]`"""
        if not search_term:
            await hf.safe_send(ctx, ctx.command.help)
            return

        # ### Check if you specify a certain site ###
        sites = {'taekim-grammar': 'www.guidetojapanese.org/learn/grammar/',
                 'taekim-complete': 'www.guidetojapanese.org/learn/complete/',
                 'taekim': "www.guidetojapanese.org/learn/grammar/",
                 'maggie': 'maggiesensei.com/',
                 'japanesetest4you': 'https://japanesetest4you.com/',
                 'imabi': 'https://www.imabi.net/',
                 'jlptsensei': 'https://jlptsensei.com/',
                 'ejlx': 'https://ejlx.blogspot.com/'}
        space_split = search_term.split()
        if space_split[0] in sites:
            site = sites[space_split[0]]
            search_term = ' '.join(space_split[1:])
        else:
            site = None

        # ### Call the search ###
        engine_id = '013657184909367434363:djogpwlkrc0'
        with open(f'{dir_path}/gcse_api.txt', 'r') as read_file:
            url = f'https://www.googleapis.com/customsearch/v1' \
                  f'?q={search_term}' \
                  f'&cx={engine_id}' \
                  f'&key={read_file.read()}'
        if site:
            url += f"&siteSearch={site}"
        response = requests.get(url)
        if response.status_code != 200:
            await hf.safe_send(ctx, embed=hf.red_embed(f"Error {response.status_code}: {response.reason}"))
            return
        jr = json.loads(response.content)
        if 'items' in jr:
            results = jr['items']
        else:
            await hf.safe_send(ctx, embed=hf.red_embed("No results found."))
            return
        search_term = jr['queries']['request'][0]['searchTerms']

        def format_title(title, url):
            if url.startswith('https://japanesetest4you.com/'):
                try:
                    return title.split(' Grammar: ')[1].split(' – Japanesetest4you.com')[0]
                except IndexError:
                    return title
            if url.startswith('http://maggiesensei.com/'):
                return title.split(' – Maggie Sensei')[0]
            if url.startswith('https://www.imabi.net/'):
                return title
            if url.startswith('http://www.guidetojapanese.org/learn/grammar/'):
                return title.split(' – Learn Japanese')[0]
            if url.startswith('http://www.guidetojapanese.org/learn/complete/'):
                return title
            if url.startswith('https://jlptsensei.com/'):
                if " Grammar: " in title:
                    return ''.join(title.split(' Grammar: ')[1:]).split(' - Learn Japanese')[0]
                else:
                    return title
            return title

        def format_url(url):
            if url.startswith('https://japanesetest4you.com/'):
                return f"[Japanesetest4you]({url})"
            if url.startswith('http://maggiesensei.com/'):
                return f"[Maggie Sensei]({url})"
            if url.startswith('https://www.imabi.net/'):
                return f"[Imabi]({url})"
            if url.startswith('http://www.guidetojapanese.org/learn/grammar/'):
                return f"[Tae Kim Grammar Guide]({url})"
            if url.startswith('http://www.guidetojapanese.org/learn/complete/'):
                return f"[Tae Kim Complete Guide]({url})"
            if url.startswith('https://jlptsensei.com/'):
                return f"[JLPT Sensei]({url})"
            return url

        def make_embed(page):
            emb = hf.green_embed(f"Search for {search_term}")
            for result in results[page * 3:(page + 1) * 3]:
                title = result['title']
                url = result['link']
                snippet = result['snippet'].replace('\n', '')
                if ' ... ' in snippet:
                    snippet = snippet.split(' ... ')[1]
                for word in search_term.split():
                    final_snippet = ''
                    for snippet_word in snippet.split():
                        if not snippet_word.startswith('**') and word in snippet_word:
                            final_snippet += f"**{snippet_word}** "
                        else:
                            final_snippet += f"{snippet_word} "
                    snippet = final_snippet
                emb.description += f"\n\n**{format_title(title, url)}**\n{format_url(url)}\n{snippet}"
            return emb

        page = 0
        msg = await hf.safe_send(ctx, embed=make_embed(0))
        await msg.add_reaction('⬅')
        await msg.add_reaction('➡')

        def check(reaction, user):
            if ((str(reaction.emoji) == '⬅' and page != 0) or
                (str(reaction.emoji) == '➡' and page != len(results) // 3)) and user == ctx.author and \
                    reaction.message.id == msg.id:
                return True

        while True:
            try:
                reaction, user = await ctx.bot.wait_for('reaction_add', timeout=30.0, check=check)
            except asyncio.TimeoutError:
                try:
                    await msg.clear_reactions()
                except (discord.Forbidden, discord.NotFound):
                    pass
                return

            if str(reaction.emoji) == '⬅':
                page -= 1
            if str(reaction.emoji) == '➡':
                page += 1
            await msg.edit(embed=make_embed(page))
            await reaction.remove(user)


def setup(bot):
    bot.add_cog(Main(bot))
