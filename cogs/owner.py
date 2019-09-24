from discord.ext import commands
import asyncio
import traceback
import discord
import textwrap
from contextlib import redirect_stdout
import io
import sys
import codecs
import json
from .utils import helper_functions as hf
import re
from ast import literal_eval

# to expose to the eval command
import datetime
from datetime import datetime, timedelta

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

RYRY_SPAM_CHAN = 275879535977955330


class Owner(commands.Cog):
    # various code from https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/admin.py in here, thanks

    def __init__(self, bot):
        self.bot = bot
        self._last_result = None
        self.sessions = set()

    async def cog_check(self, ctx):
        return ctx.author.id in [202995638860906496, 414873201349361664, 528770932613971988]

    def get_syntax_error(self, e):
        if e.text is None:
            return f'```py\n{e.__class__.__name__}: {e}\n```'
        return f'```py\n{e.text}{"^":>{e.offset}}\n{e.__class__.__name__}: {e}```'

    @commands.command()
    async def send(self, ctx, channel_id: int, *, msg):
        """Sends a message to the channel ID specified"""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            channel = self.bot.get_user(channel_id)
            if not channel:
                await hf.safe_send(ctx, "Invalid ID")
                return
        await channel.send(msg)
        await ctx.message.add_reaction("✅")

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
        channel = self.bot.get_channel(RYRY_SPAM_CHAN)
        index_re = re.search("^(;repl|;reply) (\d) ", ctx.message.content)
        if not index_re:
            reply = f"{index} {reply}"
            index = 1
        else:
            index = int(index_re.group(2))
            if not reply:
                await hf.safe_send(ctx, "Include reply message")

        async for msg in channel.history():
            result_channel_id = re.search('^(\d{17,22}) <@202995638860906496>$', msg.content)
            if not result_channel_id:
                continue
            else:
                result_channel_id = result_channel_id.group(1)
            if result_channel_id:
                if (datetime.utcnow() - msg.created_at).seconds > 1:
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
            msg += f"{key}\n"

            if int(depth) >= 2:
                if isinstance(config[key], dict):
                    for key_2 in config[key]:
                        msg += f"\t{key_2}\n"

                        if int(depth) >= 3:
                            if isinstance(config[key][key_2], dict):
                                for key_3 in config[key][key_2]:
                                    msg += f"\t\t{key_3}\n"

                                    if int(depth) >= 4:
                                        if isinstance(config[key][key_2][key_3], dict):
                                            for key_4 in config[key][key_2][key_3]:
                                                msg += f"\t\t\t{key_4}\n"

                                        else:
                                            msg = msg[:-1] + f": {config[key][key_2][key_3]}\n"
                            else:
                                msg = msg[:-1] + f": {config[key][key_2]}\n"
                else:
                    msg = msg[:-1] + f": {config[key]}\n"

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

    @commands.command()
    async def check_voice_users(self, ctx):
        """Checks to see who is currently accumulating voice chat time with the stats module"""
        try:
            config = self.bot.db['stats'][str(ctx.guild.id)]['voice']['in_voice']
            in_voice_users = f'{datetime.utcnow()}\n\n'
        except KeyError:
            return
        for user_id in config:
            member = ctx.guild.get_member(int(user_id))
            in_voice_users += f"{member.display_name} - {config[user_id]}\n"
        await hf.safe_send(ctx, in_voice_users)

    @commands.command()
    async def flush(self, ctx):
        """Flushes stderr/stdout"""
        sys.stderr.flush()
        sys.stdout.flush()
        await ctx.message.add_reaction('🚽')

    # @commands.command(aliases=['elt'])
    # async def embed_len_test(self, ctx, length: int):
    #     author = ctx.author
    #     time_dif = '3.5'
    #     emb = discord.Embed(
    #         description=f'**{author.name}#{author.discriminator}** ({author.id})'
    #                     f'\n**Message edited after {time_dif} seconds.**',
    #         colour=0xFF9933,
    #         timestamp=datetime.utcnow()
    #     )
    #     x = 'a'*length
    #
    #     emb.add_field(name='**Before:**', value=f'{x}')
    #     emb.add_field(name='**After:**', value=f'{x}')
    #     emb.add_field(name='**After again!**', value=f'{x}')
    #     emb.add_field(name='**After again!**', value=f'{x}')
    #     emb.add_field(name='**After again!**', value=f'{x}')
    #     emb.add_field(name='**After again!**', value=f'{x}')
    #     emb.add_field(name='**After again!**', value=f'{x}')
    #
    #     emb.set_footer(text=f'#{ctx.channel.name}', icon_url=ctx.author.avatar_url_as(static_format="png"))
    #     await hf.safe_send(ctx, embed=emb)
    #     y = 5 * x + \
    #         f'**{author.name}#{author.discriminator}** ({author.id})\n**Message edited after ' \
    #         f'{time_dif} seconds.****Before:****After:**#{ctx.channel.name}'
    #     await hf.safe_send(ctx, f'Possibly about {len(y)}')

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

    @commands.command(aliases=['rmdb'], hidden=True)
    async def reload_messages(self, ctx):
        """Reloads the messages"""
        with open(f"{dir_path}/messages.json", "r") as read_file:
            self.bot.messages = json.load(read_file)
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

                    file.write(f'    ({msg.created_at}) {self.BMP(msg.author.name)} - {BMP(msg.content)}\n')

    @commands.command(aliases=['quit'])
    async def kill(self, ctx):
        """Rai is a killer"""
        try:
            await ctx.message.add_reaction('💀')
            await self.bot.logout()
            await self.bot.close()
        except Exception as e:
            await hf.safe_send(ctx, f'**`ERROR:`** {type(e).__name__} - {e}')

    @commands.command(hidden=True)
    async def load(self, ctx, *, cog: str):
        """Command which loads a module."""

        try:
            self.bot.load_extension(f'cogs.{cog}')
        except Exception as e:
            await hf.safe_send(ctx, '**`ERROR:`** {} - {}'.format(type(e).__name__, e))
        else:
            await hf.safe_send(ctx, '**`SUCCESS`**')

    @commands.command(hidden=True)
    async def unload(self, ctx, *, cog: str):

        try:
            self.bot.unload_extension(f'cogs.{cog}')
        except Exception as e:
            await hf.safe_send(ctx, '**`ERROR:`** {} - {}'.format(type(e).__name__, e))
        else:
            await hf.safe_send(ctx, '**`SUCCESS`**')

    @commands.command(hidden=True)
    async def reload(self, ctx, *, cog: str):

        try:
            self.bot.reload_extension(f'cogs.{cog}')
        except Exception as e:
            await hf.safe_send(ctx, f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await hf.safe_send(ctx, '**`SUCCESS`**')

    def cleanup_code(self, content):
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
                    except discord.errors.HTTPException:
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
                    async for message in channel.history(limit=None, after=datetime.utcnow() - timedelta(days=31)):
                        emoji_list = pattern.findall(message.content)
                        if emoji_list:
                            for emoji in emoji_list:
                                name = emoji.split(':')[1]  # this will strip the ID, and include emojis from other
                                try:  # servers with the same name, which are usually the same emoji too
                                    emoji_dict[name] += 1
                                except KeyError:
                                    emoji_dict[name] = 1
                except discord.errors.Forbidden:
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
        """Irreversably mutes ryry for x amount of minutes"""
        self.bot.selfMute = True
        await hf.safe_send(ctx, f'Muting Ryry for {hour} hours and {minute} minutes (he chose to do this).')
        self.bot.selfMute = await asyncio.sleep(hour * 3600 + minute * 60, False)

    @commands.command(aliases=['fd'])
    async def get_left_users(self, ctx):
        print(f'>>finding messages<<')
        channel = self.bot.get_channel(277384105245802497)
        name_to_id = {role.name: role.id for role in channel.guild.roles}
        id_to_role = {role.id: role for role in channel.guild.roles}
        # self.bot.messages = await channel.history(limit=None, after=datetime.utcnow() - timedelta(days=60)).flatten()
        config = self.bot.db['readd_roles'][str(channel.guild.id)]
        config['users'] = {}
        print(len(self.bot.messages))
        for message in self.bot.messages:
            if message.author.id == 270366726737231884:
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
                            pass
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
        **Owner:** {guild.owner.mention} ({guild.owner.name}#{guild.owner.discriminator}))
        **Members:** {guild.member_count}
        **Channels:** {len(guild.text_channels)} text / {len(guild.voice_channels)} voice"""
        for channel in guild.text_channels:
            try:
                invite = await channel.create_invite(max_uses=1, reason="For bot owner Ryry013#9234")
                msg += f"\n{invite.url}"
                break
            except discord.HTTPException:
                pass
        await self.bot.get_user(202995638860906496).send(msg)
        await self.bot.get_user(202995638860906496).send("Channels: \n" +
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
            timestamp=datetime.utcnow(),
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


def setup(bot):
    bot.add_cog(Owner(bot))
