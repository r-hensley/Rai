from typing import Optional, Iterable

from discord.ext import commands
import aiosqlite


class Database(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[aiosqlite.Connection] = None
        self.cursor: Optional[aiosqlite.Cursor] = None

    @commands.Cog.listener()
    async def on_ready(self):
        await self.open_db()
        await self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
        await self.db.commit()

    async def open_db(self):
        if not self.db:
            self.db = await aiosqlite.connect("database.db")
        if not self.cursor:
            self.cursor: aiosqlite.Cursor = await self.db.cursor()

    @commands.is_owner()
    @commands.command()
    async def sql(self, ctx, *, query):
        await self.open_db()
        await self.execute(query)
        await ctx.message.add_reaction("✅")

    async def execute(self, query: str, parameters: Optional[Iterable] = None):
        await self.open_db()
        await self.cursor.execute(query, parameters)
        await self.db.commit()

    async def fetchrow(self, query: str, parameters: Optional[Iterable] = None):
        await self.open_db()
        await self.cursor.execute(query, parameters)
        result = await self.cursor.fetchall()
        return result

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while processing the command.")
        raise error

    async def initialize(self):
        self.db = await aiosqlite.connect("database.sqlite")
        self.cursor = await self.db.cursor()
        await self.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
        # await self.db.commit()

    async def close(self):
        if self.db:
            await self.db.close()

    @commands.command()
    async def add_user(self, ctx, name: str, age: int):
        # cursor = await self.db.cursor()
        await self.execute("INSERT INTO users (name, age) VALUES (?, ?)", (name, age))
        # await self.db.commit()
        await ctx.send("User added to the database.")

    @commands.command()
    async def get_users(self, ctx):
        # cursor = await self.db.cursor()
        users = await self.fetchrow("SELECT name, age FROM users")
        # users = await cursor.fetchall()
        await ctx.send(f"Users: {users}")

    @commands.command()
    async def remove_user(self, ctx, name: str):
        # cursor = await self.db.cursor()
        await self.execute("DELETE FROM users WHERE name=?", (name,))
        # await self.db.commit()
        await ctx.send("User removed from the database.")


async def setup(bot):
    await bot.add_cog(Database(bot))