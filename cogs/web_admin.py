from discord.ext import commands

from web_admin import WebAdminSite
from web_admin.public import PublicWeb


class WebAdmin(commands.Cog):
    """Start and stop Rai's administration website with the Discord bot."""

    def __init__(self, bot: commands.Bot):
        self.site = WebAdminSite(bot)
        self.public = PublicWeb()

    async def cog_load(self) -> None:
        await self.site.start()
        if self.site.web_ready and self.site.public_base_url == "https://admin.raidiscord.com":
            await self.public.start()

    async def cog_unload(self) -> None:
        try:
            await self.public.stop()
        finally:
            await self.site.stop()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebAdmin(bot))
