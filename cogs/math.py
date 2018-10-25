import discord
from discord.ext import commands
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import random


import os
dir_path = os.path.dirname(os.path.realpath(__file__))

class Math:
    """Fun math games"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['randomwalk', 'rw'])
    async def randomWalk(self, ctx, n=None):
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
        
        if n > 1000 and ctx.author.id != self.bot.owner_id:
            n = 1000
            await ctx.send('Setting n to 1000')
        n += 1
        if n > 1000:
            await ctx.message.add_reaction('\u2705')
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
            posList = [ -x for x in posList ]
            x = range(0,-n-1,-1)
        else:
            x = range(n+1)
            
        for i in range(n):
            string += f'{posList[i]} ({probList[i]})\n'

        myPlot = plt.plot(x, posList)
        plt.title(f"{ctx.author.name}'s random walk")
        maxVal = max(abs(max(posList)), abs(min(posList)))
        plt.axes().set_ylim(-maxVal, maxVal)
        plt.savefig(dir_path+'/randomwalk.png')
        with open(dir_path+'/randomwalk.png', 'rb') as plotIm:
            await ctx.send(file = discord.File(plotIm))
        plt.clf()
        plt.cla()

def setup(bot):
    bot.add_cog(Math(bot))