import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import json


class main:
    """My custom cog that does stuff!"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def punch(self, ctx, user: discord.Member):
        """A punch command I made as a test!"""

        # Your code will go here
        await ctx.send("ONE PUNCH! And " + user.mention + " is out! ლ(ಠ益ಠლ)")

    @commands.command()
    async def ping(self, ctx):
        """sends back 'hello'"""
        await ctx.send('hello')

    @commands.command()
    @commands.is_owner()
    async def selfMute(self, ctx, hour: float, minute: float):
        """mutes ryry for x amoutn of minutes"""
        self.bot.selfMute = True
        await ctx.send(f'Muting Ryry for {hour*3600+minute*60} seconds')
        self.bot.selfMute = await asyncio.sleep(hour * 3600 + minute * 60, False)

    @commands.command()
    async def echo(self, ctx, content: str):
        """sends back whatever you send"""
        await ctx.send(f"{content}")

    @commands.command()
    async def at(self, ctx):
        """asyncio test"""
        x = False
        print(f'Before running the sleep, x should be false: {x}.')
        me = self.bot.get_guild(275146036178059265).get_member(self.bot.owner_id)
        x = await asyncio.sleep(2, str(me.status) == 'offline')
        print(f'I have ran x = await asyncio.sleep(=="offline").  If I\'m offline, x should be True: {x}.')

    waited = False

    async def on_message(self, msg):
        if str(msg.channel) == 'Direct Message with Ryry013#9234' \
                and int(msg.author.id) == self.bot.owner_id \
                and str(msg.content[0:3]) == 'msg':
            print('hello')
            await self.bot.get_channel(int(msg.content[4:22])).send(str(msg.content[22:]))

        cont = str(msg.content)
        if (
                (
                        'ryry' in cont.casefold()
                        or ('ryan' in cont.casefold() and msg.channel.guild != self.bot.spanServ)
                ) and
                not msg.author.bot  # checks to see if account is a bot account
        ):  # random sad face
            await self.bot.spamChan.send(
                '<@202995638860906496> **By {} in <#{}>**: {}'.format(msg.author.name, msg.channel.id, msg.content))

        if msg.author.id == self.bot.owner_id and self.bot.selfMute == True:
            await msg.delete()

    @commands.command()
    async def pp(self, ctx):
        """Checks most active members who are in ping party but not welcoming party yet"""
        print('Checking ping party members')
        JHO = self.bot.get_channel(189571157446492161)
        mCount = {}

        async for m in JHO.history(limit=None, after=datetime.today()-timedelta(days=14)):
            try:
                mCount[m.author] += 1
            except KeyError:
                mCount[m.author] = 1
        print('Done counting messages')
        # print(type(list(mCount.keys())[0]))
        # print(mCount)
        mSorted = sorted(list(mCount.items()), key=lambda x: x[1], reverse=True)
        # print(mSorted)
        mCount = {}
        for memberTuple in mSorted:
            mCount[memberTuple[0].id] = [memberTuple[0].name, memberTuple[1]]
        # print(mCount)
        with open("sorted_members.json", "w") as write_file:
            json.dump(mCount, write_file)

        # print(type(mSorted[0][0]))

        for i in JHO.guild.roles:
            if i.id == 357449148405907456:  # ping party
                pingparty = i
            if i.id == 250907197075226625:  # welcoming party
                welcomingparty = i

        pingpartylist = ''
        for member in mSorted:
            # print(member[0].name)
            try:
                if pingparty in member[0].roles and welcomingparty not in member[0].roles:
                    pingpartylist += f'{member[0].name}: {member[1]}\n'
            except AttributeError:
                print(f'This user left: {member[0].name}: {member[1]}')
        await ctx.send(pingpartylist)


def setup(bot):
    bot.add_cog(main(bot))
