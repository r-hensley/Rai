from discord.ext import commands


DM_MODBOT_ID = 713245294657273856


class Reports(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    async def report(self, ctx):
        await ctx.send(f"If you're using this, please DM <@{DM_MODBOT_ID}> instead (DMModbot).")


async def setup(bot):
    await bot.add_cog(Reports(bot))
