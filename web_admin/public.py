import base64
import json
import logging
from pathlib import Path

from aiohttp import web


PATH = "/id_expand/"
PAGE = Path(__file__).with_name("id_expand.html")


def add_copy_ids_link(embed, guild_id, participants):
    if not participants:
        return
    roster = []
    for member in participants:
        avatar = member.display_avatar.key
        if member.guild_avatar:
            avatar = "g" + avatar
        roster.append([str(member.id), member.display_name, member.name, avatar])
    data = json.dumps([guild_id, roster], ensure_ascii=False, separators=(",", ":"))
    fragment = base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")
    link = f"[Copy IDs](https://api.raidiscord.com{PATH}#{fragment})"
    # shortcut: the embed field fits 1024 characters, use a stored roster if larger lists need links.
    title = "Participant IDs"
    if len(link) <= 1024 and len(embed) + len(title) + len(link) <= 6000 and len(embed.fields) < 25:
        embed.add_field(name=title, value=link, inline=False)


async def id_expand(request):
    return web.FileResponse(PAGE, headers={
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": (
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "img-src https://cdn.discordapp.com; frame-ancestors 'none'; base-uri 'none'"
        ),
    })


class PublicWeb:
    runner = None

    async def start(self):
        app = web.Application()
        app.router.add_get(PATH, id_expand)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", 8766).start()
        except OSError:
            await runner.cleanup()
            logging.getLogger(__name__).exception("Could not start Rai's public web listener")
        else:
            self.runner = runner

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
