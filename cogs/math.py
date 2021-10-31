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
                except discord.NotFound:
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

    @commands.command(aliases=['rc'])
    async def risk_calc(self, ctx, att, de):
        """Performs a simulation on a battle in risk.
        First input the number of attackers, then the number of defenders.
        Insert commas between the number of defenders to show a chain of territories to attack.

        Example: `;rc 3 2`   `;rc 8 3,2,2`"""
        try:
            initial_att = [int(att)]
            att = initial_att.copy()
            initial_de = [int(territory) for territory in de.split(',')]
            de = initial_de.copy()
            if att[0] < 2 or [i for i in de if i < 1]:
                await hf.safe_send(ctx, "You must have at least 2 att and at least 1 de.")
                return
        except (ValueError, TypeError, AttributeError):
            await hf.safe_send(ctx, "Please put a integer number of att and de. Try `;help rc`.")
            return

        results = []
        s = ''

        while len(results) < 5000:
            if att[0] == 1 or not de:
                results.append((att[0], sum(de)))
                # s += f"{att}, {de}\n"
                att = initial_att.copy()
                de = initial_de.copy()
            if att[0] > 3:
                att_rolls = 3
            elif att[0] == 3:
                att_rolls = 2
            else:  # att[0] should never equal 1 at this point
                att_rolls = 1
            att_dice = sorted([random.randint(1, 6) for _ in range(att_rolls)], reverse=True)

            if de[0] >= 2:
                de_rolls = 2
            else:
                de_rolls = de[0]
            de_dice = sorted([random.randint(1, 6) for _ in range(de_rolls)], reverse=True)

            # s += f"{att}, {de}, {att_dice}, {de_dice}, {att_rolls}, {de_rolls}, {results}\n"

            # this will pair two lists of equal lengths should one player get more dice rolls
            if att_rolls >= de_rolls:
                att_dice = att_dice[:de_rolls]
            else:
                de_dice = de_dice[:att_rolls]
            # s += f"{att_dice}, {de_dice}\n"

            for die in range(len(att_dice)):
                if att_dice[die] <= de_dice[die]:
                    att[0] -= 1
                    if att[0] == 1:
                        break
                else:
                    de[0] -= 1
                    if not de[0]:
                        del(de[0])
                        att[0] -= 1
                        break
        # await ctx.send(s)

        att_victories = [i[0] for i in results if i[1] == 0]  # counts how many times defenders lost
        att_percentage = round(100 * len(att_victories) / len(results), 2)
        try:
            att_average = round(sum(att_victories) / len(att_victories), 1)
        except ZeroDivisionError:
            att_average = 1

        de_victories = [i[1] for i in results if i[1] > 0]
        de_percentage = round(100 * len(de_victories) / len(results), 1)
        try:
            de_average = round(sum(de_victories) / len(results), 1)
        except ZeroDivisionError:
            de_average = 0

        # await ctx.send(' '.join([str(i) for i in att_victories[:30]]))
        # await ctx.send(' '.join([str(i) for i in de_victories[:30]]))
        # await ctx.send(' '.join([str(i) for i in results['att'][:60]]))
        # await ctx.send(' '.join([str(i) for i in results['de'][:60]]))

        await hf.safe_send(ctx, f"Out of 5,000 battles:\n"
                                f"Attackers occupies **{len(att_victories)} times** "
                                f"({att_percentage}%) (average {att_average} surviving troops)\n"
                                f"Defenders survived **{len(de_victories)} times** "
                                f"({de_percentage}%) (average {de_average} surviving troops)")


def setup(bot):
    bot.add_cog(Math(bot))
