import discord
from discord.ext import commands


class Dropdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    async def dropdown(self, ctx: commands.Context):
        role_1 = ctx.guild.roles[1]  # 0 might be @ everyone
        role_2 = ctx.guild.roles[2]
        role_3 = ctx.guild.roles[3]
        
        # Create a dropdown menu with the above roles
        options = [
            discord.SelectOption(label="Role 1", value=str(role_1.id), description="This is role 1"),
            discord.SelectOption(label="Role 2", value=str(role_2.id), description="This is role 2"),
            discord.SelectOption(label="Role 3", value=str(role_3.id), description="This is role 3"),
        ]

        select = discord.ui.Select(placeholder="Choose an option", options=options)

        # Create a view to hold the dropdown
        view = discord.ui.View()
        view.add_item(select)

        await ctx.send("Please select an option from the dropdown:", view=view)
        
async def setup(bot: commands.Bot):
    await bot.add_cog(Dropdown(bot))