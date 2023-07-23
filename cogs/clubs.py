import asyncio
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

    async def create_clubs_table(self):
        # Idk if it's necessary to do this or if there's a better way but I run this at the beginning
        # of all my club commands to make sure the tables exist, mainly for people running newly
        # forked copies of Rai
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
        """Returns a list of clubs. Related ommands:

        `;joinclub <club-name>` - Joins a club
        `;createclub <club-name>` - Creates a club (ask mods for help)
        `;giveclub <recipient-id> <club-name>` - Gives a club you own to someone else
        `;changeclub <club-name>` - Change the name of a club you own, it'll ask you later for a new name"""
        await self.create_clubs_table()

        list_of_clubs = await self.sqdb.fetchrow(f"SELECT id, name FROM clubs WHERE guild_id = {ctx.guild.id}")
        text = f"__List of clubs__\n"
        for club in list_of_clubs:
            count = (await self.sqdb.fetchrow(f"SELECT COUNT(*) FROM club_members WHERE club_id = {club[0]}"))[0][0]
            owner = (await self.sqdb.fetchrow(f"SELECT owner_id FROM clubs WHERE id = {club[0]}"))[0][0]
            club_name = club[1].replace("*", r"\*").replace("_", r"\_")
            text += f"・{club_name}"
            owner = ctx.guild.get_member(owner)
            if owner:
                club_owner = owner.name.replace("*", r"\*").replace("_", r"\_")
                text += f", led by {club_owner}"
            text += f" ({count} members)\n"
        await ctx.send(text)

    @commands.command(aliases=['createparty'])
    @commands.check(club_owners)
    async def createclub(self, ctx: commands.Context, *, club_name: str):
        """Creates a club. Type the name of your club afterwards like
        `;createclub my club`"""
        await self.create_clubs_table()
        if len(club_name) > 32:
            await hf.safe_send(ctx, "Please use a name shorter than 32 characters for your club.")
            return
        query = "INSERT INTO clubs (name, guild_id, created_at, owner_id) VALUES (?, ?, ?, ?)"
        parameters = (club_name, ctx.guild.id, ctx.message.created_at, ctx.author.id)
        try:
            await self.sqdb.execute(query, parameters)
            await ctx.message.add_reaction("✅")
        except aiosqlite.IntegrityError:
            await ctx.send("There is already a club with that name here, please choose a new name.")
            return

    @commands.command(aliases=['deleteparty'])
    @hf.is_admin()
    async def deleteclub(self, ctx: commands.Context, *, club_name: str):
        """Deletes a club. Type the name of your club afterwards like
        `;deleteclub my club`"""
        await self.create_clubs_table()
        if len(club_name) > 32:
            await hf.safe_send(ctx, "Please use a name shorter than 32 characters for your club.")
            return
        query1 = f"SELECT name FROM clubs WHERE name = ?"
        query2 = f"DELETE FROM clubs WHERE name = ? and guild_id = {ctx.guild.id}"
        parameters = club_name

        try:
            current_clubs = await self.sqdb.fetchrow(query1, parameters)
            if not current_clubs:
                await hf.safe_send(ctx, "I couldn't find a club with that name, please try again.")
                return
            await self.sqdb.execute(query2, parameters)
            await ctx.message.add_reaction("✅")
        except aiosqlite.IntegrityError as e:
            await ctx.send(f"Error: {e}")
            return

    @commands.command(aliases=['joinparty'])
    async def joinclub(self, ctx: commands.Context, *, club_name: str):
        """Joins a club. Type the name of the club like `;joinclub <club-name>`."""
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
        """Gives ownership of a club to another user.

        Use: `;giveclub <recipient-id> <club-name>`.
        Example: `;giveclub 414873201349361664 my club`"""
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

        query = f"UPDATE clubs SET owner_id = ? WHERE name = '{club_name}' AND guild_id = {ctx.guild.id}"
        parameters = (to_give_id,)
        try:
            await self.sqdb.execute(query, parameters)
        except aiosqlite.IntegrityError:
            await hf.safe_send(ctx, f"User (ID: {to_give_id}) already owns club: {club_name}.")
            return
        else:
            await ctx.message.add_reaction("✅")

    @commands.command(aliases=['changeparty', 'partyname'])
    async def changeclub(self, ctx: commands.Context, *, club_name):
        """Change the name of your club. Start by just inputting the name of the club you want to change"""
        clubs = await self.sqdb.fetchrow("SELECT name, owner_id FROM clubs")
        old_name = None
        for (name, owner_id) in clubs:
            if name.casefold() == club_name.casefold() and (owner_id == ctx.author.id or club_owners(ctx)):
                old_name = name
        if not old_name:
            await hf.safe_send(ctx, "You need to be the owner of a party to change the name of it.")
            return

        if not old_name:
            await hf.safe_send(ctx, "Either I couldn't find your club or there are no clubs!")
            return

        await hf.safe_send(ctx, "Please input the new name for your club")
        try:
            new_name_msg = await self.bot.wait_for("message", timeout=30.0,
                                                   check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
        except asyncio.TimeoutError:
            await hf.safe_send(ctx, "Request timed out. Please start again.")
            return

        new_name = new_name_msg.content
        if not new_name:
            await hf.safe_send(ctx, "I couldn't find what new name you wanted to set. Please try again.")
            return

        for (name, owner_id) in clubs:
            if name == new_name:
                await hf.safe_send(ctx, "There already exists a club with that name. Please choose a new name.")
                return

        if len(new_name) > 32:
            await hf.safe_send(ctx, "Please choose a shorter club name")
            return

        query = f"UPDATE clubs SET name = ? WHERE name = '{old_name}' AND guild_id = {ctx.guild.id}"
        parameters = (new_name,)
        try:
            await self.sqdb.execute(query, parameters)
        except aiosqlite.IntegrityError as e:
            await hf.safe_send(ctx, f"Error updating database: {e}")
            return
        else:
            await new_name_msg.add_reaction("✅")

    # @commands.command()
    # async def clubmembers(self, ctx, *, club_name):
    #     """List members in a club"""
    #     # maybe use this? https://gist.github.com/InterStella0/454cc51e05e60e63b81ea2e8490ef140


async def setup(bot):
    await bot.add_cog(Clubs(bot))
