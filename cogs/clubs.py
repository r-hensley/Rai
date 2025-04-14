import asyncio
import os
import sqlite3

from sqlite3 import IntegrityError

import asqlite
from discord.ext import commands
from discord.ext.commands import Context
from discord.ext.commands._types import BotT

from .database import Connect
from .utils import helper_functions as hf
from cogs.utils.BotUtils import bot_utils as utils

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATABASE_PATH = rf'{dir_path}/database.db'


def club_owners(ctx):
    if hf.submod_check(ctx):
        return True

    if ctx.author.id in [803047978939973652, 859052632098472017, 557355005087186974]:
        return True


class Clubs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    async def cog_check(self, ctx: Context[BotT]) -> bool:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.")
            return False
        return True

    @commands.command(aliases=['parties'])
    async def clubs(self, ctx):
        """Returns a list of clubs. Related ommands:

        `;joinclub <club-name>` - Joins a club
        `;createclub <club-name>` - Creates a club (ask mods for help)
        `;giveclub <recipient-id> <club-name>` - Gives a club you own to someone else
        `;changeclub <club-name>` - Change the name of a club you own, it'll ask you later for a new name"""

        clubs = Connect("database.db", "clubs")

        list_of_clubs = await clubs.execute(f"SELECT club_id, name FROM clubs WHERE guild_id = {ctx.guild.id}")
        text = f"__List of clubs__\n"
        list_of_clubs = sorted(list_of_clubs, key=lambda x: x[1])
        for club in list_of_clubs:
            count = (await clubs.execute(f"SELECT COUNT(*) FROM club_members WHERE club_id = {club[0]}"))[0][0]
            owner = (await clubs.execute(f"SELECT owner_id FROM clubs WHERE club_id = {club[0]}"))[0][0]
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
        if len(club_name) > 32:
            await utils.safe_send(ctx, "Please use a name shorter than 32 characters for your club.")
            return

        # the user ID is a foreign key to the users table, so make sure it's in there
        async with asqlite.connect(DATABASE_PATH) as c:
            await c.execute(f"INSERT OR IGNORE INTO users (user_id) VALUES ({ctx.author.id})")

        # the user ID is a foreign key to the guilds table, so make sure it's in there
        async with asqlite.connect(DATABASE_PATH) as c:
            await c.execute(f"INSERT OR IGNORE INTO guilds (guild_id) VALUES ({ctx.guild.id})")

        query = "INSERT INTO clubs (name, guild_id, created_at, owner_id) VALUES (?, ?, ?, ?)"
        parameters = (club_name, ctx.guild.id, ctx.message.created_at, ctx.author.id)
        try:
            async with asqlite.connect(DATABASE_PATH) as c:
                await c.execute(query, parameters)
        except IntegrityError:
            await ctx.send("There is already a club with that name here, please choose a new name.")
            return
        else:
            await ctx.message.add_reaction("✅")

    @commands.command(aliases=['deleteparty'])
    @hf.is_admin()
    async def deleteclub(self, ctx: commands.Context, *, club_name: str):
        """Deletes a club. Type the name of your club afterwards like
        `;deleteclub my club`"""
        if len(club_name) > 32:
            await utils.safe_send(ctx, "Please use a name shorter than 32 characters for your club.")
            return
        query1 = f"SELECT name, club_id FROM clubs WHERE name = ?"
        query2 = f"DELETE FROM clubs WHERE name = ? and guild_id = {ctx.guild.id}"
        parameters = (club_name, )

        clubs = Connect("database.db", "clubs")

        current_clubs = await clubs.execute(query1, parameters)
        if not current_clubs:
            await utils.safe_send(ctx, "I couldn't find a club with that name, please try again.")
            return
        assert len(current_clubs) == 1, f"The result of this search was somehow greater than 1: " \
                                        f"{[list(i) for i in current_clubs]}"

        try:
            await clubs.execute(query2, parameters)
        except IntegrityError as e:
            await ctx.send(f"Error: {e}")
            return
        else:
            await ctx.message.add_reaction("✅")

        to_delete_club_id = int(current_clubs[0][1])
        delete_from_club_members_query = f"DELETE FROM club_members WHERE club_id = {to_delete_club_id}"
        async with asqlite.connect(DATABASE_PATH) as c:
            await c.execute(delete_from_club_members_query)

    @commands.command(aliases=['joinparty'])
    async def joinclub(self, ctx: commands.Context, *, club_name: str):
        """Joins a club. Type the name of the club like `;joinclub <club-name>`."""
        clubs = Connect("database.db", "clubs")
        to_join_club = await clubs.execute("SELECT club_id, name FROM clubs WHERE name COLLATE nocase = ?",
                                           (club_name, ))
        if not to_join_club:
            await ctx.send("I could not find the club you are trying to join. Please try again.")
            return

        assert len(to_join_club) == 1, f"The above SQL line should've returned one result only: " \
                                       f"{[list(i) for i in to_join_club]}"

        to_join_id = to_join_club[0][0]

        # the user ID is a foreign key to the users table, so make sure it's in there
        async with asqlite.connect(DATABASE_PATH) as c:
            await c.execute(f"INSERT OR IGNORE INTO users (user_id) VALUES ({ctx.author.id})")

        query = "INSERT INTO club_members (club_id, member_id) VALUES (?, ?)"
        parameters = (to_join_id, ctx.author.id)
        try:
            async with asqlite.connect(DATABASE_PATH) as c:
                await c.execute(query, parameters)
            await ctx.message.add_reaction("✅")
        except sqlite3.IntegrityError as e:
            if e.args[0].startswith("UNIQUE constraint failed"):
                await ctx.send(f"You are already in that club!")
            else:
                raise

    @commands.command(aliases=['leaveparty'])
    async def leaveclub(self, ctx: commands.Context, *, club_name: str):
        """Leave a club. Type the name of the club you wish to leave in the command.
        Syntax: `;leaveclub <club-name>`
        Example: `;leaveclub a boring club`."""
        clubs = Connect("database.db", "clubs")
        to_leave_id = None
        list_of_clubs = await clubs.execute("SELECT club_id, name FROM clubs")
        for (club_id, name) in list_of_clubs:
            if name.casefold() == club_name.casefold():
                to_leave_id = club_id

        if not to_leave_id:
            await ctx.send("I could not find the club you are trying to leave. Please try again.")
            return

        query = "DELETE FROM club_members WHERE club_id = ? AND member_id = ?"
        parameters = (to_leave_id, ctx.author.id)
        try:
            async with asqlite.connect(DATABASE_PATH) as c:
                await c.execute(query, parameters)
        except sqlite3.IntegrityError as e:
            if e.args[0] == "FOREIGN KEY constraint failed":
                raise
            else:
                raise
        else:
            await ctx.message.add_reaction("✅")

    @commands.command(aliases=['giveparty'])
    async def giveclub(self, ctx: commands.Context, user_id, *, club_name: str):
        """Gives ownership of a club to another user.

        Use: `;giveclub <recipient-id> <club-name>`.
        Example: `;giveclub 414873201349361664 my club`"""
        try:
            user_id = int(user_id)
        except ValueError:
            await utils.safe_send(ctx, "Please send the command in this format: `giveclub <recipient-id> <club name>`. "
                                    "Example: `;giveclub 1234567890 example club`")
            return

        clubs = Connect("database.db", "clubs")
        to_give_id = None
        list_of_clubs = await clubs.execute("SELECT owner_id, name, guild_id FROM clubs")
        for (owner_id, name, guild_id) in list_of_clubs:
            if name.casefold() == club_name.casefold() and guild_id == ctx.guild.id:
                to_give_id = user_id
                if not club_owners(ctx) and owner_id != ctx.author.id:
                    await utils.safe_send(ctx, "You must be a moderator or the club's owner in order to give "
                                            "this club away.")
                    return

        if not to_give_id:
            await utils.safe_send(ctx, "I could not find the club you are trying to transfer. Please try again.")
            return

        if not ctx.guild.get_member(user_id):
            await utils.safe_send(ctx, f"A user could not be found with the ID: {user_id}; Please try again.")
            return

        # the user ID is a foreign key to the users table, so make sure it's in there
        async with asqlite.connect(DATABASE_PATH) as c:
            await c.execute(f"INSERT OR IGNORE INTO users (user_id) VALUES ({to_give_id})")

        # the user ID is a foreign key to the guilds table, so make sure it's in there
        async with asqlite.connect(DATABASE_PATH) as c:
            await c.execute(f"INSERT OR IGNORE INTO guilds (guild_id) VALUES ({ctx.guild.id})")

        query = f"UPDATE clubs SET owner_id = ? WHERE name = ? AND guild_id = ?"
        parameters = (to_give_id, club_name, ctx.guild.id)
        try:
            await clubs.execute(query, parameters)
        except IntegrityError:
            await utils.safe_send(ctx, f"User (ID: {to_give_id}) already owns club: {club_name}.")
            return
        else:
            await ctx.message.add_reaction("✅")

    @commands.command(aliases=['changeparty', 'partyname'])
    async def changeclub(self, ctx: commands.Context, *, club_name):
        """Change the name of your club. Start by just inputting the name of the club you want to change"""
        clubs = Connect("database.db", "clubs")
        clubs = await clubs.execute("SELECT name, owner_id FROM clubs")
        old_name = None
        for (name, owner_id) in clubs:
            if name.casefold() == club_name.casefold() and (owner_id == ctx.author.id or club_owners(ctx)):
                old_name = name
        if not old_name:
            await utils.safe_send(ctx, "You need to be the owner of a party to change the name of it.")
            return

        if not old_name:
            await utils.safe_send(ctx, "Either I couldn't find your club or there are no clubs!")
            return

        await utils.safe_send(ctx, "Please input the new name for your club")
        try:
            new_name_msg = await self.bot.wait_for("message", timeout=30.0,
                                                   check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
        except asyncio.TimeoutError:
            await utils.safe_send(ctx, "Request timed out. Please start again.")
            return

        new_name = new_name_msg.content
        if not new_name:
            await utils.safe_send(ctx, "I couldn't find what new name you wanted to set. Please try again.")
            return

        for (name, owner_id) in clubs:
            if name == new_name:
                await utils.safe_send(ctx, "There already exists a club with that name. Please choose a new name.")
                return

        if len(new_name) > 32:
            await utils.safe_send(ctx, "Please choose a shorter club name")
            return

        query = f"UPDATE clubs SET name = ? WHERE name = ? AND guild_id = ?"
        parameters = (new_name, old_name, ctx.guild.id)
        try:
            await clubs.execute(query, parameters)
        except IntegrityError as e:
            await utils.safe_send(ctx, f"Error updating database: {e}")
            return
        else:
            await new_name_msg.add_reaction("✅")

    # @commands.command()
    # async def clubmembers(self, ctx, *, club_name):
    #     """List members in a club"""
    #     # maybe use this? https://gist.github.com/InterStella0/454cc51e05e60e63b81ea2e8490ef140


async def setup(bot):
    await bot.add_cog(Clubs(bot))
