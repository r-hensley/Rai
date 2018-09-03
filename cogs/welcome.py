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

    def BMP(self, s):
        return "".join((i if ord(i) < 10000 else '\ufffd' for i in s))

    async def on_member_join(self, m):
        """Japanese Server welcome"""
        t0 = time.perf_counter()
        usedInvite = 'none'
        oldList = self.bot.invitesOld
        localtime = reference.LocalTimezone()

        if m.guild == self.bot.jpServ:
            newList = await self.bot.jpServ.invites()

            for new in newList:
                try:
                    # tBef = datetime.now()
                    # test = discord.utils.find(lambda i: i.code == new.code, oldList)
                    # print(test, test.code, test.uses)
                    # if new.uses != test.uses:
                    #     tAf = datetime.now()
                    #     await self.bot.testChan.send(test)
                    #     await self.bot.testChan.send(f'Time to find invite using test method: {tAf-tBef}')
                    old = oldList[oldList.index(new)]  # matches the invites
                    if new.uses != old.uses and new.code == old.code:
                        usedInvite = new
                except ValueError:  # if the new invite isn't in old invites
                    if new.uses != 0:
                        usedInvite = new

            if usedInvite == 'none':
                newNewList = await self.bot.jpServ.invites()
                await self.bot.jpEverything.send(
                    f"Yeah, someone joined but I couldn't figure out which invite link they used.  "
                    f"Big sorry <:bow2:398262327843225613>.  It was {m.name}#{m.discriminator} ({m.id})."
                )
                with open(f'{dir_path}/inviteLog/{m.name}.log', 'w') as file:
                    for i in range(len(newNewList) + 2):
                        try:
                            file.write(f'1) {oldList[i].code}, {oldList[i].uses}\n')
                            file.write(f'2) {newList[i].code}, {newList[i].uses}\n')
                            file.write(f'3) {newNewList[i].code}, {newNewList[i].uses}\n')
                        except IndexError:
                            pass

            if usedInvite != 'none':
                minutesAgoCreated = int(((datetime.utcnow() - m.created_at).total_seconds()) // 60)
                if minutesAgoCreated < 60:
                    timeStr = f'\n\nAccount created **{minutesAgoCreated}** minutes ago'
                else:
                    timeStr = ''

                emb = discord.Embed(
                    description=f":inbox_tray: **{m.name}#{m.discriminator}** has `joined` the server. "
                                f"({m.id}){timeStr}",
                    colour=0x7BA600,
                    timestamp=datetime.now(tz=localtime)
                )

                invite_string = f'Used {usedInvite.inviter.name}\'s link {usedInvite.code}'
                emb.set_footer(
                    text=f'User Join ({self.bot.jpServ.member_count}) {invite_string}',
                    icon_url=m.avatar_url_as(static_format="png")
                )

                # t1 = time.perf_counter()
                await self.bot.jpEverything.send(embed=emb)
                # t2 = time.perf_counter()

                # try:
                #     oldInviteVal = oldList[oldList.index(usedInvite)].uses
                #     newInviteVal = newList[newList.index(usedInvite)].uses
                # except ValueError:
                #     oldInviteVal = 0
                #     newInviteVal = newList[newList.index(usedInvite)].uses

                # await self.bot.testChan.send(content=f'Time to get to before posting embeds: {t1-t0}\n'
                #                                      f'Time to post embeds: {t2-t1}\n'
                #                                      f'Member: {m.name} -- '
                #                                      f'Invite: {usedInvite.code} -- '
                #                                      f'({oldInviteVal}->{newInviteVal})',
                #                              embed=emb)

                japanese_links = ['6DXjBs5', 'WcBF7XZ', 'jzfhS2', 'w6muGjF', 'TxdPsSm', 'MF9XF89', 'RJrcSb3']
                if str(usedInvite.code) in japanese_links:
                    await self.bot.jpJHO.send(f'{m.name}さん、サーバーへようこそ！')
                elif m.id != 414873201349361664:
                    await self.bot.jpJHO.send(f'Welcome {m.name}!')

            self.bot.invitesOld = newList
            sys.stderr.flush()
            sys.stdout.flush()

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

        """Spanish Server welcome"""
        if m.guild == self.bot.spanServ:
            nadekoObj = self.bot.spanServ.get_member(116275390695079945)
            if str(nadekoObj.status) == 'offline':
                await self.bot.get_channel(243838819743432704).send(
                    'Welcome to the server.  Nadeko is currently down, '
                    'so please state your roles and someone in welcoming party will come to'
                    ' assign your role as soon as possible.  If no one comes, please tag the mods with `@Mods`.  '
                    'Thanks! '
                    '(<@&470364944479813635>)'
                )

    async def on_member_update(self, bef, af):
        """Nadeko updates"""
        if bef == self.bot.spanServ.get_member(116275390695079945) and bef.guild == self.bot.spanServ:
            # await self.bot.nadLog.send('Something happened with Nadeko') nadeko: 116275390695079945
            # await self.bot.nadLog.send(f'Nadeko went from {bef.status} to {af.status}')

            # if str(bef.status) == 'online' and str(af.status) == 'online':
            #     await self.bot.nadLog.send(
            #         f'Activity: {bef.activity}-->{af.activity}\n'
            #         f'Nick: {bef.nick}-->{af.nick}'
            #     )

            if str(bef.status) == 'online' and str(af.status) == 'offline':
                # await self.bot.nadLog.send('----------------------------------------------\n'
                #                           f'{datetime.now()} - Nadeko went offline')

                def check(befcheck, afcheck):
                    return af.id == befcheck.id and str(befcheck.status) == 'offline' and str(afcheck.status) == 'online'

                try:
                    print('Waiting')
                    await self.bot.wait_for('member_update', check=check, timeout=1200)
                    self.bot.waited = False
                except asyncio.TimeoutError:
                    self.bot.waited = True
                if self.bot.waited:
                    await self.bot.nadLog.send(  # nadeko was offline for 20 mins
                        "Nadeko has gone offline.  New users won't be able to tag themselves, "
                        "and therefore will not be able to join the server.  Please be careful of this."
                    )
                    await self.bot.spanSP.send(  # nadeko was offline for 20 mins
                        "Nadeko has gone offline.  New users won't be able to tag themselves, "
                        "and therefore will not be able to join the server.  Please be careful of this."
                    )

            if str(bef.status) == 'offline' and str(af.status) == 'online':
                # await self.bot.nadLog.send(f'----------------------------------------------\n'
                #                            f'{datetime.now()} - Nadeko came online')
                if self.bot.waited:
                    self.bot.waited = False  # waited is True if Nadeko has been offline for more than 20 minutes
                    await self.bot.nadLog.send(
                        'Nadeko is back online now and was previously offline for more than 20 minutes\n'
                        f'bot.waited is now {self.bot.waited}.')
                    await self.bot.spanSP.send('Nadeko is back online now.')

    async def on_member_remove(self, m):
        localtime = reference.LocalTimezone()
        if m.guild == self.bot.jpServ:
            emb = discord.Embed(
                description=''
                f":outbox_tray: **{m.name}#{m.discriminator}** has `left` the server. "
                f"({m.id})",
                colour=0xD12B2B,
                timestamp=datetime.now(tz=localtime)
            )

            emb.set_footer(
                text=f'User Leave ({self.bot.jpServ.member_count})',
                icon_url=m.avatar_url_as(static_format="png")
            )

            await self.bot.jpEverything.send(embed=emb)


def setup(bot):
    bot.add_cog(Welcome(bot))
