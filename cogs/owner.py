from discord.ext import commands
import asyncio
import traceback
import discord
import inspect
import textwrap
from contextlib import redirect_stdout
import io
import sys
import codecs
import json

# to expose to the eval command
import datetime
from collections import Counter

import os
dir_path = os.path.dirname(os.path.realpath(__file__))


class Owner:
    # various code from https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/admin.py in here, thanks

    def __init__(self, bot):
        self.bot = bot
        self._last_result = None
        self.sessions = set()

    def BMP(self, s):
        return "".join((i if ord(i) < 10000 else '\ufffd' for i in s))

    async def __local_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    def get_syntax_error(self, e):
        if e.text is None:
            return '```py\n{}: {}\n```'.format(e.__class__.__name__,e)
        return '```py\n{}{"^":>{}}\n{}: {}```'.format(e.text,e.offset,e.__class__.__name__,e)

    @commands.command()
    async def flush(self, ctx):
        """Flushes stderr/stdout"""
        sys.stderr.flush()
        sys.stdout.flush()
        await ctx.message.add_reaction('🚽')

    @commands.command()
    async def savedatabase(self, ctx):
        """Saves the database"""
        with open(f'{dir_path}/database.json', 'w') as write_file:
            json.dump(self.bot.db, write_file)

    @commands.command()
    async def saveMessages(self, ctx):
        """Saves all messages in a channel to a text file"""
        print('Saving messages')
        with codecs.open(f'{ctx.message.channel}_messages.txt', 'w', 'utf-8') as file:
            print('File opened')
            async for msg in ctx.message.channel.history(limit=None, reverse=True):
                try:
                    file.write(f'    ({msg.created_at}) {msg.author.name} - {msg.content}\n')
                except UnicodeEncodeError:
                    file.write(f'    ({msg.created_at}) {self.BMP(msg.author.name)} - {self.BMP(msg.content)}\n')


    @commands.command(aliases=['quit'])
    @commands.is_owner()
    async def kill(self, ctx):
        """Kills bot"""
        try:
            await self.bot.logout()
            await self.bot.close()
        except Exception as e:
            await ctx.send(f'**`ERROR:`** {type(e).__name__} - {e}')
        else:
            await ctx.send('**`SUCCESS`**')
        


    @commands.command()
    @commands.is_owner()
    async def load(self, ctx, *, cog : str):
        """Command which loads a module."""

        try:
            self.bot.load_extension(f'cogs.{cog}')
        except Exception as e:
            await ctx.send('**`ERROR:`** {} - {}'.format(type(e).__name__, e))
        else:
            await ctx.send('**`SUCCESS`**')


    @commands.command()
    @commands.is_owner()
    async def unload(self, ctx, *, cog : str):

        try:
            self.bot.unload_extension(f'cogs.{cog}')
        except Exception as e:
            await ctx.send('**`ERROR:`** {} - {}'.format(type(e).__name__, e))
        else:
            await ctx.send('**`SUCCESS`**')


    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx, *, cog : str):
    
        try:
            self.bot.unload_extension(f'cogs.{cog}')
            self.bot.load_extension(f'cogs.{cog}')
        except Exception as e:
            await ctx.send('**`ERROR:`** {} - {}'.format(type(e).__name__, e))
        else:
            await ctx.send('**`SUCCESS`**')

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove triple quotes + py\n
        if content.startswith("```") and content.endswith("```"):
            return '\n'.join(content.split('\n')[1:-1])
        
        # remove `single quotes`
        return content.strip('` \n')


    @commands.command(pass_context=True, hidden=True, name='eval')
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
                    await ctx.send(f'```py\n{value}\n```')
            else:
                self._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')

                
def setup(bot):
    bot.add_cog(Owner(bot))
