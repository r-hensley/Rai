import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import json
from urllib.parse import urlparse
import re

import os

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class Main:
    """My custom cog that does stuff!"""

    def __init__(self, bot):
        self.bot = bot
        # credit: https://gist.github.com/dperini/729294
        self._url = re.compile("""
            # protocol identifier
            (?:(?:https?|ftp)://)
            # user:pass authentication
            (?:\S+(?::\S*)?@)?
            (?:
              # IP address exclusion
              # private & local networks
              (?!(?:10|127)(?:\.\d{1,3}){3})
              (?!(?:169\.254|192\.168)(?:\.\d{1,3}){2})
              (?!172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})
              # IP address dotted notation octets
              # excludes loopback network 0.0.0.0
              # excludes reserved space >= 224.0.0.0
              # excludes network & broacast addresses
              # (first & last IP address of each class)
              (?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])
              (?:\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])){2}
              (?:\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-4]))
            |
              # host name
              (?:(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)
              # domain name
              (?:\.(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)*
              # TLD identifier
              (?:\.(?:[a-z\u00a1-\uffff]{2,}))
              # TLD may end with dot
              \.?
            )
            # port number
            (?::\d{2,5})?
            # resource path
            (?:[/?#]\S*)?
        """, re.VERBOSE | re.I)

        self._emoji = re.compile(r'<a?:[A-Za-z0-9\_]+:[0-9]{17,20}>')

    def jpenratio(self, msg):
        text = self._emoji.sub('', self._url.sub('', msg.content))
        en, jp, total = self.get_character_spread(text)
        return en / total if total else None

    def get_character_spread(self, text):
        english = 0
        japanese = 0
        for ch in text:
            if self.is_cjk(ch):
                japanese += 1
            elif self.is_english(ch):
                english += 1
        return english, japanese, english + japanese

    def is_cjk(self, char):
        CJK_MAPPING = (
            (0x3040, 0x30FF),  # Hiragana + Katakana
            (0xFF66, 0xFF9D),  # Half-Width Katakana
            (0x4E00, 0x9FAF)  # Common/Uncommon Kanji
        )
        return any(start <= ord(char) <= end for start, end in CJK_MAPPING)

    def is_english(self, char):
        # basically English characters save for w because of laughter
        RANGE_CHECK = (
            (0x61, 0x76),  # a to v
            (0x78, 0x7a),  # x to z
            (0x41, 0x56),  # A to V
            (0x58, 0x5a),  # X to Z
            (0xFF41, 0xFF56),  # ａ to ｖ
            (0xFF58, 0xFF5A),  # ｘ to ｚ
            (0xFF21, 0xFF36),  # Ａ to Ｖ
            (0xFF58, 0xFF3A),  # Ｘ to Ｚ
        )
        return any(start <= ord(char) <= end for start, end in RANGE_CHECK)

    def is_admin():
        async def pred(ctx):
            return ctx.channel.permissions_for(ctx.author).administrator

        return commands.check(pred)

    async def on_message(self, msg):
        """Message as the bot"""
        if str(msg.channel) == 'Direct Message with Ryry013#9234' \
                and int(msg.author.id) == self.bot.owner_id \
                and str(msg.content[0:3]) == 'msg':
            print('hello')
            await self.bot.get_channel(int(msg.content[4:22])).send(str(msg.content[22:]))

        """Ping me if someone says my name"""
        cont = str(msg.content)
        if (
                (
                        'ryry' in cont.casefold()
                        or ('ryan' in cont.casefold() and msg.channel.guild != self.bot.spanServ)
                        or 'らいらい' in cont.casefold()
                        or 'ライライ' in cont.casefold()
                ) and
                not msg.author.bot  # checks to see if account is a bot account
        ):  # random sad face
            await self.bot.spamChan.send(
                '<@202995638860906496> **By {} in <#{}>**: {}'.format(msg.author.name, msg.channel.id, msg.content))

        if msg.author.id == self.bot.owner_id and self.bot.selfMute == True:
            await msg.delete()

        """Ultra Hardcore"""
        if msg.author.id in self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])]:
            jpServ = self.bot.get_guild(self.bot.ID["jpServ"])
            engRole = next(role for role in jpServ.roles if role.id == 197100137665921024)
            jpRole = next(role for role in jpServ.roles if role.id == 196765998706196480)
            ratio = self.jpenratio(msg)
            if msg.guild == jpServ:
                if ratio is not None:
                    if jpRole in msg.author.roles:
                        if ratio < .55:
                            await msg.delete()
                    else:
                        if ratio > .45:
                            await msg.delete()

    @commands.group(invoke_without_command=True, aliases=['uhc'])
    async def ultrahardcore(self, ctx, member: discord.Member = None):
        """Irreversible hardcore mode.  Must talk to an admin to have this undone."""
        for i in ctx.guild.roles:
            if i.id == 486851965121331200:
                role = i
                break
        if not member:  # if no ID specified in command
            if ctx.author.id not in self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])]:  # if not enabled
                self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])].append(ctx.author.id)
                with open(f'{dir_path}/database.json', 'w') as write_file:
                    json.dump(self.bot.db, write_file)
                try:
                    await ctx.author.add_roles(role)
                except discord.errors.Forbidden:
                    await ctx.send("I couldn't add the ultra hardcore role")
                await ctx.send(f"{ctx.author.name} has chosen to enable ultra hardcore mode.  It works the same as "
                               "normal hardcore mode except that you can't undo it and asterisks don't change "
                               "anything.  Talk to a mod to undo this.")
            else:  # already enabled
                await ctx.send("You're already in ultra hardcore mode.")
        else:  # if you specified someone else's ID, then remove UHC from them
            if self.bot.jpJHO.permissions_for(ctx.author).administrator:
                if ctx.author.id not in self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])]:
                    self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])].remove(member.id)
                    with open(f'{dir_path}/database.json', 'w') as write_file:
                        json.dump(self.bot.db, write_file)
                    try:
                        await member.remove_roles(role)
                    except discord.errors.Forbidden:
                        await ctx.send("I couldn't remove the ultra hardcore role")
                    await ctx.send(f'Undid ultra hardcore mode for {member.name}')

    @ultrahardcore.command()
    async def list(self, ctx):
        """Lists the people currently in ultra hardcore mode"""
        string = 'The members in ultra hardcore mode right now are '
        for member in self.bot.db['ultraHardcore'][str(self.bot.ID["jpServ"])]:
            mem = self.bot.get_guild(189571157446492161).get_member(int(member))
            string = string + f'{mem.name}, '
        await ctx.send(string)

    @ultrahardcore.command()
    async def explanation(self, ctx):
        """Explains ultra hardcore mode for those who are using it and can't explain it"""
        await ctx.send('I am currently using ultra hardcore mode.  In this mode, I can not speak any English, '
                       'and I also can not undo this mode easily.')

    @commands.command()
    async def kawaii(self, ctx):
        """Try it"""
        await ctx.send('https://i.imgur.com/hRBicd2.png')

    @commands.command(aliases=['git'])
    async def github(self, ctx):
        """Gives my github page"""
        await ctx.send('https://github.com/ryry013/Rai')

    @commands.command()
    async def punch(self, ctx, user: discord.Member = None):
        """A punch command I made as a test"""
        if not user:
            user = ctx.author
        await ctx.send("ONE PUNCH! And " + user.mention + " is out! ლ(ಠ益ಠლ)")

    @commands.command()
    async def ping(self, ctx):
        """sends back 'hello'"""
        await ctx.send('hello')

    @commands.command()
    @commands.is_owner()
    async def selfMute(self, ctx, hour: float, minute: float):
        """mutes ryry for x amount of minutes"""
        self.bot.selfMute = True
        await ctx.send(f'Muting Ryry for {hour} hours and {minute} minutes (he chose to do this).')
        self.bot.selfMute = await asyncio.sleep(hour * 3600 + minute * 60, False)

    @commands.command()
    async def echo(self, ctx, *, content: str):
        """sends back whatever you send"""
        await ctx.send(f"{content}")

    # @commands.command()
    # async def at(self, ctx):
    #     """asyncio test"""
    #     x = False
    #     print(f'Before running the sleep, x should be false: {x}.')
    #     me = self.bot.get_guild(275146036178059265).get_member(self.bot.owner_id)
    #     x = await asyncio.sleep(2, str(me.status) == 'offline')
    #     print(f'I have ran x = await asyncio.sleep(=="offline").  If I\'m offline, x should be True: {x}.')

    # async def on_command_error(self, ctx, error):
    #     """Reduces 'command not found' error to a single line in console"""
    #     #  error = getattr(error, 'original', error)
    #     if isinstance(error, commands.CommandNotFound):
    #         print(error)

    @commands.command()
    @is_admin()
    async def pp(self, ctx):
        """Checks most active members who are in ping party but not welcoming party yet"""
        print('Checking ping party members')
        JHO = self.bot.get_channel(189571157446492161)
        mCount = {}

        async for m in JHO.history(limit=None, after=datetime.today() - timedelta(days=14)):
            try:
                mCount[m.author] += 1
            except KeyError:
                mCount[m.author] = 1
        print('Done counting messages')
        mSorted = sorted(list(mCount.items()), key=lambda x: x[1], reverse=True)
        mCount = {}
        for memberTuple in mSorted:
            mCount[memberTuple[0].id] = [memberTuple[0].name, memberTuple[1]]
        with open("sorted_members.json", "w") as write_file:
            json.dump(mCount, write_file)

        for i in JHO.guild.roles:
            if i.id == 357449148405907456:  # ping party
                pingparty = i
            if i.id == 250907197075226625:  # welcoming party
                welcomingparty = i

        pingpartylist = ''
        for member in mSorted:
            # print(member[0].name)
            try:
                if pingparty in member[0].roles and welcomingparty not in member[0].roles:
                    pingpartylist += f'{member[0].name}: {member[1]}\n'
            except AttributeError:
                print(f'This user left: {member[0].name}: {member[1]}')
        await ctx.send(pingpartylist)

    @commands.group(invoke_without_command=True)
    async def report(self, ctx, user: discord.Member = None):
        try:
            if not user:
                await ctx.message.delete()
        except discord.errors.Forbidden:
            print('Unable to delete message due to lacking permissions')

        conversation = ctx.author

        msg1Text = ["Welcome to the reporting module.  You're about to make a report to the mods of the "
                    "English-Japanese Exchange Server.  Please select one of the following options for your "
                    "report.\n\n"
                    "1) Send an anonymous report to the mods.\n"
                    "2) Request an audience with the mods to have a conversation with them (choose "
                    "this if you want a response to your report).\n"
                    "3) 日本語での説明\n"
                    "4) Cancel the report and leave this menu.",
                    "レポート機能へようこそ。あなたは 、English Japanese Language Exchange サーバーのモデレーター"
                    "に報告（レポート）しようとしています。レポートをするためには次のいずれかのオプションを"
                    "選択してください。\n\n"
                    "1) モデレーターに匿名のレポートを送ります\n"
                    "2) モデレーターと一緒にこのことについて会話ができるようにリクエストします"
                    "（あなたのレポートへの回答を希望する場合はこれを選択します）\n"
                    "3) レポートをキャンセルしてこのメ​​ニューを終了します"]
        msg2Text = ['Please type your report in one message below.  Make sure to include any relevant information, '
                    "such as who the report is about, which channel they did whatever you're reporting about was in, "
                    "and other users involved.",
                    "レポートは１つのメッセージで以下に書いてください。"
                    "レポートの対象者、対象のチャンネル、関係した他のユーザーなど、関連する情報を必ず含めてください。"]
        msg3Text = ['Thank you for your report.  The mods have been notified, and your name '
                    'will remain anonymous.',
                    'レポートはありがとうございます。管理者に匿名に送りました。']

        wasJapaneseRequested = False
        fromMod = False

        def check(reaction, user):
            return user == ctx.author and (str(reaction.emoji) in "1⃣2⃣3⃣4⃣")

        def check2(m):
            return m.author == conversation and m.channel == m.author.dm_channel

        async def option1():  # anonymous report
            # "please type your report below"
            if wasJapaneseRequested:  # 0: Eng      1: Jp       2: Span
                await conversation.send(msg2Text[1])
            else:
                await conversation.send(msg2Text[0])

            # wait for them to type
            try:
                reportMessage = await self.bot.wait_for('message', timeout=300.0, check=check2)
            except asyncio.TimeoutError:
                await conversation.send('Reporting module closed')

            # "thank you for the report"
            if wasJapaneseRequested:
                await conversation.send(msg3Text[1])
            else:
                await conversation.send(msg3Text[0])

            # send to spam and eggs
            await self.bot.get_channel(206230443413078016).send(f'Received report from a user: \n\n')
            await self.bot.get_channel(206230443413078016).send(f'{reportMessage.content}')

        async def option2(userIn):  # get into report room
            if not self.bot.currentReportRoomUser:  # if no one is in the room
                if userIn in self.bot.reportRoomWaitingList:  # if the user is in the waiting list
                    self.bot.reportRoomWaitingList.remove(userIn)  # remove from the waiting list
                self.bot.currentReportRoomUser = userIn  # set the current user
                await self.bot.reportRoom.set_permissions(userIn, read_messages=True)
                if not fromMod:  # set below on "if user:", about 17 lines below
                    if wasJapaneseRequested:
                        await self.bot.currentReportRoomUser.send('.\n\n\n\n\n__ここに行ってください__：<#485391894356951050>\n'
                                                                  'そこに10秒後に歓迎のメッセージを送ります。')
                    else:
                        await self.bot.currentReportRoomUser.send('.\n\n\n\n\n__'
                                                                  'Please go here__: <#485391894356951050>\n'
                                                                  "In ten seconds, I'll send a welcome message there.")

                await self.bot.reportRoom.send(f'<@{self.bot.currentReportRoomUser.id}>')
                await asyncio.sleep(10)
                msg4Text = [f"Welcome to the report room <@{self.bot.currentReportRoomUser.id}>.  Only the mods can "
                            f"read your messages here, so you can now make your report.  When you are finished, "
                            f"type `;done` and a log of this conversation will be sent to you.  Please ping one of "
                            f"the mods you see online or `@Active Staff` if no one responds to you within a minute.",
                            f"レポートルームへようこそ<@{self.bot.currentReportRoomUser.id}>。あなたのメッセージは"
                            "モデレーターだけが読むことができます。では（安心して）レポートを作成してください。"
                            "終わったら、`;done`と入力すると、この会話のログが送信されます。もし応答が返ってこなければ、"
                            "オンラインのモデレーターまたは`@Active Staff`にpingをしても構いません。"]

                if wasJapaneseRequested:
                    self.bot.entryMessage = await self.bot.reportRoom.send(msg4Text[1])
                else:
                    self.bot.entryMessage = await self.bot.reportRoom.send(msg4Text[0])

            else:
                if userIn not in self.bot.reportRoomWaitingList:
                    self.bot.reportRoomWaitingList.append(userIn)
                await userIn.send(f"Sorry but someone else is using the room right now.  "
                                  f"I'll message you when it's open in the order that I received requests.  "
                                  f"You are position {self.bot.reportRoomWaitingList.index(userIn)+1} on the list")
                await self.bot.get_channel(206230443413078016).send(f'The user {userIn.name} has tried to access '
                                                                    f'the report room, but was put on the wait list '
                                                                    f'because someone else is currently using it.')

        if user:  # if the mod specified a user
            fromMod = True  # this will stop the bot from PMing the user
            await option2(user)
            return

        async def options_menu(wasJapaneseRequested):
            if ctx.author not in self.bot.reportRoomWaitingList:  # if the user is not in the waiting list
                if wasJapaneseRequested:
                    msg1 = await conversation.send(msg1Text[1])
                else:
                    msg1 = await conversation.send(msg1Text[0])  # then give them the full menu
                await msg1.add_reaction("1⃣")
                await msg1.add_reaction('2⃣')
                await msg1.add_reaction('3⃣')
                if not wasJapaneseRequested:
                    await msg1.add_reaction('4⃣')

                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=300.0, check=check)
                except asyncio.TimeoutError:
                    await conversation.send('Reporting module closed')

                else:
                    if str(reaction.emoji) == "1⃣":  # requested to send a single message
                        await option1()

                    if str(reaction.emoji) == '2⃣':  # requested audience with mods
                        await option2(ctx.author)

                    if str(reaction.emoji) == '3⃣':  # requested Japanese
                        if not wasJapaneseRequested:
                            wasJapaneseRequested = True
                            await msg1.delete()
                            return wasJapaneseRequested
                        else:
                            await conversation.send('わかりました。お元気で!')
                            return

                    if str(reaction.emoji) == '4⃣':  # requested cancel
                        await conversation.send('Understood.  Have a nice day!')
                        return

            else:  # if the user was on the waiting list, put them straight into the room
                await option2(ctx.author)

        if not wasJapaneseRequested:
            wasJapaneseRequested = await options_menu(wasJapaneseRequested)
        if wasJapaneseRequested:  # the inside of options_menu might set this to be true, and then I want it to go again
            await options_menu(wasJapaneseRequested)

    @report.command()
    @is_admin()
    async def check_waiting_list(self, ctx):
        message = 'List of users on the waiting list: '
        if self.bot.reportRoomWaitingList:
            for user in self.bot.reportRoomWaitingList:
                message = message + f'{user.name}, '
        else:
            message = 'There are no users on the waiting list'
        await ctx.send(message)

    @report.command()
    @is_admin()
    async def clear_waiting_list(self, ctx):
        if self.bot.reportRoomWaitingList:
            for user in self.bot.reportRoomWaitingList:
                message = message + f'{user.name}, '
            self.bot.reportRoomWaitingList = []
            await ctx.send('Waiting list cleared')
        else:
            await ctx.send('There was no one on the waiting list.')

    @commands.command()
    async def done(self, ctx):
        if ctx.channel == self.bot.reportRoom:
            await self.bot.reportRoom.set_permissions(self.bot.currentReportRoomUser, overwrite=None)
            self.bot.finalMessage = ctx.message
            messages = []
            async for message in self.bot.reportRoom.history(after=self.bot.entryMessage):
                messages.append(message)
            messageLog = 'Start of log:\n'
            for i in messages:
                messageLog += f'**__{i.author}:__** {i.content} \n'
            if len(messageLog) > 2000:
                listOfMessages = []
                for i in range((len(messageLog) // 2000) + 1):
                    listOfMessages.append(messageLog[i * 2000:(i + 1) * 2000])
                for i in listOfMessages:
                    await self.bot.currentReportRoomUser.send(i)
            else:
                await self.bot.currentReportRoomUser.send(messageLog)
            self.bot.currentReportRoomUser = None
            await self.bot.reportRoom.send('Session closed, and a log has been sent to the user')
            for member in self.bot.reportRoomWaitingList:
                waiting_msg = await member.send('The report room is now open.  Try sending `;report` to me again.  '
                                                'If you wish to be removed from the waiting list, '
                                                'please react with the below emoji.')
                await waiting_msg.add_reaction('🚫')
                asyncio.sleep(10)

    # removes people from the waiting list for ;report if they react with '🚫' to a certain message
    async def on_reaction_add(self, reaction, user):
        if reaction.emoji == '🚫':
            if reaction.message.channel == user.dm_channel:
                if user in self.bot.reportRoomWaitingList:
                    self.bot.reportRoomWaitingList.remove(user)
                    await user.send("Understood.  You've been removed from the waiting list.  Have a nice day.")
                    await self.bot.get_channel(206230443413078016).send(f"The user {user.name} was previously on the "
                                                                        f"wait list for the report room but just "
                                                                        f"removed themselves.")
                else:
                    await user.send("You aren't on the waiting list.")


    @commands.command()
    @is_admin()
    async def swap(self, ctx):
        if self.bot.jpJHO.permissions_for(ctx.author).administrator:
            if self.bot.jpJHO.position == 4:
                await self.bot.jpJHO.edit(position=5, name='just_hanging_out_2')
                await self.bot.jpJHO2.edit(position=4, name='just_hanging_out')
            else:
                await self.bot.jpJHO.edit(position=4, name='just_hanging_out')
                await self.bot.jpJHO2.edit(position=5, name='just_hanging_out_2')


def setup(bot):
    bot.add_cog(Main(bot))
