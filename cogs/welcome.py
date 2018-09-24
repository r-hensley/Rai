import discord
import asyncio
from datetime import datetime, timedelta
from pytz import reference
import time
import sys
import os

dir_path = os.path.dirname(os.path.realpath(__file__))

jpServ = 189571157446492161

spServ = 243838819743432704
secPriv = 277511392972636161

ryryServ = 275146036178059265
spamChan = 304110816607862785

nadeko = 116275390695079945

random_walk1 = 447875990333685762
random_walk2 = 447876530710904832


class Welcome:
    """Welcomes people"""

    def __init__(self, bot):
        self.bot = bot

    async def on_member_join(self, m):
        """Japanese Server welcome"""
        # usedInvite = None
        # oldList = self.bot.invitesOld
        #
        # if m.guild == self.bot.jpServ:
        #     newList = await self.bot.jpServ.invites()
        #
        #     for new in newList:
        #         try:
        #             old = oldList[oldList.index(new)]  # matches the invites
        #             if new.uses != old.uses and new.code == old.code:
        #                 usedInvite = new
        #         except ValueError:  # if the new invite isn't in old invites
        #             if new.uses != 0:
        #                 usedInvite = new
        #
        #     def make_embed():
        #         minutes_ago_created = int(((datetime.utcnow() - m.created_at).total_seconds()) // 60)
        #         if minutes_ago_created < 60:
        #             time_str = f'\n\nAccount created **{minutes_ago_created}** minutes ago'
        #         else:
        #             time_str = ''
        #
        #         emb = discord.Embed(
        #             description=f":inbox_tray: **{m.name}#{m.discriminator}** has `joined`. "
        #                         f"({m.id}){time_str}",
        #             colour=0x7BA600,
        #             timestamp=datetime.utcnow()
        #         )
        #
        #         if usedInvite:
        #             invite_string = f'Used {usedInvite.inviter.name}\'s link {usedInvite.code}'
        #             footer_text = f'User Join ({self.bot.jpServ.member_count}) {invite_string}'
        #         else:
        #             footer_text = f'User Join ({self.bot.jpServ.member_count})'
        #
        #         emb.set_footer(text=footer_text, icon_url=m.avatar_url_as(static_format="png"))
        #
        #         return emb
        #
        #     await self.bot.jpEverything.send(embed=make_embed())



        # for i in range(5):
        #     rand = round(random.random(), 3)
        #
        #     """"Random Walk 1"""
        #     if rand > (0.5 + self.bot.pos1/100): self.bot.pos1 = round(self.bot.pos1+2*rand,3)
        #     else: self.bot.pos1 = round(self.bot.pos1-2*rand,3)
        #     n1 = int(abs(self.bot.pos1))+1
        #     await self.bot.get_channel(random_walk1).send('-'*n1)
        #
        #     """Random Walk 2"""
        #     if rand <= 0.35: self.bot.pos2 -= 1
        #     elif 0.35 < rand < 0.65: pass
        #     elif 0.65 <= rand: self.bot.pos2 += 1
        #     n2 = abs(self.bot.pos2)+1
        #     await self.bot.get_channel(random_walk2).send('-'*n2)

        # """Spanish Server welcome"""
        # if m.guild == self.bot.spanServ:
        #     nadeko_obj = self.bot.spanServ.get_member(116275390695079945)
        #     if str(nadeko_obj.status) == 'offline':
        #         await self.bot.get_channel(243838819743432704).send(
        #             'Welcome to the server.  Nadeko is currently down, '
        #             'so please state your roles and someone in welcoming party will come to'
        #             ' assign your role as soon as possible.  If no one comes, please tag the mods with `@Mods`.  '
        #             'Thanks! '
        #             '(<@&470364944479813635>)'
        #         )

    async def on_member_update(self, bef, af):
        """Nadeko updates"""
        if bef == self.bot.spanServ.get_member(116275390695079945) and bef.guild == self.bot.spanServ:
            if str(bef.status) == 'online' and str(af.status) == 'offline':
                def check(befcheck, afcheck):
                    return af.id == befcheck.id and \
                           str(befcheck.status) == 'offline' and \
                           str(afcheck.status) == 'online'

                try:
                    await self.bot.wait_for('member_update', check=check, timeout=1200)
                    self.bot.waited = False
                except asyncio.TimeoutError:
                    self.bot.waited = True

                if self.bot.waited:
                    await self.bot.spanSP.send(  # nadeko was offline for 20 mins
                        "Nadeko has gone offline.  New users won't be able to tag themselves, "
                        "and therefore will not be able to join the server.  Please be careful of this."
                    )

            if str(bef.status) == 'offline' and str(af.status) == 'online':
                if self.bot.waited:
                    self.bot.waited = False  # waited is True if Nadeko has been offline for more than 20 minutes
                    await self.bot.spanSP.send('Nadeko is back online now.')

    # async def on_member_remove(self, m):
    #     if m.guild == self.bot.jpServ:
    #         emb = discord.Embed(
    #             description=''
    #             f":outbox_tray: **{m.name}#{m.discriminator}** has `left` the server. "
    #             f"({m.id})",
    #             colour=0xD12B2B,
    #             timestamp=datetime.utcnow()
    #         )
    #
    #         emb.set_footer(
    #             text=f'User Leave ({self.bot.jpServ.member_count})',
    #             icon_url=m.avatar_url_as(static_format="png")
    #         )
    #
    #         await self.bot.jpEverything.send(embed=emb)


def setup(bot):
    bot.add_cog(Welcome(bot))
