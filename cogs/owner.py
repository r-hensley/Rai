import textwrap
import asyncio
import traceback
import io
import sys
import codecs
import json
import re
import os
import importlib
import datetime
from datetime import datetime, timedelta, timezone
from subprocess import PIPE, run
from contextlib import redirect_stdout
from ast import literal_eval

import discord
from discord.ext import commands

from .utils import helper_functions as hf

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

RYRY_ID = 202995638860906496
ABELIAN_ID = 414873201349361664  # Ryry alt
MARIO_RYAN_ID = 528770932613971988  # Ryry alt
UNITARITY_ID = 528770932613971988  # Ryry alt

RYRY_RAI_BOT_ID = 270366726737231884
RAI_TEST_BOT_ID = 536170400871219222


class Owner(commands.Cog):
    # various code from https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/admin.py in here, thanks

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self._last_result = None
        self.sessions = set()

    async def cog_check(self, ctx):
        if self.bot.user.id in [RYRY_RAI_BOT_ID, RAI_TEST_BOT_ID]:  # If it's Ryry's Rai bot
            return ctx.author.id in [RYRY_ID, ABELIAN_ID, MARIO_RYAN_ID, UNITARITY_ID]
        else:
            return ctx.author.id == self.bot.owner_id

    def get_syntax_error(self, e):
        if e.text is None:
            return f'```py\n{e.__class__.__name__}: {e}\n```'
        return f'```py\n{e.text}{"^":>{e.offset}}\n{e.__class__.__name__}: {e}```'

    @commands.command()
    async def guildstats(self, ctx):
        """Checks stats on various guilds that the bot is on"""
        config = self.bot.db['guildstats']
        guild_info = {}
        id_to_guild = {str(g.id): g for g in self.bot.guilds}
        for guild_id in config.copy():
            message_count = 0
            for day in config[guild_id]['messages'].copy():
                days_ago = (discord.utils.utcnow() - datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)).days
                if days_ago > 30:
                    del(config[guild_id]['messages'][day])
                else:
                    message_count += config[guild_id]['messages'][day]

            command_count = 0
            for day in config[guild_id]['commands'].copy():
                days_ago = (discord.utils.utcnow() - datetime.strptime(day, "%Y%m%d").replace(tzinfo=timezone.utc)).days
                if days_ago > 30:
                    del(config[guild_id]['commands'][day])
                else:
                    command_count += config[guild_id]['commands'][day]

            guild = id_to_guild[guild_id]
            bot_num = len([m for m in guild.members if m.bot])
            human_num = len([m for m in guild.members if not m.bot])
            guild_info[guild] = {"messages": message_count,
                                 "member_count": guild.member_count,
                                 "bots": bot_num,
                                 "humans": human_num,
                                 "commands": command_count}
        msg = ''
        for guild in guild_info:
            info = guild_info[guild]
            msg_addition = f"**{guild.name}: ({guild.id})**" \
                           f"\n{info['messages']} messages" \
                           f"\n{info['member_count']} members " \
                           f"({info['humans']} humans, {info['bots']} bots, " \
                           f"{round(info['humans']/info['member_count'], 2)})" \
                           f"\n{info['commands']} commands\n"
            if len(msg + msg_addition) < 2000:
                msg += msg_addition
            else:
                await hf.safe_send(ctx, msg)
                msg = msg_addition
        if msg:
            await hf.safe_send(ctx, msg)

        dead_guilds = []
        for guild in self.bot.guilds:
            if guild not in guild_info:
                dead_guilds.append(guild)
        msg = ''
        for guild in dead_guilds:
            bots = len([m for m in guild.members if m.bot])
            msg_addition = f"{guild.name}  --  {guild.id}  -- {bots}/{guild.member_count}\n"
            if len(msg + msg_addition) < 2000:
                msg += msg_addition
            else:
                await hf.safe_send(ctx, msg)
                msg = msg_addition
        if msg:
            await hf.safe_send(ctx, msg)

    @commands.command()
    async def edit(self, ctx, message_id, *, content):
        """Edits a message from Rai"""
        try:
            msg = await ctx.channel.fetch_message(int(message_id))
        except discord.NotFound:
            await hf.safe_send(ctx, "Message not found")
            return
        await msg.edit(content=content)
        try:
            await ctx.message.delete()
        except discord.NotFound:
            pass

    @commands.command(aliases=['repl'])
    async def reply(self, ctx, index, *, reply=''):
        """Reply to a message to the bot"""
        channel = self.bot.get_channel(int(os.getenv("BOT_TEST_CHANNEL")))
        index_re = re.search("^(;repl|;reply) (\d) ", ctx.message.content)
        if not index_re:
            reply = f"{index} {reply}"
            index = 1
        else:
            index = int(index_re.group(2))
            if not reply:
                await hf.safe_send(ctx, "Include reply message")

        async for msg in channel.history():
            result_channel_id = re.search(f'^(\d{17,22}) <@{self.bot.owner_id}>$', msg.content)
            if not result_channel_id:
                continue
            else:
                result_channel_id = result_channel_id.group(1)
            if result_channel_id:
                if (discord.utils.utcnow() - msg.created_at).seconds > 1:
                    if index > 1:
                        index -= 1
                    else:
                        send_channel = self.bot.get_channel(int(result_channel_id))
                        try:
                            await send_channel.send(reply)
                        except discord.Forbidden as e:
                            await hf.safe_send(ctx, e)
                        return

    @commands.command(aliases=['db'])
    async def database(self, ctx, depth, *, args):
        """Shows or edits database"""
        config = self.bot.db
        if '=' in args:
            args = f"{depth} {args}"
            depth = 1
        split = args.split(' = ') + ['']  # append is to make sure split[1] always has a target
        path = split[0]
        set_to = split[1]

        def process_arg(arg):
            if arg.startswith('ctx'):
                obj = ctx
                for attr in arg.split('.'):
                    if attr == 'ctx':
                        continue
                    obj = getattr(obj, attr)
                return str(obj)
            else:
                return arg

        for arg in path.split()[:-1]:
            try:
                config = config[process_arg(arg)]
            except KeyError:
                await hf.safe_send(ctx, f"Invalid arg: `{arg}`")
                return

        if set_to:
            config[path.split()[-1]] = literal_eval(set_to)
            await hf.safe_send(ctx, f"```\n{config[path.split()[-1]]}"[:1997]+"```")
            return

        try:
            config = config[process_arg(path.split()[-1])]
        except KeyError:
            await ctx.send(f"Couldn't find {path.split()[-1]} in the database.")
            return
        msg = ''
        for key in config:
            if type(key) == str:
                key_str = f'\"{key}\"'
            else:
                key_str = key
            msg += f"{key_str}\n"

            if int(depth) >= 2:
                if isinstance(config[key], dict):
                    for key_2 in config[key]:
                        if type(key_2) == str:
                            key_2_str = f'\"{key_2}\"'
                        else:
                            key_2_str = key_2
                        msg += f"\t{key_2_str}\n"

                        if int(depth) >= 3:
                            if isinstance(config[key][key_2], dict):
                                for key_3 in config[key][key_2]:
                                    if type(key_3) == str:
                                        key_3_str = f'\"{key_3}\"'
                                    else:
                                        key_3_str = key_3
                                    msg += f"\t\t{key_3_str}\n"

                                    if int(depth) >= 4:
                                        if isinstance(config[key][key_2][key_3], dict):
                                            for key_4 in config[key][key_2][key_3]:
                                                if type(key_4) == str:
                                                    key_4_str = f'\"{key_4}\"'
                                                else:
                                                    key_4_str = key_4
                                                msg += f"\t\t\t{key_4_str}\n"

                                        else:
                                            if type(config[key][key_2][key_3]) == str:
                                                s = f"\"{config[key][key_2][key_3]}\""
                                            else:
                                                s = config[key][key_2][key_3]
                                            msg = msg[:-1] + f": {s}\n"
                            else:
                                if type(config[key][key_2]) == str:
                                    s = f"\"{config[key][key_2]}\""
                                else:
                                    s = config[key][key_2]
                                msg = msg[:-1] + f": {s}\n"
                else:
                    if type(config[key]) == str:
                        s = f"\"{config[key]}\""
                    else:
                        s = config[key]
                    msg = msg[:-1] + f": {s}\n"

        await hf.safe_send(ctx, f'```\n{msg[:1993]}```')

    @commands.command(aliases=['cdb'], hidden=True)
    async def change_database(self, ctx):
        """Change database in some way"""
        config = self.bot.db['stats']
        for guild in config:
            guild_config = config[guild]['voice']['total_time']
            for day in guild_config:
                for user in guild_config[day]:
                    if isinstance(guild_config[day][user], list):
                        guild_config[day][user] = guild_config[day][user][0] * 60 + guild_config[day][user][1]
        print('done')

    @commands.command(hidden=True)
    async def check_voice_users(self, ctx):
        """Checks to see who is currently accumulating voice chat time with the stats module"""
        try:
            config = self.bot.db['stats'][str(ctx.guild.id)]['voice']['in_voice']
            in_voice_users = f'{discord.utils.utcnow()}\n\n'
        except KeyError:
            return
        for user_id in config:
            member = ctx.guild.get_member(int(user_id))
            in_voice_users += f"{member.display_name} - {config[user_id]}\n"
        await hf.safe_send(ctx, in_voice_users)

    @commands.command(hidden=True)
    async def flush(self, ctx):
        """Flushes stderr/stdout"""
        sys.stderr.flush()
        sys.stdout.flush()
        await ctx.message.add_reaction('🚽')

    @commands.command(aliases=['sdb', 'dump'], hidden=True)
    async def savedatabase(self, ctx):
        """Saves the database"""
        await hf.dump_json()
        await ctx.message.add_reaction('\u2705')

    @commands.command(aliases=['rdb'], hidden=True)
    async def reload_database(self, ctx):
        """Reloads the database"""
        with open(f"{dir_path}/db.json", "r") as read_file:
            self.bot.db = json.load(read_file)
        self.bot.ID = self.bot.db["ID"]
        await ctx.message.add_reaction('♻')

    @commands.command(aliases=['rsdb'], hidden=True)
    async def reload_stats(self, ctx):
        """Reloads the messages"""
        with open(f"{dir_path}/stats.json", "r") as read_file:
            self.bot.stats = json.load(read_file)
        await ctx.message.add_reaction('♻')

    @commands.command(hidden=True)
    async def saveMessages(self, ctx):
        """Saves all messages in a channel to a text file"""
        print('Saving messages')
        with codecs.open(f'{ctx.message.channel}_messages.txt', 'w', 'utf-8') as file:
            print('File opened')
            async for msg in ctx.message.channel.history(limit=None, oldest_first=True):
                try:
                    file.write(f'    ({msg.created_at}) {msg.author.name} - {msg.content}\n')
                except UnicodeEncodeError:
                    def BMP(s):
                        return "".join((i if ord(i) < 10000 else '\ufffd' for i in s))

                    file.write(f'    ({msg.created_at}) {BMP(msg.author.name)} - {BMP(msg.content)}\n')

    @commands.command(hidden=True)
    async def restart(self, ctx):
        """Restarts bot"""
        await ctx.message.add_reaction('💀')
        await ctx.invoke(self.flush)
        await ctx.invoke(self.savedatabase)
        self.bot.restart = True
        await self.bot.close()

    @commands.command(aliases=['quit'])
    async def kill(self, ctx):
        """Rai is a killer"""
        try:
            await ctx.message.add_reaction('💀')
            await ctx.invoke(self.flush)
            await ctx.invoke(self.savedatabase)
            await self.bot.close()
            await self.bot.close()
        except Exception as e:
            await hf.safe_send(ctx, f'**`ERROR:`** {type(e).__name__} - {e}')

    @commands.command(hidden=True)
    async def load(self, ctx, *, cog: str):
        """Command which loads a module."""

        try:
            await self.bot.load_extension(f'cogs.{cog}')
        except Exception as e:
            await hf.safe_send(ctx, '**`ERROR:`** {} - {}'.format(type(e).__name__, e))
        else:
            await hf.safe_send(ctx, '**`SUCCESS`**')

    @commands.command(hidden=True)
    async def unload(self, ctx, *, cog: str):
        try:
            await self.bot.unload_extension(f'cogs.{cog}')
        except Exception as e:
            await hf.safe_send(ctx, '**`ERROR:`** {} - {}'.format(type(e).__name__, e))
        else:
            await hf.safe_send(ctx, '**`SUCCESS`**')

    @commands.command(hidden=True)
    async def reload(self, ctx, *, cogs: str):
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        for cog in cogs.split():
            if cog == 'database':
                importlib.reload(sys.modules['cogs.database'])
            if cog in ['hf', 'helper_function']:
                try:
                    old_module = sys.modules['cogs.utils.helper_functions']
                    importlib.reload(sys.modules['cogs.utils.helper_functions'])
                    hf.setup(bot=self.bot, loop=asyncio.get_event_loop())  # this is to define here.bot in the hf file
                except Exception as e:
                    await hf.safe_send(ctx, f'**`ERROR:`** {type(e).__name__} - {e}')
                else:
                    await hf.safe_send(ctx, f'**`{cog}: SUCCESS`**', delete_after=5.0)

            else:
                try:
                    await self.bot.reload_extension(f'cogs.{cog}')
                    if cog == 'interactions':
                        sync = self.bot.get_command('sync')
                        await ctx.invoke(sync)
                except Exception as e:
                    await hf.safe_send(ctx, f'**`ERROR:`** {type(e).__name__} - {e}')
                else:
                    await hf.safe_send(ctx, f' **`{cog}: SUCCESS`**', delete_after=5.0)

    def cleanup_code(self, content):  # credit Danny
        """Automatically removes code blocks from the code."""
        # remove triple quotes + py\n
        if content.startswith("```") and content.endswith("```"):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `single quotes`
        return content.strip('` \n')

    @commands.command(hidden=True)
    async def pp(self, ctx):
        """Checks most active members who are in ping party but not welcoming party yet"""
        print('Checking ping party members')
        JHO = self.bot.get_channel(189571157446492161)
        mCount = {}

        async for m in JHO.history(limit=None, after=datetime.today() - timedelta(days=14)):
            try:
                mCount[m.author] += 1
            except KeyError:
                mCount[m.author] = 1
        print('Done counting messages')
        mSorted = sorted(list(mCount.items()), key=lambda x: x[1], reverse=True)
        mCount = {}
        for memberTuple in mSorted:
            mCount[memberTuple[0].id] = [memberTuple[0].name, memberTuple[1]]
        with open("sorted_members.json", "w") as write_file:
            json.dump(mCount, write_file)

        ping_party_role = next(role for role in JHO.guild.roles if role.id == 357449148405907456)
        welcoming_party_role = next(role for role in JHO.guild.roles if role.id == 250907197075226625)

        ping_party_list = ''
        for member in mSorted:
            # print( member[0].name)
            try:
                if ping_party_role in member[0].roles and welcoming_party_role not in member[0].roles:
                    ping_party_list += f'{member[0].name}: {member[1]}\n'
            except AttributeError:
                print(f'This user left: {member[0].name}: {member[1]}')
        await hf.safe_send(ctx, ping_party_list)

    @commands.command(hidden=True, name='eval')
    async def _eval(self, ctx, *, body: str):
        """Evaluates a code"""

        body = body.replace('self.bot', 'bot')

        env = {
            'bot': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            '_': self._last_result
        }

        env.update(globals())

        body = self.cleanup_code(body)
        #  these are the default quotation marks on iOS, but they cause SyntaxError: invalid character in identifier
        body = body.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await hf.safe_send(ctx, f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await hf.safe_send(ctx, f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    try:
                        await hf.safe_send(ctx, f'```py\n{value}\n```')
                    except discord.HTTPException:
                        st = f'```py\n{value}\n```'
                        await hf.safe_send(ctx, 'Result over 2000 characters')
                        await hf.safe_send(ctx, st[0:1996] + '\n```')
            else:
                self._last_result = ret
                await hf.safe_send(ctx, f'```py\n{value}{ret}\n```')

    @commands.command()
    async def count_emoji(self, ctx):
        """Counts the most commonly used emojis"""
        pattern = re.compile('<a?:[A-Za-z0-9\_]+:[0-9]{17,20}>')
        channel_list = ctx.guild.channels
        emoji_dict = {}
        print('counting')
        for channel in channel_list:
            if isinstance(channel, discord.TextChannel):
                try:
                    async for message in channel.history(limit=None, after=discord.utils.utcnow() - timedelta(days=31)):
                        emoji_list = pattern.findall(message.content)
                        if emoji_list:
                            for emoji in emoji_list:
                                name = emoji.split(':')[1]  # this will strip the ID, and include emojis from other
                                try:  # servers with the same name, which are usually the same emoji too
                                    emoji_dict[name] += 1
                                except KeyError:
                                    emoji_dict[name] = 1
                except discord.Forbidden:
                    pass
        print(emoji_dict)
        sorted_list = sorted(emoji_dict.items(), key=lambda x: x[1], reverse=True)
        print(sorted_list)
        msg1 = ''
        msg2 = ''
        emoji_list = [i.name for i in self.bot.spanServ.emojis]
        print(emoji_list)
        for i in sorted_list:
            name = i[0]
            if name in emoji_list:
                msg1 += f':{name}:: {i[1]}\n'
            else:
                msg2 += f':{name}:: {i[1]}\n'
        print(msg1)
        await hf.safe_send(ctx, msg1)
        print(emoji_dict)
        print(emoji_list)

    @commands.command()
    async def selfMute(self, ctx, hour: float, minute: float):
        """Irreversibly mutes the bot owner for x amount of minutes"""
        self.bot.selfMute = True
        await hf.safe_send(ctx, f'Muting {ctx.author} for {hour} hours and {minute} minutes (he chose to do this).')
        self.bot.selfMute = await asyncio.sleep(hour * 3600 + minute * 60, False)

    @commands.command(aliases=['fd'])
    async def get_left_users(self, ctx):
        print(f'>>finding messages<<')
        channel = self.bot.get_channel(277384105245802497)
        name_to_id = {role.name: role.id for role in channel.guild.roles}
        id_to_role = {role.id: role for role in channel.guild.roles}
        # self.bot.messages = await channel.history(limit=None, after=discord.utils.utcnow() - timedelta(days=60)).flatten()
        config = self.bot.db['joins'][str(channel.guild.id)]['readd_roles']
        config['users'] = {}
        print(len(self.bot.messages))
        for message in self.bot.messages:
            if message.author.id == RYRY_RAI_BOT_ID:
                if message.embeds:
                    try:
                        embed = message.embeds[0]
                    except IndexError:
                        continue
                    if embed.footer.text[0:10] == 'User Leave':
                        USER_ID = embed.description.split('. (')[1][:-1]
                        try:
                            role_name_list = embed.fields[0].value.split(', ')
                        except IndexError:
                            await hf.safe_send(ctx, "Index error failure")
                            return
                        role_id_list = [name_to_id[role] for role in role_name_list]
                        try:
                            role_id_list.remove(309913956061806592)  # in voice role
                        except ValueError:
                            pass
                        try:
                            role_id_list.remove(249695630606336000)  # new user
                        except ValueError:
                            pass
                        if role_id_list:
                            print(USER_ID, embed.fields)
                            config['users'][USER_ID] = [message.created_at.strftime("%Y%m%d"),
                                                        role_id_list]
        print('done')

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        msg = f"""__New guild__
        **Name:** {guild.name}
        **Owner:** {guild.owner.mention} ({str(guild.owner)}))
        **Members:** {guild.member_count}
        **Channels:** {len(guild.text_channels)} text / {len(guild.voice_channels)} voice"""
        # for channel in guild.text_channels:
        #     try:
        #         invite = await channel.create_invite(max_uses=1, reason="For bot owner Ryry013#9234")
        #         msg += f"\n{invite.url}"
        #         break
        #     except discord.HTTPException:
        #         pass
        await self.bot.get_user(self.bot.owner_id).send(msg)
        await self.bot.get_user(self.bot.owner_id).send("Channels: \n" +
                                                         '\n'.join([channel.name for channel in guild.channels]))

        msg_text = "Thanks for inviting me!  See a first-time setup guide here: " \
                   "https://github.com/ryry013/Rai/wiki/First-time-setup"
        if guild.system_channel:
            if guild.system_channel.permissions_for(guild.me).send_messages:
                await guild.system_channel.send(msg_text)
                return
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(msg_text)
                return

    @commands.command()
    async def embed_test(self, ctx, color='FFFF00'):
        """Helps show the fields for embeds"""
        if color[0:2] == '0x':
            color = color[2:]
        em = discord.Embed(
            title='title',
            description='title, description, url, timestamp, color\n'
                        'em.set_footer(), em.set_image(url=), em.set_thumbnail(url=), em.set_author(), em.add_field()',
            url='https://url.com',
            timestamp=discord.utils.utcnow(),
            color=discord.Color(int(color, 16))
        )
        em.set_footer(text='em.set_footer(text=str, icon_url=str)', icon_url='https://i.imgur.com/u6tDx8h.png')
        em.set_image(url='https://i.imgur.com/GcgjR79.png')
        em.set_thumbnail(url='https://i.imgur.com/qwIpWAI.png')
        em.set_author(name='author name', url='https://author.url', icon_url='https://i.imgur.com/QLRBaM4.png')
        em.add_field(name='name=str, value=str, inline=True', value='value', inline=True)
        em.add_field(name='name=str, value=str, inline=False', value='value', inline=False)
        await hf.safe_send(ctx, embed=em)

    @commands.command(aliases=['hk'], hidden=True)
    async def hubkick(self, ctx, user: discord.Member, rule):
        await ctx.message.delete()
        role = ctx.guild.get_role(530669592218042378)
        await user.remove_roles(role)
        await hf.safe_send(user, f"I've removed your member role on the Language Hub server.  Please reread "
                                 f"<#530669247718752266> carefully and then you can rejoin the server."
                                 f"Specifically, {rule}.")

    @commands.command()
    async def ignoreserver(self, ctx, guild_id=None):
        """Ignore for banned users ID check in modserver"""
        if not guild_id:
            guild = ctx.guild
        else:
            try:
                guild = self.bot.get_guild(int(guild_id))
            except ValueError:
                await hf.safe_send(ctx, "Invalid server")
                return
            else:
                if not guild:
                    await hf.safe_send(ctx, "Invalid server")
                    return

        self.bot.db['ignored_servers'].append(guild.id)
        await ctx.message.add_reaction('✅')

    @commands.command()
    async def banserver(self, ctx, guild_id):
        """Ban/blacklist a server from Rai"""
        self.bot.db['bannedservers'].append(guild_id)

        try:
            await ctx.message.add_reaction("✅")
        except discord.Forbidden:
            pass

        guilds = {guild_id: guild for guild in self.bot.guilds}
        if int(guild_id) in guilds:
            await guilds[int(guild_id)].leave()

        try:
            await ctx.message.add_reaction("🗑️")
        except discord.Forbidden:
            pass

    @commands.command(aliases=['ls'])
    async def leaveserver(self, ctx, *, guild_id):
        guilds_in = guild_id.split()
        guilds = {guild.id: guild for guild in self.bot.guilds}
        for guild_id in guilds_in:
            if int(guild_id) in guilds:
                await guilds[int(guild_id)].leave()

                try:
                    await ctx.message.add_reaction("🗑️")
                except discord.Forbidden:
                    pass

            else:
                try:
                    await ctx.message.add_reaction("❓")
                except discord.Forbidden:
                    pass

    @commands.command()
    async def initcontext(self, ctx):
        @self.bot.message_command(guild_ids=[275146036178059265], name="Test 3")
        async def show_id(ctx, message: discord.Message):  # message commands return the message
            await ctx.respond(f"{ctx.author.name}, here'sssssss the message id: {message.id}!")

    @commands.command()
    async def console(self, ctx):
        print("Hello")

    @commands.command()
    async def get_emojis(self, ctx):
        """Saves all emojis in a server to pngs"""
        emojis = ctx.guild.emojis
        index = 1
        if not os.path.exists(f"{dir_path}/emojis/"):
            os.mkdir(f"{dir_path}/emojis/")
        for emoji in emojis:
            with open(f"{dir_path}\emojis\{emoji.name}.png", 'wb') as im:
                await emoji.url.save(im)
            index += 1

    @commands.command()
    async def os(self, ctx, *, command):
        """
        Calls an os command using subprocess.run()
        This version will directly return the results of the command as text
        Command: The command you wish to input into your system
        """
        result = run(command,
                     stdout=PIPE,
                     stderr=PIPE,
                     universal_newlines=True,
                     shell=True)
        result = f"{result.stdout}\n{result.stderr}"
        long = len(result) > 1994
        short_result = result[:1994]
        short_result = f"```{short_result}```"

        await hf.safe_send(ctx, short_result)

        if long:
            buffer = io.BytesIO(bytes(result, "utf-8"))
            f = discord.File(buffer, filename="text.txt")
            await ctx.send("Result was over 2000 characters", file=f)

    @commands.command()
    async def joindate(self, ctx, user, jump_url):
        """
        Adds a user to the manual join date database if you link to their first message with a jump url
        """
        user_id = re.findall(r"<?@?!?(\d{17,22})>?", user)  # a list containing the IDs in user
        if user_id:
            user_id = user_id[0]  # get the ID
        else:
            await hf.safe_send(ctx, "Failed to parse user")
            return

        channel_message_id = re.findall(r"https:\/\/(?:.*\.)?.*\.com\/channels\/\d{17,22}\/(\d{17,22})\/(\d{17,22})",
                                        jump_url)
        if channel_message_id:
            channel_id = int(channel_message_id[0][0])
            message_id = int(channel_message_id[0][1])
        else:
            await hf.safe_send(ctx, "Failed to parse jump url")
            return

        channel = self.bot.get_channel(channel_id)
        message = await channel.fetch_message(message_id)

        new_join_date_timestamp = message.created_at.timestamp()
        self.bot.db['joindates'][user_id] = new_join_date_timestamp

        await hf.safe_send(ctx, embed=hf.green_embed(f"Set new join date for <@{user_id}> to "
                                                     f"<t:{int(new_join_date_timestamp)}:f>"))

    @commands.command()
    async def network(self, ctx: commands.Context):
        """Resets the network on my pi"""
        os.system("sudo /etc/init.d/networking restart")
        await ctx.message.add_reaction("✅")

    @commands.command()
    async def raise_error(self, ctx):
        """Raises an error for testing purposes"""
        raise Exception


async def setup(bot):
    await bot.add_cog(Owner(bot))
