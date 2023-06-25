import os
from typing import Optional, Iterable

from discord.ext import commands
import aiosqlite

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Database(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[aiosqlite.Connection] = None
        self.cursor: Optional[aiosqlite.Cursor] = None

    @commands.Cog.listener()
    async def on_ready(self):
        await self.open_db()

    async def open_db(self):
        if not self.db or not self.db.is_alive():
            self.db = await aiosqlite.connect(f"{dir_path}/database.db")
        if not self.cursor:
            self.cursor: aiosqlite.Cursor = await self.db.cursor()

    @commands.is_owner()
    @commands.command()
    async def sql(self, ctx, *, user_input: str):
        query = user_input.split("\n")
        parameters = None
        if len(query) > 1:
            parameters = query[1].replace(", ", ",").split(",")
        query = query[0]
        try:
            if query.casefold().startswith("select"):
                r = await self.fetchrow(query, parameters)
                await ctx.message.reply(r)
            else:
                await self.execute(query, parameters)
        except Exception as e:
            await ctx.send(f"Error: {e}")
            await self.db.commit()
        else:
            await ctx.message.add_reaction("✅")

    async def execute(self, query: str, parameters: Optional[Iterable] = None):
        if parameters and type(parameters) is not tuple:
            parameters = (parameters,)
        await self.open_db()
        r = await self.cursor.execute(query, parameters)
        await self.db.commit()
        return r

    async def fetchrow(self, query: str, parameters: Optional[Iterable] = None):
        if parameters and type(parameters) is not tuple:
            parameters = (parameters,)
        await self.open_db()
        await self.cursor.execute(query, parameters)
        result = await self.cursor.fetchall()
        return result

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while processing the command.")
        raise error

    async def close(self):
        if self.db:
            await self.db.close()



async def setup(bot):
    await bot.add_cog(Database(bot))