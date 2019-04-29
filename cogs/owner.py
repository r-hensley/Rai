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

# to expose to the eval command
import datetime
from datetime import datetime, timedelta

import os
dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Owner(commands.Cog):
    # various code from https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/admin.py in here, thanks

    def __init__(self, bot):
        self.bot = bot
        self._last_result = None
        self.sessions = set()

    async def cog_check(self, ctx):
        return ctx.author.id in [202995638860906496, 414873201349361664]

    def get_syntax_error(self, e):
        if e.text is None:
            return f'```py\n{e.__class__.__name__}: {e}\n```'
        return f'```py\n{e.text}{"^":>{e.offset}}\n{e.__class__.__name__}: {e}```'

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
    #     await ctx.send(embed=emb)
    #     y = 5 * x + \
    #         f'**{author.name}#{author.discriminator}** ({author.id})\n**Message edited after ' \
    #         f'{time_dif} seconds.****Before:****After:**#{ctx.channel.name}'
    #     await ctx.send(f'Possibly about {len(y)}')

    @commands.command(aliases=['sdb', 'dump'])
    async def savedatabase(self, ctx):
        """Saves the database"""
        await hf.dump_json()
        await ctx.message.add_reaction('\u2705')

    @commands.command(aliases=['rdb'])
    async def reload_database(self, ctx):
        """Reloads the database"""
        with open(f"{dir_path}/db.json", "r") as read_file:
            self.bot.db = json.load(read_file)
        self.bot.ID = self.bot.db["ID"]
        await ctx.message.add_reaction('♻')

    @commands.command(aliases=['rmdb'])
    async def reload_messages(self, ctx):
        """Reloads the messages"""
        with open(f"{dir_path}/messages.json", "r") as read_file:
            self.bot.messages = json.load(read_file)
        await ctx.message.add_reaction('♻')

    @commands.command()
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
        """Kills bot"""
        try:
            await ctx.message.add_reaction('💀')
            await self.bot.logout()
            await self.bot.close()
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')

    @commands.command()
    async def load(self, ctx, *, cog : str):
        """Command which loads a module."""

        try:
            self.bot.load_extension(f'cogs.{cog}')
        except Exception as e:
            await ctx.send('**`ERROR:`** {} - {}'.format(type(e).__name__, e))
        else:
            await ctx.send('**`SUCCESS`**')

    @commands.command()
    async def unload(self, ctx, *, cog : str):

        try:
            self.bot.unload_extension(f'cogs.{cog}')
        except Exception as e:
            await ctx.send('**`ERROR:`** {} - {}'.format(type(e).__name__, e))
        else:
            await ctx.send('**`SUCCESS`**')

    @commands.command()
    async def reload(self, ctx, *, cog : str):
    
        try:
            self.bot.reload_extension(f'cogs.{cog}')
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('**`SUCCESS`**')

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove triple quotes + py\n
        if content.startswith("```") and content.endswith("```"):
            return '\n'.join(content.split('\n')[1:-1])
        
        # remove `single quotes`
        return content.strip('` \n')

    @commands.command()
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
            # print(member[0].name)
            try:
                if ping_party_role in member[0].roles and welcoming_party_role not in member[0].roles:
                    ping_party_list += f'{member[0].name}: {member[1]}\n'
            except AttributeError:
                print(f'This user left: {member[0].name}: {member[1]}')
        await ctx.send(ping_party_list)

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
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    try:
                        await ctx.send(f'```py\n{value}\n```')
                    except discord.errors.HTTPException:
                        st = f'```py\n{value}\n```'
                        await ctx.send('Result over 2000 characters')
                        await ctx.send(st[0:1996]+'\n```')
            else:
                self._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')

    @commands.command()
    async def count_emoji(self, ctx):
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
        await ctx.send(msg1)
        print(emoji_dict)
        print(emoji_list)

    @commands.command()
    async def selfMute(self, ctx, hour: float, minute: float):
        """mutes ryry for x amount of minutes"""
        self.bot.selfMute = True
        await ctx.send(f'Muting Ryry for {hour} hours and {minute} minutes (he chose to do this).')
        self.bot.selfMute = await asyncio.sleep(hour * 3600 + minute * 60, False)

    @commands.command()
    async def echo(self, ctx, *, content: str):
        """sends back whatever you send"""
        print(f">>{content}<<")
        try:
            await ctx.message.delete()
        except discord.errors.NotFound:
            pass
        await ctx.send(f"{content}")

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
        await hf.dump_json()
        print('done')

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.bot.get_user(202995638860906496).send(f'I have joined {guild.name}!')

    @commands.command()
    async def embed_test(self, ctx, color='FFFF00'):
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
        await ctx.send(embed=em)

    @commands.command(aliases=['hk'])
    async def hub_kick(self, ctx, user: discord.Member, rule):
        await ctx.message.delete()
        role = ctx.guild.get_role(530669592218042378)
        await user.remove_roles(role)
        await user.send(f"I've removed your member role on the Language Hub server.  Please reread "
                        f"<#530669247718752266> carefully and then you can rejoin the server.  Specifically, {rule}.")

def setup(bot):
    bot.add_cog(Owner(bot))
