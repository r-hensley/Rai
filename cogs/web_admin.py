from discord.ext import commands

from web_admin import WebAdminSite


class WebAdmin(commands.Cog):
    """Start and stop Rai's administration website with the Discord bot."""

    def __init__(self, bot: commands.Bot):
        self.site = WebAdminSite(bot)

    async def cog_load(self) -> None:
        await self.site.start()

    async def cog_unload(self) -> None:
        await self.site.stop()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebAdmin(bot))
