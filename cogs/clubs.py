from typing import Optional

import aiosqlite
from discord.ext import commands

from .database import Database


class Clubs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sqdb: Optional[Database] = self.bot.get_cog("Database")

    # @commands.Cog.listener()
    # async def on_ready(self):
    #     self.sqdb =

    async def create_clubs_table(self):
        await self.sqdb.execute("CREATE TABLE IF NOT EXISTS clubs "
                                "(id INTEGER PRIMARY KEY, "
                                "name TEXT, "
                                "guild_id INTEGER,"
                                "created_at TIMESTAMP,"
                                "owner_id INTEGER,"
                                "UNIQUE (name, guild_id))")

        await self.sqdb.execute("CREATE TABLE IF NOT EXISTS club_members "
                                "(id INTEGER PRIMARY KEY, "
                                "club_id INTEGER,"
                                "member_id INTEGER,"
                                "FOREIGN KEY (club_id) REFERENCES clubs (id),"
                                "UNIQUE (club_id, member_id))")

    @commands.command()
    async def clubs(self, ctx):
        await self.create_clubs_table()

        list_of_clubs = await self.sqdb.fetchrow("SELECT name FROM clubs")
        await ctx.send(str(list_of_clubs))

    @commands.command()
    async def createclub(self, ctx: commands.Context, *, club_name: str):
        await self.create_clubs_table()
        query = "INSERT INTO clubs (name, guild_id, created_at, owner_id) VALUES (?, ?, ?, ?)"
        parameters = (club_name, ctx.guild.id, ctx.message.created_at, ctx.author.id)
        try:
            await self.sqdb.execute(query, parameters)
        except aiosqlite.IntegrityError:
            await ctx.send("There is already a club with that name here, please choose a new name.")
            return

    @commands.command()
    async def joinclub(self, ctx: commands.Context, *, club_name: str):
        await self.create_clubs_table()

        to_join_id = None
        list_of_clubs = await self.sqdb.fetchrow("SELECT id, name FROM clubs")
        for (id, name) in list_of_clubs:
            if name.casefold() == club_name.casefold():
                to_join_id = id

        if not to_join_id:
            await ctx.send("I could not find the club you are trying to join. Please try again.")
            return

        query = "INSERT INTO club_members (club_id, member_id) VALUES (?, ?)"
        parameters = (to_join_id, ctx.author.id)
        try:
            await self.sqdb.execute(query, parameters)
        except aiosqlite.IntegrityError:
            await ctx.send("You are already in that club!")
            return


async def setup(bot):
    await bot.add_cog(Clubs(bot))