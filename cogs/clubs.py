from typing import Optional

import aiosqlite
from discord.ext import commands

from .database import Database
from .utils import helper_functions as hf


def club_owners(ctx):
    if hf.submod_check(ctx):
        return True

    if ctx.author.id in [803047978939973652, 859052632098472017, 557355005087186974]:
        return True


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

    @commands.command(aliases=['parties'])
    async def clubs(self, ctx):
        await self.create_clubs_table()

        list_of_clubs = await self.sqdb.fetchrow(f"SELECT id, name FROM clubs WHERE guild_id = {ctx.guild.id}")
        text = f"__List of clubs__\n"
        for club in list_of_clubs:
            count = (await self.sqdb.fetchrow(f"SELECT COUNT(*) FROM club_members WHERE club_id = {club[0]}"))[0][0]
            owner = (await self.sqdb.fetchrow(f"SELECT owner_id FROM clubs WHERE id = {club[0]}"))[0][0]
            text += f"・{club[1]}"
            owner = ctx.guild.get_member(owner)
            if owner:
                text += f", led by {owner.name}"
            text += f" ({count} members)\n"
        await ctx.send(text)

    @commands.command(aliases=['createparty'])
    @commands.check(club_owners)
    async def createclub(self, ctx: commands.Context, *, club_name: str):
        await self.create_clubs_table()
        query = "INSERT INTO clubs (name, guild_id, created_at, owner_id) VALUES (?, ?, ?, ?)"
        parameters = (club_name, ctx.guild.id, ctx.message.created_at, ctx.author.id)
        try:
            await self.sqdb.execute(query, parameters)
            await ctx.message.add_reaction("✅")
        except aiosqlite.IntegrityError:
            await ctx.send("There is already a club with that name here, please choose a new name.")
            return

    @commands.command(aliases=['joinparty'])
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
            await ctx.message.add_reaction("✅")
        except aiosqlite.IntegrityError:
            await ctx.send("You are already in that club!")
            return

    @commands.command(aliases=['giveparty'])
    async def giveclub(self, ctx: commands.Context, user_id, *, club_name: str):
        await self.create_clubs_table()

        try:
            user_id = int(user_id)
        except ValueError:
            await hf.safe_send(ctx, "Please send the command in this format: `giveclub <recipient-id> <club name>`. "
                                    "Example: `;giveclub 1234567890 example club`")
            return

        to_give_id = None
        list_of_clubs = await self.sqdb.fetchrow("SELECT owner_id, name, guild_id FROM clubs")
        for (owner_id, name, guild_id) in list_of_clubs:
            if name.casefold() == club_name.casefold() and guild_id == ctx.guild.id:
                to_give_id = user_id
                print(club_owners(ctx), owner_id, ctx.author.id)
                if not club_owners(ctx) and owner_id != ctx.author.id:
                    await hf.safe_send(ctx, "You must be a moderator or the club's owner in order to give "
                                            "this club away.")
                    return
                
        if not to_give_id:
            await hf.safe_send(ctx, "I could not find the club you are trying to transfer. Please try again.")
            return

        if not ctx.guild.get_member(user_id):
            await hf.safe_send(ctx, f"A user could not be found with the ID: {user_id}; Please try again.")
            return

        query = f"UPDATE clubs SET owner_id = ? WHERE name = ? AND guild_id = ?"
        parameters = (to_give_id, club_name, ctx.guild.id)
        try:
            await self.sqdb.execute(query, parameters)
            await ctx.message.add_reaction("✅")
        except aiosqlite.IntegrityError:
            await hf.safe_send(ctx, f"User (ID: {to_give_id}) already owns club: {club_name}.")
            return

    # @commands.command()
    # async def changeclub(self, ctx: commands.Context, *, club_name):
    #     """Change the name of your club. Start by just inputting the name of the club you want to change"""
    #     club = await self.sqdb.fetchrow("SELECT name, owner_id FROM clubs")


async def setup(bot):
    await bot.add_cog(Clubs(bot))
