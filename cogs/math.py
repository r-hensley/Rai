import discord
from discord.ext import commands
import matplotlib

matplotlib.use('agg')
import matplotlib.pyplot as plt
import random
import math
import asyncio
import io
import os
from .utils import helper_functions as hf

dir_path = os.path.dirname(os.path.realpath(__file__))


class Math(commands.Cog):
    """Fun math games"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['nft'])
    async def nadeko_flip_test(self, ctx, starting_money=None, starting_bet=None,
                               bet_increase=None, save=None):
        """A test to see if/when you would go bankrupt with Nadeko coinflipping/martingale bets"""
        try:
            if not starting_bet and not starting_money and not bet_increase:  # if no amounts were specified
                await ctx.send(
                    "This is a module to simulate the martingale strategy for betting with Nadeko coin flips "
                    "(<https://en.wikipedia.org/wiki/Martingale_(betting_system)>).  At any time, type `cancel` to "
                    "leave the module.  \n\n"
                    "First, tell me how much money you wish to start with.  ")

                starting_money = await self.bot.wait_for('message', timeout=25.0,
                                                         check=lambda m: m.author == ctx.author and
                                                                         m.channel == ctx.channel)
                starting_money = int(starting_money.content)

                await ctx.send(
                    f"Ok, starting money set to `{starting_money}`.  Now tell me how much you want your first "
                    f"bet to be")
                starting_bet = await self.bot.wait_for('message', timeout=25.0,
                                                       check=lambda m: m.author == ctx.author and
                                                                       m.channel == ctx.channel)
                starting_bet = int(starting_bet.content)
                await ctx.send(
                    f"Ok, starting bet set to `{starting_bet}`.  Now by which multiple do you want to increase "
                    f"your bet when you lose?  (Usual choice is `2`)")
                bet_increase = await self.bot.wait_for('message', timeout=25.0,
                                                       check=lambda m: m.author == ctx.author and
                                                                       m.channel == ctx.channel)
                if float(bet_increase.content).is_integer():
                    bet_increase = int(bet_increase.content)
                else:
                    bet_increase = float(bet_increase.content)
                await ctx.send(
                    f"Ok, the bets will multiply by `{bet_increase}` each time you lose.  I'll start calculating."
                    f"  You're going to bet heads everytime.  Good luck.\n(Note you can skip process in the future by "
                    f"typing `;nft {starting_money} {starting_bet} {bet_increase}`)")
            else:  # if the amounts were specified in the command call
                starting_money = int(starting_money)
                starting_bet = int(starting_bet)
                bet_increase = float(bet_increase)
                try:
                    await ctx.message.add_reaction('👍')
                except discord.errors.NotFound:
                    pass

        except asyncio.TimeoutError:
            await ctx.send("Timed out.  Exiting module")
            return
        except TypeError as e:
            print(f">>{e}<<")
            await ctx.send("You put in a bad number somewhere.  Try again from the beginning.  Exiting module")
            return
        except ValueError as e:
            print(f">>{e}<<")
            await ctx.send("You put in a bad number somewhere.  Try again from the beginning.  Exiting module")
            return

        money_history = [starting_money]
        current_money = int(starting_money)
        current_bet = starting_bet
        bet_number = 1
        number_axis = [0]
        flip_history = ['Start']
        streak_history = ['Start']
        bet_history = ['Start']
        streak = 0

        while current_money > 0 and bet_number < 1000000:
            current_money -= current_bet
            bet_history.append(current_bet)
            flip = random.choice(['heads', 'tails'])
            if flip == 'heads':  # win
                current_money = int(current_money + math.floor(1.95 * current_bet))
                current_bet = starting_bet
                if streak > 0:
                    streak += 1
                else:
                    streak = 1
            else:  # lose
                current_bet = int(current_bet * bet_increase)
                if streak > 0:
                    streak = -1
                else:
                    streak -= 1
            number_axis.append(bet_number)
            bet_number += 1
            flip_history.append(flip)
            streak_history.append(streak)
            money_history.append(current_money)

        if bet_number >= 1000000:
            await ctx.send('I reached 1,000,000 flips so I stopped.')

        flipTest = plt.figure(ctx.author.id)
        plt.plot(number_axis, money_history)
        plt.title(f"Start with {starting_money}, first bet: {starting_bet} (x{bet_increase} on loss)")
        stats = f"```Some stats: \n\n" \
                f"Number of bets: {bet_number}\n" \
                f"Highest point: {max(money_history)} at bet {money_history.index(max(money_history))}```"
        with io.BytesIO() as plotIm:
            with io.StringIO() as write_file:
                for i in range(len(number_axis)):
                    line = f"bet#:{number_axis[i]},\tbet:{bet_history[i]},\tresult:{flip_history[i]},\t" \
                           f"money_after_flip:{money_history[i]},\tstreak={streak_history[i]}\n"
                    write_file.write(line)
                plt.savefig(plotIm, format='png')
                plotIm.seek(0)
                write_file.seek(0, os.SEEK_END)
                text_file_size = write_file.tell()  # size of the text file in bytes
                if text_file_size < 8000000:
                    write_file.seek(0)
                    await ctx.send(content=stats, files=[discord.File(plotIm, 'plot.png'),
                                                         discord.File(write_file, 'betting_log.txt')])
                else:
                    stats = stats + 'The text file was too big for Discord so it is not included'
                    await ctx.send(content=stats, file=discord.File(plotIm, 'plot.png'))
        if save == 'save':
            return

        plt.clf()
        plt.cla()
        plt.close()

    @commands.command(aliases=['randomwalk', 'rw'])
    async def randomWalk(self, ctx, n=None, save=None):
        """A random walk game, usage: ;randomWalk [length(number)]"""

        if not n:
            await ctx.send(
                "Please input a number after 'randomWalk' like `;randomWalk [number]`.  Example: `;randomWalk 10`"
            )
            return

        try:
            n = int(n)
        except ValueError:
            await ctx.send("Please input an integer")
            return

        position = 0
        posList = [0]
        probList = []
        string = ''

        flipped = False
        if n < 0:
            flipped = True
            n = -n

        if n > 100000 and ctx.author.id != self.bot.owner_id:
            n = 100000
            await ctx.send('Setting n to 100,000')
        n += 1
        if n > 1000:
            try:
                await ctx.message.add_reaction('\u2705')
            except NotFound:
                pass
        for i in range(n):
            rand = round(random.random(), 3)
            if rand < 0.5:  # from [0.000, 0.499]
                position -= 1
                posList.append(position)
                probList.append(rand)
            else:  # from [0.500, 0.999]
                position += 1
                posList.append(position)
                probList.append(rand)

        if flipped:
            posList = [-x for x in posList]
            x = range(0, -n - 1, -1)
        else:
            x = range(n + 1)

        for i in range(n):
            string += f'{posList[i]} ({probList[i]})\n'

        walkPlot = plt.figure(ctx.author.id+1)
        plt.plot(x, posList)
        plt.title(f"{ctx.author.name}'s random walk")
        maxVal = max(abs(max(posList)), abs(min(posList)))
        walkAxes = plt.axes().set_ylim(-maxVal, maxVal)
        with io.BytesIO() as walkIm:
            plt.savefig(walkIm, format='png')
            walkIm.seek(0)
            await hf.safe_send(ctx, "Here's your random walk!", file=discord.File(walkIm, 'plot.png'))

        if save == 'save':  # will show multiple plots on one graph
            return

        plt.clf()
        plt.cla()


def setup(bot):
    bot.add_cog(Math(bot))
