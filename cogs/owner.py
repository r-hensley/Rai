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
from collections import Counter, deque
from ast import literal_eval
from datetime import datetime, timedelta, timezone
from subprocess import PIPE, run, TimeoutExpired
from contextlib import redirect_stdout
from typing import Union

import discord
from discord.ext import commands
from matplotlib import pyplot as plt, cm
from matplotlib.colors import Normalize

from cogs.utils.BotUtils import bot_utils as utils
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
        # If it's Ryry's Rai bot
        if self.bot.user.id in [RYRY_RAI_BOT_ID, RAI_TEST_BOT_ID]:
            return ctx.author.id in [RYRY_ID, ABELIAN_ID, MARIO_RYAN_ID, UNITARITY_ID]
        else:
            return ctx.author.id == self.bot.owner_id

    @commands.command()
    async def guildstats(self, ctx):
        """Checks stats on various guilds that the bot is on"""
        config = self.bot.db['guildstats']
        guild_info = {}
        id_to_guild = {str(g.id): g for g in self.bot.guilds}
        for guild_id in config.copy():
            message_count = 0
            for day in config[guild_id]['messages'].copy():
                days_ago = (discord.utils.utcnow() - datetime.strptime(day,
                            "%Y%m%d").replace(tzinfo=timezone.utc)).days
                if days_ago > 30:
                    del config[guild_id]['messages'][day]
                else:
                    message_count += config[guild_id]['messages'][day]

            command_count = 0
            for day in config[guild_id]['commands'].copy():
                days_ago = (discord.utils.utcnow() - datetime.strptime(day,
                            "%Y%m%d").replace(tzinfo=timezone.utc)).days
                if days_ago > 30:
                    del config[guild_id]['commands'][day]
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
                f"{round(info['humans'] / info['member_count'], 2)})" \
                f"\n{info['commands']} commands\n"
            if len(msg + msg_addition) < 2000:
                msg += msg_addition
            else:
                await utils.safe_send(ctx, msg)
                msg = msg_addition
        if msg:
            await utils.safe_send(ctx, msg)

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
                await utils.safe_send(ctx, msg)
                msg = msg_addition
        if msg:
            await utils.safe_send(ctx, msg)

    @commands.command()
    async def edit(self, ctx, message_id, *, content):
        """Edits a message from Rai"""
        try:
            msg = await ctx.channel.fetch_message(int(message_id))
        except discord.NotFound:
            await utils.safe_send(ctx, "Message not found")
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
        index_re = re.search(r"^(;repl|;reply) (\d) ", ctx.message.content)
        if not index_re:
            reply = f"{index} {reply}"
            index = 1
        else:
            index = int(index_re.group(2))
            if not reply:
                await utils.safe_send(ctx, "Include reply message")

        async for msg in channel.history():
            result_channel_id = re.search(
                rf'^(\d{17, 22}) <@{self.bot.owner_id}>$', msg.content)
            if not result_channel_id:
                continue
            else:
                result_channel_id = result_channel_id.group(1)
            if result_channel_id:
                if (discord.utils.utcnow() - msg.created_at).seconds > 1:
                    if index > 1:
                        index -= 1
                    else:
                        send_channel = self.bot.get_channel(
                            int(result_channel_id))
                        try:
                            await send_channel.send(reply)
                        except discord.Forbidden as e:
                            await utils.safe_send(ctx, e)
                        return

    @commands.command(aliases=['db'])
    async def database(self, ctx, depth: int = 1, *, path: str = ""):
        """
        Command to preview the structure of the bot's database.
        This helps in understanding the hierarchical structure without focusing on the actual data.

        :param ctx: The context of the command invocation.
        :param depth: The depth of database hierarchy to preview (default is 1).
        :param path: The starting path in the database to explore.
        """
        try:
            # Validate depth
            if depth < 1 or depth > 4:
                await ctx.send("Depth must be between 1 and 4.")
                return

            async def validate_path(_path):
                _config = self.bot.db
                if _path:
                    keys = _path.split()
                    for key in keys:
                        # if I pass a key like "ctx.guild.id", return the actual value of ctx.guild.id as a str
                        if key.startswith("ctx"):
                            try:
                                key = str(literal_eval(key))
                            except Exception as e:
                                await ctx.send(f"An error occurred: {e}")
                                return
                        _config = _config.get(key)
                        if _config is None:
                            await ctx.send(f"Path '{' '.join(keys[:keys.index(key) + 1])}' does not exist in the database.")
                            return
                return _config

            config = await validate_path(path)

            # Function to recursively extract keys up to the specified depth
            def extract_structure(data, current_depth):
                if current_depth > depth:
                    if isinstance(data, dict):
                        return "{...}"
                    elif isinstance(data, list):
                        return "[...]"
                    else:
                        return "..."

                _structure = {}
                cutoff = 3
                key: str  # in my database, the dict keys are always strings
                value: Union[dict, list, int, str, bool]
                for i, (key, value) in enumerate(data.items()):
                    if len(data) > 10:
                        cutoff_here = cutoff
                    else:
                        cutoff_here = len(data)
                    if i >= cutoff_here:  # Limit to cutoff # of elements per level
                        _structure[f"...{len(data) - cutoff} more"] = "..."
                        break
                    if isinstance(value, dict):
                        _structure[key] = extract_structure(
                            value, current_depth + 1) or "{...}"
                    elif isinstance(value, list):
                        preview = [
                            extract_structure(
                                item, current_depth + 1) if isinstance(item, (dict, list)) else "..."
                            for item in value[:2]
                        ]
                        if len(value) > 2:
                            preview.append(f"...{len(value) - 2} more items")
                        _structure[key] = preview
                    elif isinstance(value, str):
                        _structure[key] = value[:35] + \
                            "..." if len(value) > 35 else value
                    else:
                        # Non-dict value, probably str, int, bool
                        _structure[key] = value
                return _structure

            # Extract the structure and format for display
            structure = extract_structure(config, 1)
            if structure is None:
                await ctx.send("The path exists but contains no data to display.")
                return

            # Use JSON for pretty printing
            formatted_structure = json.dumps(structure, indent=2)

            # Split the output into chunks Discord can send
            chunks = utils.split_text_into_segments(formatted_structure, 1900)
            for _i, chunk in enumerate(chunks[:3]):
                await ctx.send(f"```json\n{chunk}```")
            if len(chunks) > 3:
                await ctx.send("Output truncated. Showing only the first 3 messages.")

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")

    @commands.command(aliases=['cdb'], hidden=True)
    async def change_database(self, _):
        """Change database in some way; modify this command each time it needs to be ran"""
        run_command = False
        if run_command:
            config = self.bot.db['stats']
            for guild in config:
                guild_config = config[guild]['voice']['total_time']
                for day in guild_config:
                    for user in guild_config[day]:
                        if isinstance(guild_config[day][user], list):
                            guild_config[day][user] = guild_config[day][user][0] * \
                                60 + guild_config[day][user][1]
            print('done')
        else:
            print('Command not run')

    @commands.command(hidden=True)
    async def check_voice_users(self, ctx):
        """Checks to see who is currently accumulating voice chat time with the stats module"""
        try:
            config = self.bot.db['stats'][str(
                ctx.guild.id)]['voice']['in_voice']
            in_voice_users = f'{discord.utils.utcnow()}\n\n'
        except KeyError:
            return
        for user_id in config:
            member = ctx.guild.get_member(int(user_id))
            in_voice_users += f"{member.display_name} - {config[user_id]}\n"
        await utils.safe_send(ctx, in_voice_users)

    @commands.command(hidden=True)
    async def flush(self, ctx):
        """Flushes stderr/stdout"""
        sys.stderr.flush()
        sys.stdout.flush()
        await ctx.message.add_reaction('🚽')

    @commands.command(aliases=['sdb', 'dump'], hidden=True)
    async def savedatabase(self, ctx):
        """Saves the database"""
        await utils.dump_json('db')
        await utils.dump_json('stats')
        await utils.dump_json('message_queue')
        await ctx.message.add_reaction('\u2705')

    @commands.command(aliases=['rdb'], hidden=True)
    async def reload_database(self, ctx):
        """Reloads the database"""
        with open(f"{dir_path}/db.json", "r", encoding='utf-8') as read_file:
            self.bot.db = json.load(read_file)
        self.bot.ID = self.bot.db["ID"]
        await ctx.message.add_reaction('♻')

    @commands.command(aliases=['rsdb'], hidden=True)
    async def reload_stats(self, ctx):
        """Reloads the messages"""
        with open(f"{dir_path}/stats.json", "r", encoding='utf-8') as read_file:
            self.bot.stats = json.load(read_file)
        await ctx.message.add_reaction('♻')

    @commands.command(hidden=True)
    async def save_messages(self, ctx):
        """Saves all messages in a channel to a text file"""
        print('Saving messages')
        with codecs.open(f'{ctx.message.channel}_messages.txt', 'w', 'utf-8') as file:
            print('File opened')
            async for msg in ctx.message.channel.history(limit=None, oldest_first=True):
                try:
                    file.write(
                        f'    ({msg.created_at}) {msg.author.name} - {msg.content}\n')
                except UnicodeEncodeError:
                    def bmp(s):
                        return "".join((i if ord(i) < 10000 else '\ufffd' for i in s))

                    file.write(
                        f'    ({msg.created_at}) {bmp(msg.author.name)} - {bmp(msg.content)}\n')

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
            await utils.safe_send(ctx, f'**`ERROR:`** {type(e).__name__} - {e}')

    @commands.command(hidden=True)
    async def load(self, ctx, *, cog: str):
        """Command which loads a module."""

        try:
            await self.bot.load_extension(f'cogs.{cog}')
        except Exception as e:
            await utils.safe_send(ctx, f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await utils.safe_send(ctx, '**`SUCCESS`**')

    @commands.command(hidden=True)
    async def unload(self, ctx, *, cog: str):
        try:
            await self.bot.unload_extension(f'cogs.{cog}')
        except Exception as e:
            await utils.safe_send(ctx, f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await utils.safe_send(ctx, '**`SUCCESS`**')

    @commands.command(hidden=True)
    async def reload(self, ctx, *, cogs: str):
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        for cog in cogs.split():
            if cog == 'database':
                importlib.reload(sys.modules['cogs.database'])
            if cog == 'rl':
                cog = 'rl.rl'
            if cog in ['hf', 'helper_function']:
                try:
                    importlib.reload(
                        sys.modules['cogs.utils.helper_functions'])
                except Exception as e:
                    await self.reload_error(ctx, cog, e)
                else:
                    # this is to define here.bot in the hf file
                    hf.setup(bot=self.bot, loop=asyncio.get_event_loop())
                    if hasattr(self.bot, "profiling_decorators"):
                        # looks like cogs.message, cogs.events, etc
                        decorators = self.bot.profiling_decorators.copy()
                        # reset set to allow potentially for removal of old ones
                        self.bot.profiling_decorators = set()
                        for decorator_cog in decorators:
                            try:
                                await self.bot.reload_extension(decorator_cog)
                            except Exception as e:
                                await self.reload_error(ctx, decorator_cog, e)
                            else:
                                await utils.safe_send(ctx,
                                                      f'**`{decorator_cog}: SUCCESS`** (decorator follow-up)',
                                                      delete_after=5.0)

                    await self.reload_success(ctx, cog)

            elif cog == 'utils':
                # reload file in cogs/utils/BotUtils/bot_utils.py
                try:
                    importlib.reload(
                        sys.modules['cogs.utils.BotUtils.bot_utils'])
                    utils.setup(bot=self.bot, loop=asyncio.get_event_loop())
                except Exception as e:
                    await self.reload_error(ctx, cog, e)
                else:
                    await self.reload_success(ctx, cog)

            else:
                try:
                    await self.bot.reload_extension(f'cogs.{cog}')
                    if cog == 'interactions':
                        sync = self.bot.get_command('sync')
                        await ctx.invoke(sync)
                except Exception as e:
                    print(ctx, cog, e)
                    await self.reload_error(ctx, cog, e)
                else:
                    await self.reload_success(ctx, cog)

    @staticmethod
    async def reload_success(ctx, cog):
        await utils.safe_send(ctx, f'**`{cog}: SUCCESS`**', delete_after=5.0)

    @staticmethod
    async def reload_error(ctx, cog, e):
        err = traceback.format_exc()
        err_first_line = f'{cog} - **`ERROR:`** {type(e).__name__} - {e}\n'
        remaining_char = 1990 - len(err_first_line)
        err = err_first_line + f"```py\n{err[:remaining_char]}```"
        await utils.safe_send(ctx, err)

    @staticmethod
    def cleanup_code(content):  # credit Danny
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
        mSorted = sorted(list(mCount.items()),
                         key=lambda x: x[1], reverse=True)
        mCount = {}
        for memberTuple in mSorted:
            mCount[memberTuple[0].id] = [memberTuple[0].name, memberTuple[1]]
        with open("sorted_members.json", "w", encoding='utf-8') as write_file:
            json.dump(mCount, write_file)

        ping_party_role = next(
            role for role in JHO.guild.roles if role.id == 357449148405907456)
        welcoming_party_role = next(
            role for role in JHO.guild.roles if role.id == 250907197075226625)

        ping_party_list = ''
        for member in mSorted:
            # print( member[0].name)
            try:
                if ping_party_role in member[0].roles and welcoming_party_role not in member[0].roles:
                    ping_party_list += f'{member[0].name}: {member[1]}\n'
            except AttributeError:
                print(f'This user left: {member[0].name}: {member[1]}')
        await utils.safe_send(ctx, ping_party_list)

    @commands.command(hidden=True, name='eval')
    async def _eval(self, ctx: commands.Context, *, body: str):
        # noinspection PyTypeChecker
        await ctx.invoke(self.eval_internal, seconds=15, body=body)

    @commands.command(hidden=True, name='longeval')
    async def _longeval(self, ctx: commands.Context, time, *, body: str):
        try:
            seconds = int(time)
        except ValueError:
            # length is a list of ints [days, hours, minutes]
            _, length = hf.parse_time(time)
            seconds = length[0] * 86400 + length[1] * 3600 + length[2] * 60
        # noinspection PyTypeChecker
        await ctx.invoke(self.eval_internal, seconds=seconds, body=body)

    async def eval_internal(self, ctx, seconds, body: str):
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
        body = body.replace("“", '"').replace(
            "”", '"').replace("‘", "'").replace("’", "'")
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}\n'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await utils.safe_send(ctx, f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        # noinspection PyBroadException
        try:
            ret = None
            with redirect_stdout(stdout):
                ret = await asyncio.wait_for(func(), seconds)
        except asyncio.TimeoutError:
            await utils.safe_send(ctx, 'Evaluation timed out.')
        except Exception as _:
            value = stdout.getvalue()
            to_send = f'\n{value}{traceback.format_exc()}\n'
            to_send_segments = utils.split_text_into_segments(to_send, 1990)
            for segment in to_send_segments[:5]:
                await utils.safe_send(ctx, f'```py\n{segment}\n```')
            if len(to_send_segments) > 5:
                await utils.safe_send(ctx, "Output truncated. Showing only the first 5 messages.")
            return
        finally:
            value = stdout.getvalue()
            # noinspection PyBroadException
            try:
                await ctx.message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    segments = utils.split_text_into_segments(value, 1990)
                    for segment in segments[:5]:
                        await utils.safe_send(ctx, f'```py\n{segment}\n```')
                    if len(segments) > 5:
                        await utils.safe_send(ctx, "Output truncated. Showing only the first 5 messages.")
            else:
                self._last_result = ret
                segments = utils.split_text_into_segments(
                    f"{value}{ret}", 1990)
                for segment in segments[:5]:
                    await utils.safe_send(ctx, f'```py\n{segment}\n```')
                if len(segments) > 5:
                    await utils.safe_send(ctx, "Output truncated. Showing only the first 5 messages.")

    @commands.command()
    async def count_emoji(self, ctx):
        """Counts the most commonly used emojis"""
        pattern = re.compile('<a?:[A-Za-z0-9_]+:[0-9]{17,20}>')
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
                                # this will strip the ID, and include emojis from other
                                name = emoji.split(':')[1]
                                try:  # servers with the same name, which are usually the same emoji too
                                    emoji_dict[name] += 1
                                except KeyError:
                                    emoji_dict[name] = 1
                except discord.Forbidden:
                    pass
        print(emoji_dict)
        sorted_list = sorted(emoji_dict.items(),
                             key=lambda x: x[1], reverse=True)
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
        await utils.safe_send(ctx, msg1)
        print(emoji_dict)
        print(emoji_list)

    @commands.command(hidden=True)
    async def self_mute_owner(self, ctx, time: str):
        """Irreversibly mutes the bot owner for x amount of minutes"""
        _, (days, hours, minutes) = hf.parse_time(time)
        hours += days * 24
        self.bot.selfMute = True
        await utils.safe_send(ctx, f'Muting {ctx.author} for {hours} hours and {minutes} minutes (he chose to do this).')
        self.bot.selfMute = await asyncio.sleep(hours * 3600 + minutes * 60, False)

    @commands.command(aliases=['fd'])
    async def get_left_users(self, ctx):
        print('>>finding messages<<')
        channel = self.bot.get_channel(277384105245802497)
        name_to_id = {role.name: role.id for role in channel.guild.roles}
        # id_to_role = {role.id: role for role in channel.guild.roles}
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
                            await utils.safe_send(ctx, "Index error failure")
                            return
                        role_id_list = [name_to_id[role]
                                        for role in role_name_list]
                        try:
                            role_id_list.remove(
                                309913956061806592)  # in voice role
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
        em.set_footer(text='em.set_footer(text=str, icon_url=str)',
                      icon_url='https://i.imgur.com/u6tDx8h.png')
        em.set_image(url='https://i.imgur.com/GcgjR79.png')
        em.set_thumbnail(url='https://i.imgur.com/qwIpWAI.png')
        em.set_author(name='author name', url='https://author.url',
                      icon_url='https://i.imgur.com/QLRBaM4.png')
        em.add_field(name='name=str, value=str, inline=True',
                     value='value', inline=True)
        em.add_field(name='name=str, value=str, inline=False',
                     value='value', inline=False)
        await utils.safe_send(ctx, embed=em)

    @commands.command(aliases=['hk'], hidden=True)
    async def hubkick(self, ctx, user: discord.Member, rule):
        await ctx.message.delete()
        role = ctx.guild.get_role(530669592218042378)
        await user.remove_roles(role)
        await utils.safe_send(user, f"I've removed your member role on the Language Hub server.  Please reread "
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
                await utils.safe_send(ctx, "Invalid server")
                return
            else:
                if not guild:
                    await utils.safe_send(ctx, "Invalid server")
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
    async def console(self, _):
        print("Hello")

    @commands.command()
    async def get_emojis(self, ctx):
        """Saves all emojis in a server to pngs"""
        emojis = ctx.guild.emojis
        index = 1
        if not os.path.exists(f"{dir_path}/emojis/"):
            os.mkdir(f"{dir_path}/emojis/")
        for emoji in emojis:
            with open(rf"{dir_path}\emojis\{emoji.name}.png", 'wb') as im:
                await emoji.url.save(im)
            index += 1

    @commands.command()
    async def os(self, ctx, *, command):
        """
        Calls an os command using subprocess.run()
        This version will directly return the results of the command as text
        Command: The command you wish to input into your system
        """
        try:
            result = run(command,
                         stdout=PIPE,
                         stderr=PIPE,
                         universal_newlines=True,
                         shell=True,
                         timeout=15,
                         check=False)
        except TimeoutExpired:
            await utils.safe_send(ctx, "Command timed out")
            return
        result = f"{result.stdout}\n{result.stderr}"
        long = len(result) > 1994
        short_result = result[:1994]
        short_result = f"```{short_result}```"

        await utils.safe_send(ctx, short_result)

        if long:
            buffer = io.BytesIO(bytes(result, "utf-8"))
            f = discord.File(buffer, filename="text.txt")
            await ctx.send("Result was over 2000 characters", file=f)

    @commands.command()
    async def joindate(self, ctx, user, jump_url):
        """
        Adds a user to the manual join date database if you link to their first message with a jump url
        """
        user_id = re.findall(
            r"<?@?!?(\d{17,22})>?", user)  # a list containing the IDs in user
        if user_id:
            user_id = user_id[0]  # get the ID
        else:
            await utils.safe_send(ctx, "Failed to parse user")
            return

        channel_message_id = re.findall(r"https://(?:.*\.)?.*\.com/channels/\d{17,22}/(\d{17,22})/(\d{17,22})",
                                        jump_url)
        if channel_message_id:
            channel_id = int(channel_message_id[0][0])
            message_id = int(channel_message_id[0][1])
        else:
            await utils.safe_send(ctx, "Failed to parse jump url")
            return

        channel = self.bot.get_channel(channel_id)
        message = await channel.fetch_message(message_id)

        new_join_date_timestamp = message.created_at.timestamp()
        self.bot.db['joindates'][user_id] = new_join_date_timestamp

        await utils.safe_send(ctx, embed=utils.green_embed(f"Set new join date for <@{user_id}> to "
                                                           f"<t:{int(new_join_date_timestamp)}:f>"))

    @commands.command()
    async def network(self, ctx: commands.Context):
        """Resets the network on my pi"""
        os.system("sudo /etc/init.d/networking restart")
        await ctx.message.add_reaction("✅")

    @commands.command()
    async def raise_error(self, _):
        """Raises an error for testing purposes"""
        print("raising error")
        x = 1 / 0

    @commands.command()
    async def spybotcheck(self, ctx, url="https://gist.githubusercontent.com/Dziurwa14/"
                                         "05db50c66e4dcc67d129838e1b9d739a/raw/spy.pet%2520accounts"):
        id_list_str = await utils.aiohttp_get_text(ctx, url)
        if not id_list_str:
            await utils.safe_send(ctx, "Failed to get list")
            return
        # Extracts integers within double quotes
        id_list = re.findall(r'"(\d+)"', id_list_str)

        await utils.safe_send(ctx, f"Checking from this list: {url}")
        for guild in self.bot.guilds:
            member_ids = [str(member.id) for member in guild.members]
            for account in id_list:
                if account in member_ids:
                    await utils.safe_send(ctx, f"{account} is in {guild.name}")
        await utils.safe_send(ctx, "Done")

    @commands.command()
    async def queue(self, ctx):
        """Prints information about the messages deque: self.bot.messages_queue"""
        queue: hf.MessageQueue = self.bot.message_queue
        # the __repr__ method produces some good info, but there it is constricted greatly for readability.
        # Here, expand a bit more with more space, better formatting, and more info.
        # __repr__ gives: <MessageQueue: 2453 messages ー 45m depth ー 858.61 KB (358.42 B/msg, 33.1 char/msg)>
        bot_cache_len = len(self.bot.cached_messages)
        bot_cache_depth = hf.format_interval(
            self.bot.cached_messages[-1].created_at - self.bot.cached_messages[0].created_at)
        msg = f"Queue length: {len(queue)} (bot len: {bot_cache_len})\n"
        msg += f"Queue depth: {queue.depth} (bot depth: {bot_cache_depth})\n"
        msg += f"Queue size: {queue.memory_usage}\n"

        # calculate the top five most common guilds
        guild_count = Counter()
        for message in queue:
            guild_count[message.guild_id] += 1

        guild_count = guild_count.most_common(10)
        msg += "Top 10 guilds:\n"
        for guild_id, count in guild_count:
            guild = self.bot.get_guild(guild_id)
            percentage = count / len(queue) * 100
            msg += f"- {guild.name} ({percentage:.2f}%): {count}\n"

        await utils.safe_send(ctx, msg)

    @commands.command(aliases=['queue_reload', 'reloadqueue'])
    async def reload_queue(self, ctx):
        """Reloads the message queue in the case that I've changed the code inside the message queue class definition"""
        self.bot.message_queue = hf.MessageQueue(self.bot.message_queue)
        await ctx.message.add_reaction("✅")

    @commands.command(aliases=['reloadqueuemessages', 'rqm'])
    async def reload_queue_messages(self, ctx):
        """Reloads all the message objects in a queue"""
        new_message_queue = hf.MessageQueue(
            maxlen=self.bot.message_queue.maxlen)
        for message in self.bot.message_queue:
            new_message_queue.append(hf.MiniMessage.from_mini_message(message))
        self.bot.message_queue = new_message_queue
        await ctx.message.add_reaction("✅")

    @commands.command()
    async def mostbansdate(self, ctx: commands.Context):
        """Finds the date of the most bans"""
        _seven_days_ago = discord.utils.utcnow() - timedelta(days=7)
        daily_bans = Counter()

        # save bans locally, so I don't keep spamming audit log
        if not hasattr(self.bot, 'ban_log_history'):
            self.bot.ban_log_history = []

        # Fetch bans and count per day
        last_date = None
        processed_count = 0
        modlog_channel = self.bot.get_channel(598367270678560780)
        if not self.bot.ban_log_history:
            async for message in modlog_channel.history(limit=None, oldest_first=False):
                processed_count += 1
                if not message.embeds:
                    continue
                if "was `banned`" not in (message.embeds[0].description or ''):
                    continue
                if message.created_at.year not in [2022, 2023, 2024]:
                    break
                self.bot.ban_log_history.append(message.id)
                ban_date = message.created_at.strftime("%m%d")
                if ban_date != last_date:
                    print(
                        f"[{processed_count}] Processing bans for {message.created_at.year}{ban_date}")
                    ban_count_last_day = daily_bans[last_date] if last_date else 0
                    if ban_count_last_day > 20:
                        print(
                            f"Detected a day with {ban_count_last_day} bans: {last_date}")
                    last_date = ban_date
                daily_bans[ban_date] += 1
        else:
            print("Using cached ban log history")
            bans_this_day = 0
            for message_id in self.bot.ban_log_history:
                processed_count += 1
                ban_date = discord.utils.snowflake_time(message_id)
                if ban_date.year not in [2024]:
                    continue
                if not last_date:
                    last_date = ban_date
                bans_this_day += 1
                if ban_date.day != last_date.day:
                    ban_date_str = last_date.strftime("%m%d")
                    if bans_this_day < 50:  # ignore outlier days
                        daily_bans[ban_date_str] += bans_this_day
                    bans_this_day = 0
                    last_date = ban_date

        # sort daily_bans by date
        daily_bans = dict(sorted(daily_bans.items(), key=lambda item: item[0]))

        # Plot data
        days = list(daily_bans.keys())
        counts = [daily_bans[day] for day in days]

        # Calculate 7-day running average. For values at end of list, just loop back to beginning
        running_avg = []
        avg_calculator = deque([counts[0]] * 7, maxlen=7)

        for day, count in zip(days, counts):
            avg_calculator.append(count)
            running_avg.append(sum(avg_calculator) / 7)
        assert len(running_avg) == len(days) == len(counts), (f"Length mismatch: "
                                                              f"{len(running_avg)=}, {len(days)=}, {len(counts)=}")

        norm = Normalize(vmin=min(counts), vmax=max(counts))
        colors = cm.viridis(norm(counts))  # Use a colormap (e.g., viridis)

        fig, ax = plt.subplots(figsize=(10, 6))  # Adjust figure size
        fig: plt.Figure
        ax: plt.Axes
        ax.bar(days, running_avg, color=colors,
               label="Daily Bans (7 day average)", alpha=0.6)
        ax.set_xlabel("Date (MMDD)")
        step = max(len(days) // 7, 1)
        ax.set_xticks(ticks=range(0, len(days), step), labels=[
                      days[i] for i in range(0, len(days), step)], rotation=70)
        ax.set_ylabel("Number of Bans")
        ax.set_title("Ban Counts (Rolling Average)")
        sm = cm.ScalarMappable(norm=norm, cmap=cm.viridis)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax)
        cbar.set_label("Number of Bans")
        plt.tight_layout()

        # Save and send the plot
        with io.BytesIO() as plot_buffer:
            plt.savefig(plot_buffer, format="png")
            plot_buffer.seek(0)
            await ctx.send(file=discord.File(plot_buffer, "bans_plot.png"))
        plt.close()

    @commands.command()
    async def summarize(self, ctx: commands.Context, limit_jump_url: str = None, limit_message_number: Union[int] = 500):
        """Summarizes a conversation using OpenAI's GPT-4"""
        if not self.bot.openai:
            await utils.safe_reply(ctx, "OpenAI not initialized")
            return

        re_result = re.findall(
            r"https://(?:.*\.)?.*\.com/channels/\d{17,22}/(\d{17,22})/(\d{17,22})", limit_jump_url)
        if not re_result:
            await utils.safe_reply(ctx, "Invalid message link. Please give a message link to the message from which you want to "
                                        "summarize")
        channel_id = int(re_result[0][0])
        message_id = int(re_result[0][1])
        channel = self.bot.get_channel(channel_id)
        first_message = await channel.fetch_message(message_id)
        messages = [{"role": "developer",
                     "content": "Please summarize the main points of the conversation given, including the main points of each user. "
                                "Assume there is some important conversation happening, so if it ever looks like there's parts of "
                                "the conversations that get off topic or parts of the conversation where people get sidetracked "
                                "with casual conversation, please ignore those parts. Keep the answer very concise. For a debate or "
                                "discussion, summarize each party's main points with bullet points. If any conclusions were reached, "
                                "specify the conclusion. If the conversation involves messages from 'DM Modbot', messages starting with "
                                "'_' are private messages among moderators that don't get sent to the user."}]
        total_len = 0
        last_message = None
        async for message in ctx.channel.history(limit=limit_message_number, after=first_message.created_at, oldest_first=True):
            content = f"{message.author.display_name}: {message.content}"
            total_len += len(content)
            last_message = message
            messages.append({"role": "user", "content": content})

        await utils.safe_reply(ctx, f"Summarizing {len(messages)} messages from "
                               f"{first_message.jump_url} ({first_message.content[:50]}...)"
                               f"to {last_message.jump_url} ({last_message.content[:50]}...)")

        await hf.send_to_test_channel(messages)
        try:
            completion = await self.bot.openai.chat.completions.create(model="gpt-4o", messages=messages)
        except Exception as e:
            await hf.send_to_test_channel(f"Error: `{e}`\n{messages}")
            raise
        to_send = utils.split_text_into_segments(
            completion.choices[0].message.content, 2000)
        for m in to_send:
            await utils.safe_reply(ctx, m)


async def setup(bot):
    await bot.add_cog(Owner(bot))
